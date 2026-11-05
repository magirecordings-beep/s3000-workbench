# S3000 Workbench

A Windows program for the Akai S3000XL: edit samples and programs, build disk images, send samples over MIDI,
and auto-sample synths through your sound card's **ASIO** driver.

## Install

1. Download `S3000-Workbench-Setup-<version>.exe` from **Releases** (or from the latest run under **Actions › Build Windows installer › Artifacts**).
2. Run it. It installs for your user account, so no administrator password is needed.
3. The first time, Windows may show **"Windows protected your PC"** because the program is not code-signed.
   Click **More info › Run anyway**.

Start it from the Start menu or the desktop shortcut. The Workbench opens in its own window.
Closing the window closes the program.

## Auto sampling through ASIO

1. Close any DAW (ASIO lets one program use the card at a time).
2. Route the synth's input to an ASIO channel. On E-MU cards: in PatchMix, give the input strip a send to a **HOST ASIO** pair.
3. In the Workbench, open **Auto sample**. **Source** is already set to **ASIO**. Choose the device and inputs and press **Enable input**.
4. Connect MIDI, press **Test note** (it also checks the pitch), then **Start auto sample**.

Monitor through the sound card itself (PatchMix or your interface's mixer).

**No sound card handy?** Start menu › **S3000 Workbench (test tone, no sound card)** runs the program with a built-in test tone.

Saved work lives in `%LOCALAPPDATA%\S3000 Workbench` and is kept when you uninstall or upgrade.
A log file (`log.txt`) is in the same folder if something goes wrong.

## Building

Every push to `main` builds the installer on GitHub (Actions › Build Windows installer). Pushing a tag such as `v1.0.0`
also publishes it as a release. To build by hand on Windows:

```
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean s3000_workbench.spec
iscc installer\setup.iss
```

The version number is `VERSION` in `app/s3000_workbench.py`.

## How it works

`app/s3000_workbench.py` serves the Workbench page on `127.0.0.1:8741` (this computer only), records through
ASIO with [sounddevice](https://python-sounddevice.readthedocs.io/) (PortAudio built with ASIO support), and opens
the page in Microsoft Edge's app mode with its own profile. It only accepts connections from its own window.

ASIO is a trademark and software of Steinberg Media Technologies GmbH. If you distribute this program publicly,
check the current ASIO licensing terms.
