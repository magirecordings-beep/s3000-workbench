# S3000 Workbench

A Windows and Mac program for the Akai S3000XL: edit samples and programs, build disk images, send samples over MIDI,
and auto-sample synths through your sound card (**ASIO** on Windows, **Core Audio** on the Mac).

## Install on Windows

1. Download `S3000-Workbench-Setup-<version>.exe` from **Releases** (or from the latest run under **Actions › Build Windows and Mac apps › Artifacts**).
2. Run it. It installs for your user account, so no administrator password is needed.
3. The first time, Windows may show **"Windows protected your PC"** because the program is not code-signed.
   Click **More info › Run anyway**.

Start it from the Start menu or the desktop shortcut. The Workbench opens in the program's own window
(WebView2, the Edge engine built into Windows), with no browser sign-in or sync prompts. Closing the window
closes the program. If WebView2 is missing, it falls back to an Edge app window; `--edge` forces that.

## Install on the Mac

1. Download `S3000-Workbench-<version>-mac-apple-silicon.dmg` (M1 and later) or `...-mac-intel.dmg` (older Intel Macs).
2. Open it and drag **S3000 Workbench** onto **Applications**.
3. The app is not notarized by Apple, so the first time macOS says it cannot check it for malware.
   Open **System Settings › Privacy & Security**, scroll down and press **Open Anyway** next to S3000 Workbench
   (on older macOS: right-click the app › **Open**). After that it opens normally.
4. When you first enable the audio input, macOS asks to let S3000 Workbench use the microphone: press **Allow**,
   or the inputs stay silent. You can change this later under **Privacy & Security › Microphone**.

On the Mac the app records through Core Audio, and MIDI goes through the app itself (CoreMIDI), because the Mac's
built-in web engine has no Web MIDI. Every MIDI feature works the same: the keyboard on the Programs tab, auto
sampling, and MIDI send. Saved work lives in `~/Library/Application Support/S3000 Workbench`.

To test without an interface, run it from Terminal with a test tone and a MIDI loopback port:
`"/Applications/S3000 Workbench.app/Contents/MacOS/S3000 Workbench" --fake`

## Auto sampling through ASIO (Windows)

1. Close any DAW (ASIO lets one program use the card at a time).
2. Route the synth's input to an ASIO channel. On E-MU cards: in PatchMix, give the input strip a send to a **HOST ASIO** pair.
3. In the Workbench, open **Auto sample**. **Source** is already set to **ASIO**. Choose the device and inputs and press **Enable input**.
4. Connect MIDI, press **Test note** (it also checks the pitch), then **Start auto sample**.

Monitor through the sound card itself (PatchMix or your interface's mixer).

**No sound card handy?** Start menu › **S3000 Workbench (test tone, no sound card)** runs the program with a built-in test tone.

Saved work lives in `%LOCALAPPDATA%\S3000 Workbench` and is kept when you uninstall or upgrade.
A log file (`log.txt`) is in the same folder if something goes wrong.

## Building

Every push to `main` builds the Windows installer and the Mac disk images on GitHub (Actions › Build Windows and Mac apps).
Pushing a tag such as `v1.0.0` also publishes them as a release. To build by hand on Windows:

```
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean s3000_workbench.spec
iscc installer\setup.iss
```

On a Mac:

```
pip install -r requirements.txt pyinstaller pillow
pyinstaller --noconfirm --clean s3000_workbench_mac.spec
```

The version number is `VERSION` in `app/s3000_workbench.py`.

## How it works

`app/s3000_workbench.py` serves the Workbench page on `127.0.0.1:8741` (this computer only), records through
ASIO with [sounddevice](https://python-sounddevice.readthedocs.io/) (PortAudio built with ASIO support), and shows
the page in a [pywebview](https://pywebview.flowrl.com/) WebView2 window. On the Mac it records through Core Audio,
shows the page in WKWebView, and bridges MIDI with [python-rtmidi](https://pypi.org/project/python-rtmidi/) (`app/midi_bridge.py`). It only accepts connections from its own window.
The MIDI keyboard and MIDI send ports you choose are remembered.

ASIO is a trademark and software of Steinberg Media Technologies GmbH. If you distribute this program publicly,
check the current ASIO licensing terms.
