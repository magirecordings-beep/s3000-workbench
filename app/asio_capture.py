"""Audio recording for the S3000 Workbench app: ASIO on Windows, Core Audio on the Mac.
One input stream, recorded while the page asks for it."""
import os
import sys
import threading
import time

os.environ.setdefault("SD_ENABLE_ASIO", "1")   # makes sounddevice load its PortAudio build with ASIO (Windows)

import numpy as np


class Capture:
    """The audio callback copies frames into a list while recording and keeps a running peak for the meters."""

    def __init__(self, fake=False):
        self.fake = fake
        self.stream = None
        self.fake_run = False
        self.lock = threading.Lock()
        self.rec = False
        self.buf = []
        self.peak = np.zeros(2, dtype=np.float32)
        self.xruns = 0
        self.rate = None
        self.info = {}
        self.pick = None            # Core Audio: device channels to keep (the stream opens 0..max of them)

    @property
    def is_open(self):
        return self.stream is not None or self.fake_run

    # ---------- devices ----------
    def devices(self):
        if self.fake:
            return [{"id": 0, "name": "Test tone (started with --fake)", "inputs": 8, "rate": 44100}]
        import sounddevice as sd
        apis = sd.query_hostapis()
        if sys.platform == "win32":
            asio = [i for i, a in enumerate(apis) if "ASIO" in a["name"]]
            if not asio:
                raise RuntimeError("ASIO is not available on this PC. Install your sound card's ASIO driver, then restart the program.")
        else:
            asio = list(range(len(apis)))     # Core Audio on the Mac
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d["hostapi"] in asio and d["max_input_channels"] > 0:
                out.append({"id": i, "name": d["name"], "inputs": d["max_input_channels"],
                            "rate": int(d["default_samplerate"])})
        return out

    # ---------- open / close ----------
    def open(self, device, channels, rate):
        self.close()
        channels = [int(c) for c in channels][:2] or [0, 1]
        if self.fake:
            self.rate = int(rate or 44100)
            self.fake_run = True
            threading.Thread(target=self._fake_loop, args=(len(channels),), daemon=True).start()
            self.info = {"name": "Test tone", "rate": self.rate, "channels": channels}
            return self.info
        import sounddevice as sd
        dev = sd.query_devices(device)
        win = sys.platform == "win32"
        if win:
            n, extra, self.pick = len(channels), sd.AsioSettings(channel_selectors=channels), None
        else:
            # Core Audio: open the device's first channels up to the highest one wanted, keep only the chosen ones
            n = min(max(channels) + 1, int(dev["max_input_channels"]))
            channels = [c for c in channels if c < n] or [0]
            extra, self.pick = None, channels
        tried, last = [], None
        for r in [rate, dev["default_samplerate"]]:
            if not r or r in tried:
                continue
            tried.append(r)
            try:
                self.stream = sd.InputStream(
                    device=device, channels=n, samplerate=r, dtype="float32",
                    extra_settings=extra, callback=self._callback, latency="low")
                self.stream.start()
                break
            except Exception as e:      # rate refused by the driver: fall back to the card's own rate
                last = e
                self.stream = None
        if self.stream is None:
            what = "The ASIO driver" if win else "The audio device"
            raise RuntimeError("%s would not open at %s Hz: %s. Close any other program using the interface (a DAW) and try again."
                               % (what, " or ".join(str(int(t)) for t in tried), last))
        self.rate = int(self.stream.samplerate)
        self.info = {"name": dev["name"], "rate": self.rate, "channels": channels,
                     "requested": int(rate) if rate else None}
        return self.info

    def close(self):
        self.fake_run = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        with self.lock:
            self.rec = False
            self.buf = []

    # ---------- audio ----------
    def _callback(self, indata, frames, time_info, status):
        if self.pick is not None:
            indata = indata[:, self.pick]
        data = indata if indata.shape[1] == 2 else np.repeat(indata[:, :1], 2, axis=1)
        p = np.abs(data).max(axis=0)
        with self.lock:
            np.maximum(self.peak, p, out=self.peak)
            if self.rec:
                self.buf.append(data.copy())
                if status:
                    self.xruns += 1

    def _fake_loop(self, nch):
        """A 220 Hz saw that sounds for 1.5 s every 3 s, so the meters and recordings have something in them."""
        block, t0, n = 512, time.perf_counter(), 0
        while self.fake_run:
            i = np.arange(n, n + block)
            on = ((i / self.rate) % 3.0) < 1.5
            saw = (((i * 220.0 / self.rate) % 1.0) * 2 - 1) * 0.4 * on
            data = np.stack([saw, saw * 0.8], axis=1).astype(np.float32)
            self._callback(data if nch == 2 else data[:, :1], block, None, None)
            n += block
            ahead = n / self.rate - (time.perf_counter() - t0)
            if ahead > 0:
                time.sleep(ahead)

    def start(self):
        with self.lock:
            self.buf = []
            self.xruns = 0
            self.rec = True

    def stop(self):
        with self.lock:
            self.rec = False
            take = np.concatenate(self.buf) if self.buf else np.zeros((0, 2), dtype=np.float32)
            self.buf = []
            return take, self.xruns

    def levels(self):
        with self.lock:
            p = self.peak.copy()
            self.peak[:] = 0
        return [float(p[0]), float(p[1])]
