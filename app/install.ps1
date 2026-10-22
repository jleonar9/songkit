# Songkit installer for Windows. Run via Install-Songkit.bat (double-click).
# Installs Python + ffmpeg if needed, sets Songkit up in %LOCALAPPDATA%\Songkit,
# adds Desktop/Start Menu shortcuts and the songkit:// link the website uses.
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Installing Songkit'

function Step($n, $t) { Write-Host "`n[$n/6] $t" -ForegroundColor Yellow }
function Ok($t)       { Write-Host "      $t" -ForegroundColor Green }
function Fail($t)     { Write-Host "`n$t" -ForegroundColor Red; Read-Host "`nPress Enter to close"; exit 1 }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') }

$src  = $PSScriptRoot
$dest = Join-Path $env:LOCALAPPDATA 'Songkit'
$hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
$wg = @('--silent', '--accept-package-agreements', '--accept-source-agreements')

Write-Host ""
Write-Host "  SONGKIT - by The Solid Ground" -ForegroundColor DarkYellow
Write-Host "  One-time setup. Takes about 5-10 minutes. Keep this window open." -ForegroundColor Gray

# ---------- 1. Python ----------
function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in '3.12', '3.11', '3.13', '3.10') {
            $p = & py "-$v" -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
        }
    }
    foreach ($v in '312', '311', '313', '310') {
        $p = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe"
        if (Test-Path $p) { return $p }
    }
    return $null
}
Step 1 'Checking for Python...'
$py = Find-Python
if (-not $py) {
    if (-not $hasWinget) { Fail "Python isn't installed and this PC can't install it automatically.`nInstall Python 3.12 from https://www.python.org/downloads/ then run this installer again." }
    Write-Host '      Installing Python 3.12...'
    winget install -e --id Python.Python.3.12 --scope user @wg | Out-Null
    Refresh-Path
    $py = Find-Python
    if (-not $py) { Fail "Python didn't install. Install Python 3.12 from https://www.python.org/downloads/ then run this again." }
}
Ok "Python ready ($py)"

# ---------- 2. Folder + files ----------
Step 2 'Copying Songkit files...'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
foreach ($f in 'app.py', 'songkit.py', 'requirements.txt', 'start.bat', 'uninstall.bat') {
    Copy-Item (Join-Path $src $f) $dest -Force
}
$lic = Join-Path (Split-Path $src -Parent) 'LICENSE'
if (Test-Path $lic) { Copy-Item $lic $dest -Force }
Copy-Item (Join-Path $src 'assets') $dest -Recurse -Force
Ok "Installed to $dest"

# ---------- 3. ffmpeg ----------
function Find-Ffmpeg {
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $link = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\ffmpeg.exe'
    if (Test-Path $link) { return $link }
    $pk = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path $pk) {
        $hit = Get-ChildItem $pk -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}
Step 3 'Checking for ffmpeg (video tool)...'
$ff = Find-Ffmpeg
if (-not $ff) {
    if (-not $hasWinget) { Fail "ffmpeg isn't installed and this PC can't install it automatically.`nSee https://ffmpeg.org/download.html, then run this installer again." }
    Write-Host '      Installing ffmpeg...'
    winget install -e --id Gyan.FFmpeg @wg | Out-Null
    Refresh-Path
    $ff = Find-Ffmpeg
    if (-not $ff) { Fail "ffmpeg didn't install. Restart your PC and run this installer again." }
}
Set-Content -Path (Join-Path $dest 'ffmpeg_path.txt') -Value $ff -Encoding ASCII
Ok "ffmpeg ready"

# ---------- 4. Python packages ----------
Step 4 'Installing Songkit''s parts (the longest step)...'
$vpy = Join-Path $dest '.venv\Scripts\python.exe'
if (-not (Test-Path $vpy)) { & $py -m venv (Join-Path $dest '.venv') }
& $vpy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $vpy -m pip install -r (Join-Path $dest 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "Installing packages failed. Check your internet connection and run this again." }
$nvidia = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'NVIDIA' }
if ($nvidia) {
    Write-Host "      NVIDIA graphics found ($($nvidia[0].Name)) - adding GPU speed-up..."
    & $vpy -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Write-Host "      GPU speed-up skipped; Songkit will use the CPU." -ForegroundColor DarkYellow }
}
Ok "Packages ready"

# ---------- 5. Shortcuts ----------
Step 5 'Adding shortcuts...'
$sh = New-Object -ComObject WScript.Shell
$icon = Join-Path $dest 'assets\songkit.ico'
function Make-Link($path, $target, $desc) {
    $l = $sh.CreateShortcut($path)
    $l.TargetPath = $target; $l.WorkingDirectory = $dest; $l.IconLocation = $icon; $l.Description = $desc
    $l.Save()
}
Make-Link (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Songkit.lnk') (Join-Path $dest 'start.bat') 'Start Songkit'
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Songkit'
New-Item -ItemType Directory -Force -Path $menu | Out-Null
Make-Link (Join-Path $menu 'Songkit.lnk') (Join-Path $dest 'start.bat') 'Start Songkit'
Make-Link (Join-Path $menu 'Uninstall Songkit.lnk') (Join-Path $dest 'uninstall.bat') 'Remove Songkit'
Ok 'Desktop and Start Menu shortcuts added'

# ---------- 6. Website link (songkit://) ----------
Step 6 'Connecting the Songkit website to this PC...'
$k = 'HKCU:\Software\Classes\songkit'
New-Item $k -Force | Out-Null
Set-ItemProperty $k '(default)' 'URL:Songkit'
New-ItemProperty $k 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
New-Item "$k\DefaultIcon" -Force | Out-Null
Set-ItemProperty "$k\DefaultIcon" '(default)' $icon
New-Item "$k\shell\open\command" -Force | Out-Null
Set-ItemProperty "$k\shell\open\command" '(default)' ('"' + $env:ComSpec + '" /c ""' + (Join-Path $dest 'start.bat') + '" --site"')
Ok 'The "Launch Songkit" button on the website now works'

Write-Host "`n  All done! Songkit is installed." -ForegroundColor Green
Write-Host "  Start it from the website's Launch button or the Songkit icon on your desktop." -ForegroundColor Gray
Write-Host "  Your files are saved in Documents\Songkit.`n" -ForegroundColor Gray
Start-Process (Join-Path $dest 'start.bat') -WorkingDirectory $dest
Read-Host 'Press Enter to close this window'
