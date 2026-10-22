#!/usr/bin/env python3
"""
Songkit by The Solid Ground - a local app for releasing your songs:
timed lyrics, lyric clips, Spotify Canvas loops and church-ready lyric files.
Everything runs on your own computer. Start it with:  python app.py
"""
import base64
import re
from pathlib import Path

import gradio as gr

import songkit as sk

HERE = Path(__file__).resolve().parent
OUT_ROOT = HERE / "output"
ASSETS = HERE / "assets"

CHARCOAL, PANEL, PANEL2 = "#1a1a16", "#24231e", "#2e2c26"
CREAM, STONE = "#e4d8c5", "#8c867f"
GOLD, SUNSET = "#c8963e", "#b04b24"


def song_dir(title):
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "untitled").lower()).strip("-") or "untitled"
    d = OUT_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    return d, slug


def fail(e):
    raise gr.Error(str(e)) from e


# ---------- actions ----------

def do_lyrics(title, lyrics, audio, model, device, progress=gr.Progress()):
    if not audio:
        raise gr.Error("Add the vocal stem (or full mix) first.")
    d, slug = song_dir(title)
    log = []
    progress(0.1, desc="Listening to the vocal...")
    try:
        lrc, srt, rows = sk.make_timed_lyrics(audio, lyrics, d / slug, model, device, log=log.append)
    except sk.SongkitError as e:
        fail(e)
    est = sum(1 for r in rows if r[2] == "estimated")
    note = (f"**{len(rows) - est}/{len(rows)} lines heard.** "
            + (f"{est} estimated; give those a quick check." if est else "All lines matched.")
            + f"  \nSaved to `{d}`")
    return rows, [str(lrc), str(srt)], note, str(srt)


def do_clip(title, song, clips, srt_file, srt_state, start, length, logo, progress=gr.Progress()):
    d, slug = song_dir(title)
    srt = srt_file or srt_state or None
    progress(0.2, desc="Stitching clips and adding captions...")
    try:
        out = sk.make_clip(song, clips or [], d / f"{slug}_clip_{str(start).replace(':', 'm')}.mp4",
                           srt, start, length, logo)
    except sk.SongkitError as e:
        fail(e)
    return str(out), f"Saved to `{out}`"


def do_canvas(title, clips, length, progress=gr.Progress()):
    d, slug = song_dir(title)
    progress(0.2, desc="Making the loop...")
    try:
        out = sk.make_canvas(clips or [], d / f"{slug}_canvas.mp4", length)
    except sk.SongkitError as e:
        fail(e)
    return str(out), f"Saved to `{out}`. Upload it in Spotify for Artists → Canvas."


def do_church(title, lyrics, artist, lines_per_slide, credits):
    d, slug = song_dir(title)
    try:
        slides = sk.make_slides(lyrics, d / f"{slug}_slides.txt", int(lines_per_slide))
        sheet = sk.make_lyric_sheet(lyrics, d / f"{slug}_lyric_sheet.html", title or "Untitled", artist, credits)
    except sk.SongkitError as e:
        fail(e)
    preview = slides.read_text(encoding="utf-8").split("\n\n")
    shown = "\n\n".join(f"— slide {i + 1} —\n{s}" for i, s in enumerate(preview[:8]))
    more = f"\n\n…and {len(preview) - 8} more" if len(preview) > 8 else ""
    return [str(slides), str(sheet)], shown + more, f"Saved to `{d}`"


# ---------- look ----------

def logo_html():
    p = ASSETS / "logo.png"
    img = ""
    if p.exists():
        img = f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" alt="Solid Ground">'
    return f"""<div id="sg-header">{img}
  <div><div class="sg-title">Songkit</div>
  <div class="sg-sub">by The Solid Ground · lyrics · clips · canvas · church kit</div>
  <div class="sg-note">Runs on your computer. Nothing is uploaded.</div></div></div>"""


CSS = f"""
:root, .dark {{
  --body-background-fill:{CHARCOAL}; --background-fill-primary:{PANEL}; --background-fill-secondary:{PANEL2};
  --block-background-fill:{PANEL}; --block-border-color:#3a382f; --border-color-primary:#3a382f;
  --body-text-color:{CREAM}; --body-text-color-subdued:{STONE}; --block-label-text-color:{STONE};
  --block-title-text-color:{CREAM}; --input-background-fill:{PANEL2}; --input-border-color:#3a382f;
  --color-accent:{GOLD}; --color-accent-soft:#3b3122; --link-text-color:{GOLD};
  --button-primary-background-fill:{GOLD}; --button-primary-background-fill-hover:#d9a74e;
  --button-primary-text-color:{CHARCOAL}; --button-primary-border-color:{GOLD};
  --button-secondary-background-fill:{PANEL2}; --button-secondary-text-color:{CREAM};
  --checkbox-background-color-selected:{GOLD}; --slider-color:{GOLD};
  --table-even-background-fill:{PANEL}; --table-odd-background-fill:{PANEL2};
}}
.gradio-container {{ max-width:1100px !important; margin:auto; }}
#sg-header {{ display:flex; align-items:center; gap:20px; padding:18px 6px 14px;
  border-bottom:2px solid {GOLD}; margin-bottom:6px; }}
#sg-header img {{ width:96px; height:96px; filter:drop-shadow(0 4px 10px rgba(0,0,0,.6)); }}
.sg-title {{ font-family:'Rockwell','Roboto Slab','Georgia',serif; font-weight:800; font-size:34px;
  letter-spacing:.08em; text-transform:uppercase; color:{CREAM}; line-height:1; }}
.sg-sub {{ color:{GOLD}; font-size:13px; letter-spacing:.14em; text-transform:uppercase; margin-top:6px; }}
.sg-note {{ color:{STONE}; font-size:12px; margin-top:4px; }}
.tab-nav button.selected, button[role=tab][aria-selected=true] {{ color:{GOLD} !important; border-color:{GOLD} !important; }}
.sg-tip {{ color:{STONE}; font-size:13px; }}
footer {{ display:none !important; }}
"""

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.amber,
    neutral_hue=gr.themes.colors.stone,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
)

LYRICS_HELP = ("One sung line per line, in order, with repeats included. "
               "[Verse] / [Chorus] tags and blank lines are fine; they're used for slides and the lyric sheet.")


# ---------- layout ----------

with gr.Blocks(title="Songkit · The Solid Ground", css=CSS, theme=THEME) as demo:
    gr.HTML(logo_html())
    srt_state = gr.State(None)

    with gr.Row():
        title = gr.Textbox(label="Song title", placeholder="Anyway I'll Rise", scale=2)
        artist = gr.Textbox(label="Artist", value="The Solid Ground", scale=1)
    lyrics = gr.Textbox(label="Lyrics", lines=10, placeholder="[Verse 1]\nFirst line\nSecond line\n\n[Chorus]\n...",
                        info=LYRICS_HELP)

    with gr.Tabs():
        with gr.Tab("1 · Timed lyrics"):
            gr.Markdown("Makes **.lrc** and **.srt** files. Use the vocal stem from Suno for the best match. "
                        "Paste the timing into Musixmatch to get synced lyrics on Spotify.", elem_classes="sg-tip")
            with gr.Row():
                vocal = gr.Audio(label="Vocal stem (or full mix)", type="filepath", sources=["upload"])
                with gr.Column():
                    model = gr.Dropdown(["large-v3", "medium", "small"], value="large-v3", label="Whisper model",
                                        info="large-v3 for a desktop GPU · medium or small for a laptop")
                    device = gr.Radio(["auto", "cuda", "cpu"], value="auto", label="Run on",
                                      info="auto tries the GPU, then falls back to CPU")
                    go_lyrics = gr.Button("Time my lyrics", variant="primary")
            lyr_note = gr.Markdown()
            table = gr.Dataframe(headers=["Time", "Line", "How"], interactive=False, wrap=True)
            lyr_files = gr.File(label="Downloads", file_count="multiple")
            go_lyrics.click(do_lyrics, [title, lyrics, vocal, model, device],
                            [table, lyr_files, lyr_note, srt_state])

        with gr.Tab("2 · Clips"):
            gr.Markdown("Vertical 9:16 clips for Reels, Shorts and TikTok. Make 3–4 Gemini clips first "
                        "(*vertical 9:16, no music, ambient sound only*). Their audio is replaced by your song. "
                        "Captions use the timing from tab 1 automatically.", elem_classes="sg-tip")
            with gr.Row():
                with gr.Column():
                    song = gr.Audio(label="Song (full mix)", type="filepath", sources=["upload"])
                    clips = gr.File(label="Video clips, in order (they loop if short)",
                                    file_count="multiple", file_types=["video"])
                    srt_in = gr.File(label="Captions .srt (optional; tab 1 fills this in)", file_types=[".srt"])
                with gr.Column():
                    start = gr.Textbox(label="Start at", value="0:00", info="e.g. 1:12, where the chorus hits")
                    length = gr.Slider(10, 60, value=30, step=1, label="Length (seconds)")
                    logo = gr.Checkbox(value=True, label="Put the Solid Ground badge in the corner")
                    go_clip = gr.Button("Make clip", variant="primary")
                    clip_note = gr.Markdown()
            clip_out = gr.Video(label="Clip", height=520)
            go_clip.click(do_clip, [title, song, clips, srt_in, srt_state, start, length, logo],
                          [clip_out, clip_note])

        with gr.Tab("3 · Spotify Canvas"):
            gr.Markdown("A silent 3–8 second vertical loop that plays behind your song on Spotify. No text.",
                        elem_classes="sg-tip")
            with gr.Row():
                with gr.Column():
                    canvas_clips = gr.File(label="Video clip(s)", file_count="multiple", file_types=["video"])
                    canvas_len = gr.Slider(3, 8, value=8, step=1, label="Length (seconds)")
                    go_canvas = gr.Button("Make Canvas", variant="primary")
                    canvas_note = gr.Markdown()
                canvas_out = gr.Video(label="Canvas", height=480)
            go_canvas.click(do_canvas, [title, canvas_clips, canvas_len], [canvas_out, canvas_note])

        with gr.Tab("4 · Church kit"):
            gr.Markdown("**Slides** (.txt, one blank line between slides) import into ProPresenter, EasyWorship "
                        "and most presentation apps. The **lyric sheet** opens in your browser; "
                        "use Print → Save as PDF.", elem_classes="sg-tip")
            with gr.Row():
                with gr.Column():
                    per_slide = gr.Slider(1, 4, value=2, step=1, label="Lines per slide")
                    credits = gr.Textbox(label="Credits line (optional)",
                                         placeholder="Words & music: Josh · Music created with AI assistance")
                    go_church = gr.Button("Make church kit", variant="primary")
                    church_note = gr.Markdown()
                    church_files = gr.File(label="Downloads", file_count="multiple")
                slide_preview = gr.Textbox(label="Slide preview", lines=18, interactive=False)
            go_church.click(do_church, [title, lyrics, artist, per_slide, credits],
                            [church_files, slide_preview, church_note])

    gr.Markdown(f"<div class='sg-tip'>Files are saved in <code>{OUT_ROOT}</code>, one folder per song.</div>")


if __name__ == "__main__":
    OUT_ROOT.mkdir(exist_ok=True)
    demo.queue().launch(inbrowser=True, favicon_path=str(ASSETS / "favicon.png"),
                        allowed_paths=[str(OUT_ROOT)])
