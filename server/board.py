"""Toy board tools for the dashboard's "Toy board" tab: set up an ESP32-S3 plugged into this Mac by USB.

The browser asks; this server runs the tested command-line tools from ~/talktoy/esp32/.venv
(esptool to install MicroPython, mpremote to copy Dikkey's toy code and run tests, pyserial for the log).
Only requests from this Mac itself are accepted: nobody else on the wifi can reprogram the toy.
The wifi password goes straight onto the board; it is never written to a log or kept on the Mac."""
import json, os, re, socket, subprocess, tempfile, threading, time

from flask import Blueprint, jsonify, request

HERE = os.path.dirname(os.path.abspath(__file__))
ESP = os.path.join(os.path.dirname(HERE), "esp32")
BIN = os.path.join(ESP, ".venv", "bin")
BOARD_CODE = os.path.join(ESP, "board")
FIRMWARE_DIR = os.path.join(ESP, "firmware")

bp = Blueprint("board", __name__)
_job = {"name": "", "lines": [], "running": False, "ok": None, "started": 0}
_lock = threading.Lock()


@bp.before_request
def only_this_mac():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(error="the toy board tools only work on the Mac itself (open http://localhost:8700)"), 403


def firmware():
    files = sorted(f for f in os.listdir(FIRMWARE_DIR) if f.endswith(".bin")) if os.path.isdir(FIRMWARE_DIR) else []
    return os.path.join(FIRMWARE_DIR, files[-1]) if files else None


def lan_ip():
    """This Mac's address on the home wifi: what the toy uses to reach the brain."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def ports():
    code = ("import json;from serial.tools import list_ports;"
            "print(json.dumps([dict(port=p.device,desc=p.description,vid=p.vid,pid=p.pid) for p in list_ports.comports()]))")
    out = subprocess.run([os.path.join(BIN, "python"), "-c", code], capture_output=True, text=True, timeout=20)
    found = json.loads(out.stdout or "[]")
    for p in found:   # Espressif's own USB (303A), or the usual USB-serial chips on DevKitC boards
        p["esp"] = p["vid"] in (0x303A, 0x10C4, 0x1A86, 0x0403) or "usbmodem" in p["port"] or "usbserial" in p["port"]
    return [p for p in found if "Bluetooth" not in p["port"] and "debug-console" not in p["port"]]


def _say(line):
    with _lock:
        _job["lines"].append(line)
        del _job["lines"][:-400]


def _run_steps(name, steps, secret=None):
    """Run commands one after another in the background; the page polls /api/board/job for the output."""
    def go():
        ok = True
        try:
            for title, cmd in steps:
                _say("▶ " + title)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ESP)
                buf = b""
                while True:
                    ch = p.stdout.read(1)
                    if not ch:
                        break
                    if ch in b"\r\n":
                        line = buf.decode(errors="replace").strip()
                        if line and (not secret or secret not in line):
                            _say("  " + line)
                        buf = b""
                    else:
                        buf += ch
                if p.wait() != 0:
                    ok = False
                    _say("✖ failed: " + title)
                    break
        except Exception as e:
            ok = False
            _say("✖ " + str(e))
        finally:
            with _lock:
                _job["running"], _job["ok"] = False, ok
            _say("✔ done" if ok else "✖ stopped")
    with _lock:
        if _job["running"]:
            return False
        _job.update(name=name, lines=[], running=True, ok=None, started=time.time())
    threading.Thread(target=go, daemon=True).start()
    return True


def _port():
    port = str((request.get_json(silent=True) or {}).get("port", ""))
    return port if port.startswith("/dev/") and port in [p["port"] for p in ports()] else None


def _mp(port, *args):
    return [os.path.join(BIN, "mpremote"), "connect", port, *args]


def virtual_running():
    """Is the virtual board (esp32/virtual_board.py, the toy code on the Mac's mic/speaker) running?"""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8710/state", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


@bp.get("/api/board/status")
def status():
    fw = firmware()
    return jsonify(ports=ports(), brain="http://%s:8700" % lan_ip(), firmware=os.path.basename(fw) if fw else None,
                   tools=os.path.exists(os.path.join(BIN, "mpremote")), virtual=virtual_running())


@bp.get("/api/board/job")
def job():
    with _lock:
        return jsonify(name=_job["name"], running=_job["running"], ok=_job["ok"], lines=_job["lines"][-200:])


@bp.post("/api/board/install")
def install():
    """Step 1, once per board: erase it and put MicroPython on it."""
    port, fw = _port(), firmware()
    if not port:
        return jsonify(error="pick the board's USB port first"), 400
    if not fw:
        return jsonify(error="MicroPython file missing in esp32/firmware"), 500
    esptool = os.path.join(BIN, "esptool")
    ok = _run_steps("Install MicroPython", [
        ("erase the board", [esptool, "--chip", "esp32s3", "--port", port, "erase-flash"]),
        ("write MicroPython (%s)" % os.path.basename(fw), [esptool, "--chip", "esp32s3", "--port", port, "--baud", "460800",
                                                           "write-flash", "0", fw]),
    ])
    return jsonify(ok=ok) if ok else (jsonify(error="another job is still running"), 409)


@bp.post("/api/board/setup")
def setup():
    """Step 2: write config.py (wifi + brain address) and Dikkey's toy code, then restart the board."""
    body = request.get_json(silent=True) or {}
    port = _port()
    ssid, password = str(body.get("ssid", "")).strip(), str(body.get("password", ""))
    brain = str(body.get("brain", "")).strip().rstrip("/") or "http://%s:8700" % lan_ip()
    lang = str(body.get("lang", ""))
    led = int(body.get("led", 48)) if str(body.get("led", "48")).isdigit() else 48
    button = int(body.get("button", 0)) if str(body.get("button", "0")).isdigit() else 0
    if not port:
        return jsonify(error="pick the board's USB port first"), 400
    if not ssid:
        return jsonify(error="type the wifi name"), 400
    if not re.fullmatch(r"https?://[\w.\-]+(:\d+)?", brain):
        return jsonify(error="the brain address should look like http://192.168.1.50:8700"), 400
    if lang not in ("", "en", "hi", "as", "mr") or led not in (38, 48) or button not in (0, 4):
        return jsonify(error="bad language, LED pin or button pin"), 400
    cfg = "\n".join([
        "# Written by Dikkey's dashboard (Toy board -> Set up).",
        "WIFI_SSID = %r" % ssid, "WIFI_PASS = %r" % password, "BRAIN = %r" % brain,
        "TOY_ID = %r" % "dikkey-toy", "LANG = %r" % lang,
        'MIC = {"sck": 5, "ws": 6, "sd": 7}', 'AMP = {"sck": 15, "ws": 16, "sd": 17}',
        "BUTTON = %d" % button, "LED = %d" % led, "VOLUME_DOWN = 1", "MIC_SHIFT = 14", ""])
    tmp = tempfile.NamedTemporaryFile("w", suffix="_config.py", delete=False)
    tmp.write(cfg)
    tmp.close()

    def cleanup_later():          # the password file only lives until the copy is done
        for _ in range(600):
            time.sleep(1)
            with _lock:
                if not _job["running"]:
                    break
        try:
            os.remove(tmp.name)
        except OSError:
            pass
    ok = _run_steps("Set up Dikkey", [
        ("copy the settings and Dikkey's toy code", _mp(port, "cp", tmp.name, ":config.py", "+",
                                                      "cp", os.path.join(BOARD_CODE, "dikkey.py"), ":dikkey.py", "+",
                                                      "cp", os.path.join(BOARD_CODE, "main.py"), ":main.py")),
        ("restart the board", _mp(port, "reset")),
    ], secret=password or None)
    if not ok:
        os.remove(tmp.name)
        return jsonify(error="another job is still running"), 409
    threading.Thread(target=cleanup_later, daemon=True).start()
    return jsonify(ok=True, brain=brain)


TESTS = {"info": "import dikkey; dikkey.info()", "beep": "import dikkey; dikkey.beep()",
         "mic": "import dikkey; dikkey.mic_test()", "led": "import dikkey; dikkey.led_test()"}


@bp.post("/api/board/test")
def test():
    """Speaker beep, mic level, LED colours, info - or restart the toy (back to "hold BOOT to talk")."""
    what = (request.get_json(silent=True) or {}).get("what")
    port = _port()
    if not port:
        return jsonify(error="pick the board's USB port first"), 400
    if what == "restart":
        steps = [("restart the toy", _mp(port, "reset"))]
    elif what in TESTS:
        steps = [("test: " + what, _mp(port, "exec", TESTS[what]))]
    else:
        return jsonify(error="unknown test"), 400
    ok = _run_steps("Test " + what, steps)
    return jsonify(ok=ok) if ok else (jsonify(error="another job is still running"), 409)


@bp.post("/api/board/listen")
def listen():
    """Show what the running toy prints (its log) for 20 seconds, without restarting it."""
    port = _port()
    if not port:
        return jsonify(error="pick the board's USB port first"), 400
    code = ("import serial,time,sys\n"
            "s=serial.Serial();s.port=sys.argv[1];s.baudrate=115200;s.timeout=0.2;s.dtr=False;s.rts=False;s.open()\n"
            "end=time.time()+20\n"
            "while time.time()<end:\n"
            "  b=s.read(256)\n"
            "  if b: sys.stdout.write(b.decode(errors='replace'));sys.stdout.flush()\n")
    ok = _run_steps("Toy log (20 s)", [("listening to the toy for 20 seconds", [os.path.join(BIN, "python"), "-c", code, port])])
    return jsonify(ok=ok) if ok else (jsonify(error="another job is still running"), 409)


# ---------------------------------------------------------------- the virtual board, for the live diagram
def _virtual(path, method="GET"):
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8710" + path, data=b"" if method == "POST" else None, method=method)
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read() or b"{}")


@bp.get("/api/board/virtual/state")
def virtual_state():
    """The virtual board's LED colour and button state (the diagram follows it while you talk)."""
    try:
        st = _virtual("/state")
        return jsonify(running=True, led=st.get("led"), pressed=st.get("pressed"), log=st.get("log", [])[-3:])
    except Exception:
        return jsonify(running=False)


@bp.post("/api/board/virtual/<action>")
def virtual_button(action):
    """The dashboard's "Hold to talk" button = the virtual board's BOOT button."""
    if action not in ("press", "release"):
        return jsonify(error="press or release"), 400
    try:
        _virtual("/" + action, "POST")
        return jsonify(ok=True)
    except Exception:
        return jsonify(error="the virtual board is not running"), 503


VBOARD = os.path.join(ESP, "virtual_board.py")
VBOARD_PID = os.path.join(ESP, "virtual_board.pid")


@bp.post("/api/board/virtual/power")
def virtual_power():
    """The dashboard's ON/OFF switch: start or stop the virtual board (like the toy's power switch)."""
    on = bool((request.get_json(silent=True) or {}).get("on"))
    running = virtual_running()
    if on and not running:
        log = open(os.path.join(ESP, "virtual_board.log"), "ab")
        p = subprocess.Popen([os.path.join(BIN, "python"), "-u", VBOARD], cwd=ESP, stdout=log, stderr=log,
                             start_new_session=True)
        open(VBOARD_PID, "w").write(str(p.pid))
        for _ in range(40):                       # wait until it answers (mic check takes a moment)
            time.sleep(0.25)
            if virtual_running():
                break
    elif not on and running:
        try:
            pid = int(open(VBOARD_PID).read().strip())
            os.kill(pid, 15)
        except (OSError, ValueError):
            # started some other way: find whoever holds its port
            out = subprocess.run(["lsof", "-nP", "-iTCP:8710", "-sTCP:LISTEN", "-t"], capture_output=True, text=True)
            for pid in out.stdout.split():
                os.kill(int(pid), 15)
        for _ in range(20):
            time.sleep(0.25)
            if not virtual_running():
                break
    return jsonify(on=virtual_running())
