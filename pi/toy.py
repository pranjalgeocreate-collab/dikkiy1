#!/usr/bin/env python3
"""talktoy — the toy side, for a Raspberry Pi Zero W.

Hold the button, talk, let go. The recording goes to the brain server on the
Mac, and the spoken reply plays on the speaker. Standard library + gpiozero
only (both ship with Raspberry Pi OS), so nothing needs pip on the Zero.

A small web page on :8080 shows status and the last exchange, and has a
"talk" button that records 5 seconds, for testing from a phone.
"""
import json, os, signal, subprocess, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env(os.path.join(HERE, "config.env"))
BRAIN = os.environ.get("BRAIN_URL", "http://192.168.1.50:8700").rstrip("/")
TOY_ID = os.environ.get("TOY_ID", "dikkey")
MIC = os.environ.get("MIC_DEVICE", "default")        # `arecord -l` to list
SPEAKER = os.environ.get("SPEAKER_DEVICE", "default")  # `aplay -l` to list
BUTTON_PIN = int(os.environ.get("BUTTON_PIN", 17))
LED_PIN = int(os.environ.get("LED_PIN", 27))
WEB_PORT = int(os.environ.get("WEB_PORT", 8080))
MAX_SECONDS = int(os.environ.get("MAX_SECONDS", 15))  # safety stop if the button sticks
REQ_TIMEOUT = int(os.environ.get("BRAIN_TIMEOUT", 320))  # stories take minutes on the Mac
TOY_LANG = os.environ.get("TOY_LANG", "en")  # language of the first "thinking" line; then follows the child
FILLER_EVERY = int(os.environ.get("FILLER_EVERY", 8))  # seconds between "still thinking" lines
MIN_BYTES = 16000  # under ~0.5 s of audio = an accidental tap
TMP = "/tmp/talktoy"
SLEEPY = os.path.join(HERE, "sleepy.wav")

os.makedirs(TMP, exist_ok=True)
state = {"status": "starting", "heard": "", "reply": "", "last_ms": None, "brain_ok": None, "talks": 0, "lang": TOY_LANG}
busy = threading.Lock()

try:
    from gpiozero import Button, LED
    button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
    led = LED(LED_PIN)
except Exception as e:  # lets the web page still work on a desk without GPIO
    print("GPIO not available:", e, flush=True)
    button = led = None


def light(on):
    if led:
        led.on() if on else led.off()


players = set()               # aplay processes currently sounding
cancel = threading.Event()    # set by the button / Stop: drop whatever Dikkey is doing


def play(path):
    """Play a WAV; returns early if stop_everything() kills it."""
    if cancel.is_set():
        return
    p = subprocess.Popen(["aplay", "-q", "-D", SPEAKER, path])
    players.add(p)
    try:
        p.wait()
    finally:
        players.discard(p)


def stop_everything():
    """Button pressed (or Stop tapped) while Dikkey is thinking, talking or singing."""
    cancel.set()
    for p in list(players):
        p.terminate()


def record_start(path, seconds=MAX_SECONDS):
    return subprocess.Popen(["arecord", "-q", "-D", MIC, "-f", "S16_LE", "-r", "16000", "-c", "1",
                             "-t", "wav", "-d", str(seconds), path])


def ask_brain(wav_path):
    data = open(wav_path, "rb").read()
    req = urllib.request.Request(BRAIN + "/talk", data, {"Content-Type": "audio/wav", "X-Toy-Id": TOY_ID})
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
        reply_wav = r.read()
        h = {k: urllib.parse.unquote(r.headers.get(k, "")) for k in ("X-Heard", "X-Reply", "X-Total-Ms", "X-Lang")}
    out = os.path.join(TMP, "reply.wav")
    open(out, "wb").write(reply_wav)
    return out, h


def fetch_filler(lang, kind):
    try:
        with urllib.request.urlopen(f"{BRAIN}/filler?lang={lang}&kind={kind}", timeout=3) as r:
            if r.status != 200:
                return None
            path = os.path.join(TMP, f"filler-{kind}.wav")
            open(path, "wb").write(r.read())
            return path
    except Exception:
        return None


def start_fillers(lang):
    """Play a 'thinking' line now and another every FILLER_EVERY s until stop.set().
    Returns (stop_event, thread); join the thread before playing the answer so clips never overlap."""
    stop = threading.Event()

    def run():
        kind = "start"
        while not stop.is_set():
            path = fetch_filler(lang, kind)
            if path and not stop.is_set():
                play(path)
            kind = "wait"
            if stop.wait(FILLER_EVERY):
                return

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return stop, t


def converse(wav_path):
    """Send one recording and play the answer. Never raises."""
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) < MIN_BYTES:
        state["status"] = "ready"
        return
    state["status"] = "thinking"
    t0 = time.time()
    cancel.clear()
    if button:
        button.when_pressed = stop_everything   # a press now means "stop"; keep holding to talk again
    stop, fillers = start_fillers(state["lang"])
    try:
        result = {}

        def fetch():
            try:
                result["ok"] = ask_brain(wav_path)
            except Exception as e:
                result["err"] = e
        worker = threading.Thread(target=fetch, daemon=True)
        worker.start()
        while worker.is_alive() and not cancel.is_set():
            worker.join(0.1)
        stop.set()
        if cancel.is_set():               # child pressed the button / parent tapped Stop
            state.update(reply="(stopped)")
            return
        if "err" in result:
            raise result["err"]
        reply_path, h = result["ok"]
        fillers.join(timeout=15)  # let the current thinking line finish
        state.update(heard=h["X-Heard"], reply=h["X-Reply"], brain_ok=True, lang=h["X-Lang"] or state["lang"],
                     last_ms=int((time.time() - t0) * 1000), talks=state["talks"] + 1)
        state["status"] = "speaking"
        play(reply_path)
    except Exception as e:
        stop.set()
        fillers.join(timeout=15)
        print("brain unreachable:", e, flush=True)
        state.update(brain_ok=False, reply="(brain offline: played sleepy clip)")
        state["status"] = "speaking"
        if os.path.exists(SLEEPY):
            play(SLEEPY)
    finally:
        if button:
            button.when_pressed = None
        state["status"] = "ready"


def button_loop():
    path = os.path.join(TMP, "heard.wav")
    while True:
        button.wait_for_press()
        if not busy.acquire(blocking=False):
            continue
        try:
            state["status"] = "listening"
            light(True)
            proc = record_start(path)
            button.wait_for_release(timeout=MAX_SECONDS)
            time.sleep(0.25)  # keep the tail of the last word
            proc.send_signal(signal.SIGINT)  # arecord closes the WAV header cleanly on SIGINT
            proc.wait(timeout=3)
            light(False)
            converse(path)
        finally:
            light(False)
            busy.release()


def web_talk(seconds=5):
    if not busy.acquire(blocking=False):
        return False

    def run():
        try:
            path = os.path.join(TMP, "web.wav")
            state["status"] = "listening"
            light(True)
            record_start(path, seconds).wait()
            light(False)
            converse(path)
        finally:
            light(False)
            busy.release()

    threading.Thread(target=run, daemon=True).start()
    return True


def set_volume(pct):
    pct = max(0, min(100, int(pct)))
    for control in ("PCM", "Speaker", "Master", "Headphone"):
        if subprocess.run(["amixer", "-q", "sset", control, f"{pct}%"], capture_output=True).returncode == 0:
            return control
    return None


PAGE = open(os.path.join(HERE, "page.html")).read()


class Web(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/state":
            self._send(200, json.dumps({**state, "brain": BRAIN, "toy": TOY_ID}))
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path == "/stop":
            stop_everything()
            self._send(200, '{"ok": true}')
        elif self.path == "/talk":
            ok = web_talk()
            self._send(200 if ok else 409, json.dumps({"ok": ok, "error": None if ok else "toy is busy"}))
        elif self.path.startswith("/volume"):
            pct = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("pct", ["70"])[0]
            control = set_volume(pct)
            self._send(200, json.dumps({"ok": bool(control), "control": control}))
        else:
            self._send(404, '{"error":"not found"}')

    def log_message(self, *a):
        pass


def check_brain():
    while True:
        try:
            with urllib.request.urlopen(BRAIN + "/health", timeout=4) as r:
                state["brain_ok"] = bool(json.load(r).get("llm_ready"))
        except Exception:
            state["brain_ok"] = False
        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=check_brain, daemon=True).start()
    if button:
        threading.Thread(target=button_loop, daemon=True).start()
    state["status"] = "ready"
    print(f"talktoy up: brain={BRAIN} web=:{WEB_PORT} button=GPIO{BUTTON_PIN}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", WEB_PORT), Web).serve_forever()
