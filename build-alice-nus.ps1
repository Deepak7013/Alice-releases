$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$BuildDir = Join-Path $Root 'alice-runtime-dist'
$SpecDir = Join-Path $Root 'build-spec'
New-Item -ItemType Directory -Force -Path $BuildDir,$SpecDir | Out-Null
python -m PyInstaller --noconfirm --onefile --noconsole `
  --name alice_nus_sidecar --distpath $BuildDir --workpath (Join-Path $Root 'pyinstaller-work') `
  --specpath $SpecDir --add-data "$Root\alice;alice" --add-data "$Root\VERSION.txt;." --collect-submodules alice `
  --collect-all google.genai --collect-all openai --collect-all numpy `
  --collect-all sklearn --collect-all fitz --collect-all PIL --collect-all pystray `
  --collect-all cryptography --collect-all docx --collect-all openpyxl `
  --collect-all pptx --collect-all reportlab --collect-all requests --collect-all scipy `
  --collect-all pyautogui --collect-all pygetwindow --collect-all pycaw `
  --collect-all pyttsx3 --collect-all comtypes `
  --hidden-import win32timezone `
  (Join-Path $Root 'alice_nus_sidecar.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
$Exe = Join-Path $BuildDir 'alice_nus_sidecar.exe'
if (-not (Test-Path -LiteralPath $Exe)) { throw 'Frozen ALICE runtime was not produced.' }
Get-FileHash -LiteralPath $Exe -Algorithm SHA256 | Format-List
