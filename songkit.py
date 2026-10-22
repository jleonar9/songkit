#!/usr/bin/env python3
"""
songkit - timed lyrics, lyric clips, Spotify Canvas loops and church-ready
lyric files for your songs. Runs entirely on your own computer.

CLI:
  python songkit.py lyrics --audio vocals.wav --lyrics song.txt
  python songkit.py clip --song song.wav --clips a.mp4 b.mp4 --srt song.srt --start 1:12 --length 30
  python songkit.py clip --canvas --clips a.mp4 --out canvas.mp4
  python songkit.py slides --lyrics song.txt --title "Anyway I'll Rise"

GUI:  python app.py
"""
import argparse
import difflib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGO = HERE / "assets" / "logo.png"


class SongkitError(Exception):
    """A problem worth showing to the user in plain words."""


# ---------- helpers ----------

def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def parse_time(t):
    t = str(t).strip() or "0"
    try:
        if ":" in t:
            m, s = t.split(":", 1)
            return int(m) * 60 + float(s)
        return float(t)
    except ValueError:
        raise SongkitError(f"Couldn't read the time '{t}'. Use something like 1:12 or 72.")


def ts_lrc(t):
    cs = int(round(max(t, 0) * 100))
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"[{m:02d}:{s:02d}.{cs:02d}]"


def ts_srt(t):
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for n, (s, e, text) in enumerate(items, 1):
            f.write(f"{n}\n{ts_srt(s)} --> {ts_srt(e)}\n{text}\n\n")


def read_srt(path):
    items = []
    txt = Path(path).read_text(encoding="utf-8-sig")
    for block in re.split(r"\n\s*\n", txt.strip()):
        ls = block.splitlines()
        if len(ls) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ls[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        items.append((s, e, " ".join(ls[2:])))
    return items


def ffmpeg_path():
    ff = None
    saved = HERE / "ffmpeg_path.txt"  # written by the Windows installer
    if saved.exists():
        p = saved.read_text(encoding="utf-8", errors="ignore").strip()
        if p and Path(p).exists():
            ff = p
    ff = ff or shutil.which("ffmpeg")
    if not ff:
        raise SongkitError("ffmpeg isn't installed. On Windows run: winget install ffmpeg "
                           "(then close and reopen the app).")
    return ff


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SongkitError("ffmpeg failed:\n" + r.stderr[-1500:])


# ---------- lyrics text ----------

def read_sections(text):
    """Split lyrics into sections: [(label or None, [lines])]. Blank lines and [Tags] start new sections."""
    sections, label, cur = [], None, []
    for raw in text.splitlines():
        s = raw.strip()
        tag = re.fullmatch(r"\[(.+)\]", s)
        if not s or tag:
            if cur:
                sections.append((label, cur))
            cur, label = [], (tag.group(1) if tag else None)
            continue
        cur.append(s)
    if cur:
        sections.append((label, cur))
    return sections


def read_lyrics_text(text):
    return [l for _, lines in read_sections(text) for l in lines]


# ---------- 1. timed lyrics ----------

def _add_gpu_libs():
    """On Windows, let faster-whisper find the NVIDIA libraries the installer added."""
    if os.name != "nt":
        return
    import glob
    import site
    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def transcribe(audio, model_size="large-v3", device="auto", log=print):
    _add_gpu_libs()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SongkitError("faster-whisper isn't installed. Run: pip install faster-whisper")
    tries = [("cuda", "float16"), ("cpu", "int8")] if device == "auto" else \
            [(device, "float16" if device == "cuda" else "int8")]
    last = None
    for dev, ct in tries:
        try:
            log(f"Loading Whisper '{model_size}' on {dev} (first run downloads the model)...")
            model = WhisperModel(model_size, device=dev, compute_type=ct)
            segs, _ = model.transcribe(str(audio), word_timestamps=True, language="en")
            words = [(norm(w.word), w.start, w.end) for s in segs for w in (s.words or [])]
            words = [w for w in words if w[0]]
            log(f"Heard {len(words)} words on {dev}.")
            return words
        except Exception as e:  # GPU libs missing, out of memory, etc.
            last = e
            log(f"  {dev} didn't work ({e.__class__.__name__}: {e}).")
    raise SongkitError(f"Transcription failed: {last}")


def align(lines, words):
    toks = [(i, norm(t)) for i, l in enumerate(lines) for t in l.split() if norm(t)]
    sm = difflib.SequenceMatcher(None, [t for _, t in toks], [w[0] for w in words], autojunk=False)
    starts = [None] * len(lines)
    ends = [None] * len(lines)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            li = toks[blk.a + k][0]
            _, ws, we = words[blk.b + k]
            starts[li] = ws if starts[li] is None else min(starts[li], ws)
            ends[li] = we if ends[li] is None else max(ends[li], we)

    known = [i for i, s in enumerate(starts) if s is not None]
    if not known:
        raise SongkitError("Couldn't match any lyrics to the vocal. Use the vocal stem and check the lyrics.")
    matched = set(known)

    for i in range(len(lines)):  # estimate unmatched lines from neighbours
        if starts[i] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is not None and nxt is not None:
            starts[i] = starts[prev] + (i - prev) / (nxt - prev) * (starts[nxt] - starts[prev])
        elif prev is not None:
            starts[i] = ends[prev] + 2.5 * (i - prev)
        else:
            starts[i] = max(0.0, starts[nxt] - 2.5 * (nxt - i))

    for i in range(1, len(starts)):
        if starts[i] <= starts[i - 1]:
            starts[i] = starts[i - 1] + 0.3

    for i in range(len(lines)):
        e = ends[i] if ends[i] is not None else starts[i] + 3.0
        e = max(e + 0.4, starts[i] + 1.0)
        if i + 1 < len(lines):
            e = min(e, starts[i + 1] - 0.05)
        ends[i] = max(e, starts[i] + 0.3)

    return starts, ends, matched


def make_timed_lyrics(audio, lyrics_text, out_stem, model="large-v3", device="auto", log=print):
    """Returns (lrc_path, srt_path, rows) where rows = [(time, line, 'heard'|'estimated')]."""
    lines = read_lyrics_text(lyrics_text)
    if not lines:
        raise SongkitError("The lyrics are empty.")
    words = transcribe(audio, model, device, log)
    starts, ends, matched = align(lines, words)
    out_stem = Path(out_stem)
    lrc, srt = out_stem.with_suffix(".lrc"), out_stem.with_suffix(".srt")
    lrc.write_text("".join(f"{ts_lrc(s)}{l}\n" for s, l in zip(starts, lines)), encoding="utf-8")
    write_srt(srt, list(zip(starts, ends, lines)))
    rows = [(ts_lrc(s)[1:-1], l, "heard" if i in matched else "estimated")
            for i, (s, l) in enumerate(zip(starts, lines))]
    return lrc, srt, rows


# ---------- 2. clips + canvas ----------

def _prep_visuals(ff, clips, work):
    if not clips:
        raise SongkitError("Add at least one video clip.")
    parts = []
    for i, c in enumerate(clips):
        p = work / f"part{i}.mp4"
        run([ff, "-y", "-i", str(Path(c).resolve()), "-an", "-vf",
             "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(p)])
        parts.append(p)
    (work / "list.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    visuals = work / "visuals.mp4"
    run([ff, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", str(visuals)], cwd=work)
    return visuals


def make_clip(song, clips, out, srt=None, start="0", length=30.0, logo=False):
    ff = ffmpeg_path()
    if not song:
        raise SongkitError("Add the song (full mix).")
    start, L = parse_time(start), float(length)
    work = Path(tempfile.mkdtemp(prefix="songkit_"))
    try:
        visuals = _prep_visuals(ff, clips, work)
        inputs = ["-stream_loop", "-1", "-i", str(visuals), "-ss", str(start), "-i", str(Path(song).resolve())]
        chain = "[0:v]null"
        if srt:
            items = [(max(s - start, 0), min(e - start, L), t)
                     for s, e, t in read_srt(srt) if e > start and s < start + L]
            write_srt(work / "cap.srt", items)
            style = ("FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00C5D8E4,"
                     "OutlineColour=&H00161A1A,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=40")
            chain = f"[0:v]subtitles=cap.srt:force_style='{style}'"
        if logo and LOGO.exists():
            inputs += ["-i", str(LOGO)]
            graph = (f"{chain}[base];[2:v]scale=190:190,format=rgba,colorchannelmixer=aa=0.9[lg];"
                     f"[base][lg]overlay=W-w-48:72[v]")
        else:
            graph = f"{chain}[v]"
        run([ff, "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "1:a", "-t", str(L),
             "-af", f"afade=t=in:d=0.5,afade=t=out:st={max(L - 1.5, 0)}:d=1.5",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(Path(out).resolve())], cwd=work)
        return Path(out)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_canvas(clips, out, length=8.0):
    ff = ffmpeg_path()
    work = Path(tempfile.mkdtemp(prefix="songkit_"))
    try:
        visuals = _prep_visuals(ff, clips, work)
        L = max(3.0, min(float(length), 8.0))  # Spotify Canvas: 3-8 seconds
        run([ff, "-y", "-stream_loop", "-1", "-i", str(visuals), "-t", str(L), "-an",
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(Path(out).resolve())])
        return Path(out)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------- 3. church kit ----------

def make_slides(lyrics_text, out, lines_per_slide=2):
    """Plain-text slides: one blank line between slides. ProPresenter, EasyWorship
    and most presentation apps can import this."""
    slides = []
    for _, lines in read_sections(lyrics_text):
        for i in range(0, len(lines), lines_per_slide):
            slides.append("\n".join(lines[i:i + lines_per_slide]))
    if not slides:
        raise SongkitError("The lyrics are empty.")
    Path(out).write_text("\n\n".join(slides) + "\n", encoding="utf-8")
    return Path(out)


def make_lyric_sheet(lyrics_text, out, title="Untitled", artist="The Solid Ground", credits=""):
    """Printable one-page lyric sheet (open in a browser, Print > Save as PDF)."""
    import base64
    logo_tag = ""
    if LOGO.exists():
        b64 = base64.b64encode(LOGO.read_bytes()).decode()
        logo_tag = f'<img class="logo" src="data:image/png;base64,{b64}" alt="">'
    secs = []
    for label, lines in read_sections(lyrics_text):
        head = f'<div class="label">{html.escape(label)}</div>' if label else ""
        body = "<br>".join(html.escape(l) for l in lines)
        secs.append(f'<section>{head}<p>{body}</p></section>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
 @page {{ size: letter; margin: 0.6in; }}
 body {{ font-family: Georgia, 'Times New Roman', serif; color:#1a1a16; margin:0 auto; max-width:7.3in; }}
 header {{ display:flex; align-items:center; gap:18px; border-bottom:2px solid #c8963e; padding-bottom:12px; margin-bottom:18px; }}
 .logo {{ width:78px; height:78px; }}
 h1 {{ font-family: 'Arial Black', Arial, sans-serif; text-transform:uppercase; letter-spacing:.06em; margin:0; font-size:26px; }}
 .artist {{ color:#8c867f; font-size:14px; margin-top:4px; letter-spacing:.08em; text-transform:uppercase; }}
 main {{ columns:2; column-gap:.45in; }}
 section {{ break-inside:avoid; margin:0 0 14px; }}
 .label {{ font-family: Arial, sans-serif; font-size:11px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; color:#b04b24; margin-bottom:3px; }}
 p {{ margin:0; font-size:14px; line-height:1.45; }}
 footer {{ margin-top:18px; border-top:1px solid #ddd; padding-top:8px; font-size:10.5px; color:#8c867f; }}
</style></head><body>
<header>{logo_tag}<div><h1>{html.escape(title)}</h1><div class="artist">{html.escape(artist)}</div></div></header>
<main>{''.join(secs)}</main>
<footer>{html.escape(credits)}</footer>
</body></html>"""
    Path(out).write_text(page, encoding="utf-8")
    return Path(out)


# ---------- cli ----------

def main():
    ap = argparse.ArgumentParser(description="Timed lyrics, lyric clips and church lyric files.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("lyrics", help="make .lrc/.srt from a vocal stem + lyrics text")
    a.add_argument("--audio", required=True)
    a.add_argument("--lyrics", required=True, help="text file, one sung line per line, repeats included")
    a.add_argument("--model", default="large-v3", help="large-v3 (GPU) or medium/small (laptop)")
    a.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    a.add_argument("--out", help="output name without extension")

    c = sub.add_parser("clip", help="9:16 clip from video clips + song + captions")
    c.add_argument("--clips", nargs="+", required=True)
    c.add_argument("--song")
    c.add_argument("--srt")
    c.add_argument("--start", default="0")
    c.add_argument("--length", type=float, default=30)
    c.add_argument("--logo", action="store_true", help="add the logo in the corner")
    c.add_argument("--canvas", action="store_true", help="silent 8s loop for Spotify Canvas")
    c.add_argument("--out", default="clip.mp4")

    s = sub.add_parser("slides", help="church slides (.txt) + printable lyric sheet (.html)")
    s.add_argument("--lyrics", required=True)
    s.add_argument("--title", default="Untitled")
    s.add_argument("--artist", default="The Solid Ground")
    s.add_argument("--lines", type=int, default=2, help="lines per slide")

    args = ap.parse_args()
    try:
        if args.cmd == "lyrics":
            text = Path(args.lyrics).read_text(encoding="utf-8-sig")
            stem = args.out or str(Path(args.lyrics).with_suffix(""))
            lrc, srt, rows = make_timed_lyrics(args.audio, text, stem, args.model, args.device)
            for t, line, how in rows:
                print(f"  [{t}] {line}" + ("   <- estimated" if how == "estimated" else ""))
            print(f"\nWrote {lrc} and {srt}")
        elif args.cmd == "clip":
            if args.canvas:
                print(f"Canvas ready: {make_canvas(args.clips, args.out)}")
            else:
                print(f"Clip ready: {make_clip(args.song, args.clips, args.out, args.srt, args.start, args.length, args.logo)}")
        elif args.cmd == "slides":
            text = Path(args.lyrics).read_text(encoding="utf-8-sig")
            stem = Path(args.lyrics).with_suffix("")
            sl = make_slides(text, f"{stem}_slides.txt", args.lines)
            sh = make_lyric_sheet(text, f"{stem}_sheet.html", args.title, args.artist)
            print(f"Wrote {sl} and {sh}")
    except SongkitError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
