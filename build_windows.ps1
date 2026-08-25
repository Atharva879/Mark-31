$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install .[windows,multimodal,voice]
python -m playwright install chromium
python -m pip install pyinstaller
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
pyinstaller --noconfirm --clean jarvis-agent.spec
Write-Host "Built dist/Mark31Jarvis.exe"
Write-Host "Run the executable once to configure providers and allowed local roots."
