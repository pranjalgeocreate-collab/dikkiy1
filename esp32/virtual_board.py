#!/usr/bin/env python3
"""Virtual Dikkey board: runs the REAL board code (board/dikkey.py) on the Mac before the ESP32 arrives.

Stand-ins for the ESP32-only parts:
  INMP441 mic  -> the Mac's microphone        MAX98357A + speaker -> the Mac's speaker
  BOOT button  -> "Hold to talk" on the page  RGB LED             -> the circle on the page
  wifi         -> already connected           viper mic routine   -> the same maths in numpy
Everything else (recording while held, the HTTP to /talk, fillers, streaming playback, stop-by-button)
is the exact code the board will run.

Run:  .venv/bin/python virtual_board.py      then open  http://localhost:8710
"""
import builtins, json, os, queue, socket, sys, threading, time, types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import sounddevice as sd

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("VBOARD_PORT", 8710))
state = {"pressed": False, "led": (0, 0, 0), "log": []}


def note(line):
    state["log"].append(time.strftime("%H:%M:%S ") + line)
    del state["log"][:-60]


# ---------------------------------------------------------------- stand-ins for MicroPython modules
class FakeI2S:
    RX, TX, MONO = 0, 1, 0

    def __init__(self, idx, sck=None, ws=None, sd_=None, mode=0, bits=16, format=0, rate=16000, ibuf=0, **kw):
        self.mode, self.bits, self.rate = mode, bits, rate
        if mode == FakeI2S.RX:
            self.stream = sd.InputStream(samplerate=rate, channels=1, dtype="int16", blocksize=1024)
            self.stream.start()
        else:
            # Output runs on a CALLBACK stream, not blocking .write(): the OS gives that callback its own
            # high-priority real-time thread, so playback stays smooth even if the Mac is busy elsewhere -
            # a blocking write from an ordinary Python thread can stall under load and the speaker clicks/
            # crackles right at the stall. write() below just drops bytes in a queue; the callback below
            # pulls from it on its own schedule, padding with silence (a clean gap, not a click) if we're
            # behind, so a slow feeder causes a brief pause, not noise.
            self._q = queue.Queue()
            self._carry = b""

            def callback(outdata, frames, time_info, status):
                need = frames * 2                     # int16 mono: 2 bytes per frame
                buf = self._carry
                while len(buf) < need:
                    try:
                        buf += self._q.get_nowait()
                    except queue.Empty:
                        buf += b"\x00" * (need - len(buf))
                        break
                outdata[:] = np.frombuffer(buf[:need], dtype=np.int16).reshape(-1, 1)
                self._carry = buf[need:]

            self.stream = sd.OutputStream(samplerate=rate, channels=1, dtype="int16", blocksize=1024, callback=callback)
            self.stream.start()

    def readinto(self, buf):
        """The INMP441 gives 24-bit samples in 32-bit slots; the board code shifts them right by MIC_SHIFT (14),
        so hand it the Mac's 16-bit samples shifted left by 14: the result is the original loudness."""
        n = len(buf) // 4
        data, _ = self.stream.read(n)
        out = np.frombuffer(buf, dtype=np.int32, count=n)
        out[:] = data[:, 0].astype(np.int32) << 14
        return n * 4

    def write(self, buf):
        self._q.put(bytes(buf))
        return len(buf)

    def deinit(self):
        if self.mode == FakeI2S.TX:
            while not self._q.empty():             # let the callback actually finish playing what's queued
                time.sleep(0.02)
            time.sleep(0.15)
        self.stream.stop()
        self.stream.close()

    @staticmethod
    def shift(buf, bits, shift):
        a = np.frombuffer(buf, dtype=np.int16)
        if shift < 0:
            a >>= -shift
        else:
            a <<= shift


class FakePin:
    IN = OUT = PULL_UP = 0

    def __init__(self, num, *a, **k):
        self.num = num

    def value(self):
        return 0 if state["pressed"] else 1      # BOOT reads 0 while held


class FakeNeoPixel:
    def __init__(self, pin, n):
        self.px = [(0, 0, 0)] * n

    def __setitem__(self, i, v):
        self.px[i] = v

    def write(self):
        state["led"] = self.px[0]


class FakeWLAN:
    def __init__(self, *a): pass
    def active(self, *a): return True
    def isconnected(self): return True
    def ifconfig(self): return ("127.0.0.1", "", "", "")
    def connect(self, *a): pass


def mp_viper(f):
    return f


machine = types.ModuleType("machine"); machine.I2S, machine.Pin = FakeI2S, FakePin
micropython = types.ModuleType("micropython"); micropython.viper = mp_viper
network = types.ModuleType("network"); network.WLAN, network.STA_IF = FakeWLAN, 0
neopixel = types.ModuleType("neopixel"); neopixel.NeoPixel = FakeNeoPixel
config = types.ModuleType("config")
config.WIFI_SSID, config.WIFI_PASS = "(virtual)", ""
config.BRAIN = os.environ.get("VBOARD_BRAIN", "http://127.0.0.1:8700")
config.TOY_ID, config.LANG = "virtual-board", os.environ.get("VBOARD_LANG", "")
config.MIC, config.AMP = {"sck": 5, "ws": 6, "sd": 7}, {"sck": 15, "ws": 16, "sd": 17}
config.BUTTON, config.LED, config.VOLUME_DOWN, config.MIC_SHIFT = 0, 48, 0, 14
builtins.ptr32 = builtins.ptr16 = object             # viper type names
# MicroPython's time helpers
time.sleep_ms = lambda ms: time.sleep(ms / 1000)
time.ticks_ms = lambda: int(time.monotonic() * 1000)
time.ticks_diff = lambda a, b: a - b
for name, mod in (("machine", machine), ("micropython", micropython), ("network", network),
                  ("neopixel", neopixel), ("config", config)):
    sys.modules[name] = mod


class MPSocket(socket.socket):
    """MicroPython sockets have write/readline/readinto on the socket itself."""
    def write(self, b):
        self.sendall(b)

    def _file(self):
        if not hasattr(self, "_f"):
            self._f = self.makefile("rb")
        return self._f

    def readline(self):
        return self._file().readline()

    def readinto(self, mv):
        return self._file().readinto(mv)


socket.socket = MPSocket
sys.path.insert(0, os.path.join(HERE, "board"))
import dikkey  # noqa: E402  (the real board code)

_orig_print = builtins.print


def board_print(*a, **k):                          # the board's log shows on the page too
    _orig_print(*a, **k)
    note(" ".join(str(x) for x in a))


dikkey.print = board_print


def to16(src, dst, n, shift):
    """Same as the board's viper routine: 32-bit mic slots -> 16-bit samples."""
    s = np.frombuffer(src, dtype=np.int32, count=n).astype(np.int64) >> shift
    np.frombuffer(dst, dtype=np.int16, count=n)[:] = np.clip(s, -32768, 32767)


dikkey._to16 = to16

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Virtual Dikkey board</title><style>
:root{--bg:#f5f7f3;--ink:#1c2420;--muted:#5b6861;--card:#fff;--line:#d8dfd9}
@media (prefers-color-scheme:dark){:root{--bg:#121614;--ink:#e5ebe7;--muted:#9aa8a0;--card:#1a201d;--line:#2c3530}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
.w{max-width:520px;margin:0 auto;padding:28px 16px;display:grid;gap:18px;justify-items:center;text-align:center}
h1{margin:0;font-size:22px} p{margin:0;color:var(--muted);font-size:14px}
.board{background:#0d3b2e;border-radius:18px;padding:22px;display:grid;gap:16px;justify-items:center;width:100%;box-sizing:border-box}
.led{width:70px;height:70px;border-radius:50%;border:3px solid #ffffff33;transition:background .2s,box-shadow .2s}
#state{color:#d8f0e6;font-weight:600}
button{font:inherit;font-size:20px;font-weight:700;padding:26px 34px;border:0;border-radius:16px;background:#e8b923;color:#222;cursor:pointer;user-select:none;touch-action:none;width:100%}
button.on{background:#3ec46d;color:#fff}
button:focus-visible{outline:3px solid #fff;outline-offset:3px}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;font:12px/1.4 ui-monospace,monospace;text-align:left;width:100%;box-sizing:border-box;max-height:260px;overflow:auto;white-space:pre-wrap;margin:0}
</style></head><body><div class="w">
<h1>Virtual Dikkey board</h1>
<p>The real ESP32 toy code, running on this Mac: the Mac's mic and speaker stand in for the board's.</p>
<div class="board"><div class="led" id="led"></div><div id="state">starting…</div>
<button id="boot" type="button" aria-label="Hold to talk (the board's BOOT button)">Hold to talk (BOOT)</button></div>
<p>Hold the button (or the space bar), talk, let go. Press again while Dikkey talks to stop him.</p>
<pre id="log"></pre></div><script>
const names={"0,0,6":"ready — hold to talk","0,40,0":"listening…","40,18,0":"thinking…","24,0,40":"talking","40,0,0":"problem (see log)","0,0,0":"off"};
async function set(p){await fetch(p?"/press":"/release",{method:"POST"});b.classList.toggle("on",p)}
const b=document.getElementById("boot");
b.addEventListener("pointerdown",e=>{b.setPointerCapture(e.pointerId);set(true)});
b.addEventListener("pointerup",()=>set(false));b.addEventListener("pointercancel",()=>set(false));
let space=false;
addEventListener("keydown",e=>{if(e.code==="Space"&&!space){space=true;e.preventDefault();set(true)}});
addEventListener("keyup",e=>{if(e.code==="Space"){space=false;e.preventDefault();set(false)}});
setInterval(async()=>{try{const s=await(await fetch("/state")).json();const [r,g,bl]=s.led;
const c=`rgb(${Math.min(255,r*6)},${Math.min(255,g*6)},${Math.min(255,bl*6)})`;
document.getElementById("led").style.background=c;document.getElementById("led").style.boxShadow=`0 0 30px ${c}`;
document.getElementById("state").textContent=names[s.led.join(",")]||"";
const lg=document.getElementById("log");lg.textContent=s.log.join("\\n");lg.scrollTop=lg.scrollHeight}catch{}},250);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/state":
            self._send(200, json.dumps({"led": list(state["led"]), "pressed": state["pressed"], "log": state["log"]}),
                       "application/json")
        else:
            self._send(200, PAGE, "text/html; charset=utf-8")

    def do_POST(self):
        if self.path in ("/press", "/release"):
            state["pressed"] = self.path == "/press"
            self._send(200, "{}", "application/json")
        else:
            self._send(404, "{}", "application/json")

    def log_message(self, *a):
        pass


def run_board():
    """The board's main loop; if it ever crashes, say so on the page (red LED) instead of failing silently."""
    import traceback
    try:
        dikkey.run()
    except Exception:
        note("BOARD CODE CRASHED:\n" + traceback.format_exc())
        state["led"] = (40, 0, 0)


def main():
    if self_check():
        threading.Thread(target=run_board, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("virtual board: open http://localhost:%d  (brain %s)" % (PORT, config.BRAIN), flush=True)
    srv.serve_forever()


def self_check():
    """Mic and speaker reachable? (macOS may need microphone permission for the terminal.)"""
    try:
        rec = sd.rec(1600, samplerate=16000, channels=1, dtype="int16")
        sd.wait()
        note("mic ok (level %d)" % int(np.abs(rec).max()))
        return True
    except Exception as e:
        note("mic not available: %s" % e)
        state["led"] = (40, 0, 0)
        return False


if __name__ == "__main__":
    main()
