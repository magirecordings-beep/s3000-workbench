# PyInstaller build for the S3000 Workbench Mac app (run on a Mac: pyinstaller --noconfirm --clean s3000_workbench_mac.spec)
import re
from PyInstaller.utils.hooks import collect_all

VERSION = re.search(r'VERSION = "([^"]+)"', open("app/s3000_workbench.py").read()).group(1)

datas, binaries, hiddenimports = [("app/workbench.html", ".")], [], ["sounddevice", "_sounddevice", "_cffi_backend"]
# PortAudio (Core Audio), pywebview with its Cocoa/WKWebView backend, and rtmidi (CoreMIDI)
for pkg in ("_sounddevice_data", "webview", "rtmidi"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
hiddenimports += ["webview.platforms.cocoa", "objc", "Foundation", "AppKit", "WebKit", "Quartz", "Security",
                  "UniformTypeIdentifiers", "midi_bridge"]

a = Analysis(["app/s3000_workbench.py"], pathex=["app"], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=["tkinter", "matplotlib", "PIL", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="S3000 Workbench", console=False, upx=False,
          argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="S3000 Workbench", upx=False)
app = BUNDLE(coll, name="S3000 Workbench.app", icon="installer/app.png",
             bundle_identifier="com.magirecordings.s3000workbench", version=VERSION,
             info_plist={
                 "CFBundleDisplayName": "S3000 Workbench",
                 "CFBundleShortVersionString": VERSION,
                 "CFBundleVersion": VERSION,
                 "NSHighResolutionCapable": True,
                 "LSMinimumSystemVersion": "11.0",
                 "LSApplicationCategoryType": "public.app-category.music",
                 "NSMicrophoneUsageDescription":
                     "S3000 Workbench records your synth through your audio interface for the Auto sample tab.",
                 "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
             })
