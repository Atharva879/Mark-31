# PyInstaller specification for Mark-31 Jarvis desktop UI.
# Build on Windows with the project optional dependencies installed.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project = Path(SPECPATH)
hiddenimports = [
    "tkinter",
    "PIL",
    "playwright.sync_api",
    "pywinauto",
    "win32crypt",
]
hiddenimports += collect_submodules("llm")
hiddenimports += collect_submodules("skills")
hiddenimports += collect_submodules("memory")
datas = collect_data_files("playwright")

analysis = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Mark31Jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
