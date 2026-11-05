# PyInstaller build for the S3000 Workbench Windows program (run: pyinstaller --noconfirm --clean s3000_workbench.spec)
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [("app/workbench.html", ".")], [], ["sounddevice", "_sounddevice", "_cffi_backend"]
# PortAudio DLLs that ship with sounddevice, including the build with ASIO support
d, b, h = collect_all("_sounddevice_data")
datas += d; binaries += b; hiddenimports += h

a = Analysis(["app/s3000_workbench.py"], pathex=["app"], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=["tkinter", "matplotlib", "PIL", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="S3000 Workbench", console=False,
          icon="installer/app.ico", upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="S3000 Workbench", upx=False)
