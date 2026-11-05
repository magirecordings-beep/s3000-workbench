"""
S3000 Workbench for Windows

Serves the Workbench page on this computer only (127.0.0.1), records through the sound card's ASIO
driver for the Auto sample tab, and opens the page in its own app window (Microsoft Edge app mode).
The program closes itself a few seconds after its window is closed.

    S3000 Workbench.exe              normal start
    S3000 Workbench.exe --fake       no sound card needed: a test tone instead of ASIO
    S3000 Workbench.exe --no-window  do not open a window (for testing in a browser)
"""
import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import urllib.request
import webbrowser

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from asio_capture import Capture

APP_NAME = "S3000 Workbench"
VERSION = "1.0.0"
PORT = 8741                 # fixed, so the page keeps the same address and its saved work between runs
LEVEL_EVERY = 0.05          # seconds between level reports to the page
IDLE_EXIT = 8               # seconds after the last window closes before the program exits
FIRST_WINDOW_WAIT = 120     # give up if no window connects at all within this time

log = logging.getLogger("s3k")


# ---------- paths ----------
def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def data_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(root, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def message_box(text, title=APP_NAME):
    """A visible error even though the program has no console window."""
    log.error(text)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
            return
        except Exception:
            pass
    print(text, file=sys.stderr)


# ---------- the app window ----------
def find_browser():
    """Edge first (on every Windows 10/11 PC), then Chrome. Both have an app mode and Web MIDI."""
    if sys.platform != "win32":
        return None
    cands = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            cands.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for exe in ("msedge.exe", "chrome.exe"):
                try:
                    with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\\" + exe) as k:
                        cands.append(winreg.QueryValue(k, None))
                except OSError:
                    pass
    except ImportError:
        pass
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            cands.append(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def open_window(url):
    exe = find_browser()
    if not exe:
        log.info("No Edge or Chrome found; opening the default browser")
        webbrowser.open(url)
        return
    profile = os.path.join(data_dir(), "Window")
    args = [exe, "--app=" + url, "--user-data-dir=" + profile, "--window-size=1440,900",
            "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
    log.info("Opening window: %s", exe)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(args, close_fds=True, creationflags=flags)


# ---------- the page ----------
def page_bytes(port):
    with open(resource("workbench.html"), encoding="utf-8") as f:
        html = f.read()
    flag = '<script>window.S3K_APP=%s;</script>\n' % json.dumps({"version": VERSION, "ws": "/asio"})
    i = html.find("<script")
    html = html[:i] + flag + html[i:] if i >= 0 else flag + html
    return html.encode("utf-8")


def http(status, body, ctype):
    reason = {200: "OK", 403: "Forbidden", 404: "Not Found"}[status]
    return Response(status, reason, Headers([("Content-Type", ctype), ("Content-Length", str(len(body))),
                                             ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")]), body)


class App:
    def __init__(self, args):
        self.args = args
        self.cap = Capture(args.fake)
        self.clients = set()
        self.page = page_bytes(args.port)
        self.url = "http://127.0.0.1:%d/" % args.port
        self.origins = {"http://127.0.0.1:%d" % args.port, "http://localhost:%d" % args.port}
        self.done = None
        self.idle_task = None

    # plain web requests: the page itself, and a ping used to find a copy that is already running
    def process_request(self, connection, request):
        path = request.path.split("?")[0]
        if path == "/asio":
            origin = request.headers.get("Origin")
            if origin not in self.origins:
                log.warning("Refused a connection from %s", origin)
                return http(403, b"This program only answers its own window.", "text/plain")
            return None
        if path in ("/", "/index.html"):
            return http(200, self.page, "text/html; charset=utf-8")
        if path == "/ping":
            return http(200, json.dumps({"app": "s3000-workbench", "version": VERSION}).encode(), "application/json")
        if path == "/show":
            if not self.args.no_window:
                open_window(self.url)
            return http(200, b"ok", "text/plain")
        return http(404, b"Not found", "text/plain")

    async def handler(self, ws):
        for old in list(self.clients):          # one window records at a time: the newest takes over
            await old.close(1000, "Opened in another window")
        self.clients.add(ws)
        if self.idle_task:
            self.idle_task.cancel()
            self.idle_task = None
        log.info("Window connected")
        await ws.send(json.dumps({"type": "hello", "version": VERSION, "fake": self.cap.fake, "app": True}))

        async def levels():
            while True:
                await asyncio.sleep(LEVEL_EVERY)
                if self.cap.is_open:
                    await ws.send(json.dumps({"type": "level", "peaks": self.cap.levels()}))

        task = asyncio.create_task(levels())
        try:
            async for raw in ws:
                msg = json.loads(raw)
                rid, cmd = msg.get("id"), msg.get("cmd")
                try:
                    if cmd == "devices":
                        await ws.send(json.dumps({"id": rid, "type": "devices", "devices": self.cap.devices()}))
                    elif cmd == "open":
                        info = self.cap.open(msg.get("device"), msg.get("channels") or [0, 1], msg.get("rate"))
                        log.info("Opened %s, inputs %s at %d Hz", info["name"], "+".join(str(c + 1) for c in info["channels"]), info["rate"])
                        await ws.send(json.dumps({"id": rid, "type": "opened", **info}))
                    elif cmd == "start":
                        self.cap.start()
                        await ws.send(json.dumps({"id": rid, "type": "started"}))
                    elif cmd == "stop":
                        take, xruns = self.cap.stop()
                        await ws.send(json.dumps({"id": rid, "type": "take", "frames": int(take.shape[0]),
                                                  "rate": self.cap.rate, "xruns": xruns}))
                        await ws.send(take.T.astype("float32").tobytes())    # left block, then right
                    elif cmd == "close":
                        self.cap.close()
                        await ws.send(json.dumps({"id": rid, "type": "closed"}))
                    else:
                        raise RuntimeError("Unknown command %r" % cmd)
                except Exception as e:
                    log.exception("Command %s failed", cmd)
                    await ws.send(json.dumps({"id": rid, "type": "error", "message": str(e)}))
        except Exception:
            pass
        finally:
            task.cancel()
            self.clients.discard(ws)
            log.info("Window disconnected")
            if not self.clients:
                self.cap.close()
                self.idle_task = asyncio.create_task(self.exit_after(IDLE_EXIT))

    async def exit_after(self, seconds):
        await asyncio.sleep(seconds)
        if not self.clients and not self.args.stay:
            log.info("No window open; exiting")
            self.done.set_result(None)

    async def run(self):
        self.done = asyncio.get_running_loop().create_future()
        async with serve(self.handler, "127.0.0.1", self.args.port, process_request=self.process_request,
                         max_size=None, ping_interval=20):
            log.info("%s %s running at %s%s", APP_NAME, VERSION, self.url, " (test tone)" if self.args.fake else "")
            if not self.args.no_window:
                open_window(self.url)
            self.idle_task = asyncio.create_task(self.exit_after(FIRST_WINDOW_WAIT))
            await self.done
        self.cap.close()


def already_running(port):
    """If a copy is already running, ask it to open another window and return True."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=2) as r:
            if json.load(r).get("app") == "s3000-workbench":
                urllib.request.urlopen("http://127.0.0.1:%d/show" % port, timeout=2).read()
                return True
    except Exception:
        pass
    return False


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--fake", action="store_true", help="test tone instead of ASIO")
    ap.add_argument("--no-window", action="store_true", help="do not open the app window")
    ap.add_argument("--stay", action="store_true", help="keep running after the window closes")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    logging.basicConfig(filename=os.path.join(data_dir(), "log.txt"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if sys.stderr is not None:
        logging.getLogger().addHandler(logging.StreamHandler())

    if already_running(args.port):
        return
    try:
        asyncio.run(App(args).run())
    except OSError as e:
        message_box("%s could not start: port %d on this computer is in use by another program (%s)." % (APP_NAME, args.port, e))
    except Exception as e:
        log.exception("Crashed")
        message_box("%s stopped because of an error:\n\n%s\n\nDetails are in %s" % (APP_NAME, e, os.path.join(data_dir(), "log.txt")))


if __name__ == "__main__":
    main()
