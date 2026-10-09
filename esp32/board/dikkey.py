"""Dikkey toy firmware for an ESP32-S3 board (MicroPython 1.29, SPIRAM build).

Hold BOOT, talk, let go. The recording goes to Dikkey's brain on the Mac (POST /talk); while the brain
thinks, a short "Hmm, let me think!" plays; then the reply plays on the speaker.
Hardware (see config.py): INMP441 mic on I2S0, MAX98357A amp + speaker on I2S1, BOOT button, RGB LED.
The LED shows: blue = ready, green = listening, orange = thinking, purple = talking, red = problem.
Everything is 16 kHz mono 16-bit: the server converts replies to that (header X-Want-Rate)."""
import gc, select, socket, struct, time

import micropython
import network
from machine import I2S, Pin

import config

try:
    import neopixel
except ImportError:
    neopixel = None

RATE = 16000
MAX_SECONDS = 15
MIN_BYTES = RATE * 2 * 4 // 10                  # under 0.4 s = an accidental tap
WAIT_FILLER_MS = 8000                          # "still thinking" every 8 s while the brain works
COLORS = {"idle": (0, 0, 6), "listen": (0, 40, 0), "think": (40, 18, 0), "talk": (24, 0, 40),
          "error": (40, 0, 0), "off": (0, 0, 0)}

_np = None
_pcm = None                                    # one recording buffer, allocated once (PSRAM)
_last_lang = getattr(config, "LANG", "") or "en"


def log(*a):
    print("[dikkey]", *a)


def led(state):
    global _np
    if neopixel is None:
        return
    try:
        if _np is None:
            _np = neopixel.NeoPixel(Pin(config.LED, Pin.OUT), 1)
        _np[0] = COLORS.get(state, (0, 0, 0))
        _np.write()
    except Exception:
        pass


def button():
    return Pin(config.BUTTON, Pin.IN, Pin.PULL_UP)   # BOOT: 0 while pressed


def wifi(timeout_s=25):
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if w.isconnected():
        return w
    log("connecting to wifi", config.WIFI_SSID)
    w.connect(config.WIFI_SSID, config.WIFI_PASS)
    t0 = time.ticks_ms()
    while not w.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
            raise OSError("wifi did not connect: check the name/password, and use 2.4 GHz wifi")
        time.sleep_ms(250)
    log("wifi ok, my address", w.ifconfig()[0])
    return w


# ------------------------------------------------------------------ microphone
@micropython.viper
def _to16(src: ptr32, dst: ptr16, n: int, shift: int):
    """INMP441 gives 24-bit samples in 32-bit slots; keep the top 16 bits (with a little gain)."""
    i = 0
    while i < n:
        v = int(src[i]) >> shift
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        dst[i] = v
        i += 1


def record(max_s=MAX_SECONDS, until_release=True):
    """Record while BOOT is held (or for max_s seconds). Returns (buffer, number of bytes)."""
    global _pcm
    if _pcm is None:
        _pcm = bytearray(RATE * 2 * MAX_SECONDS)
    m = config.MIC
    mic = I2S(0, sck=Pin(m["sck"]), ws=Pin(m["ws"]), sd=Pin(m["sd"]), mode=I2S.RX, bits=32,
              format=I2S.MONO, rate=RATE, ibuf=32000)
    raw = bytearray(4096)                      # 1024 samples of 32 bits
    out = memoryview(_pcm)
    limit = min(RATE * max_s, len(_pcm) // 2)
    shift = getattr(config, "MIC_SHIFT", 14)
    btn = button()
    try:
        for _ in range(3):                     # the mic needs ~100 ms to settle
            mic.readinto(raw)
        got = 0
        while got < limit:
            n = mic.readinto(raw) // 4
            n = min(n, limit - got)
            _to16(raw, out[got * 2:], n, shift)
            got += n
            if until_release and btn.value():
                break
    finally:
        mic.deinit()
    return _pcm, got * 2


def wav_header(nbytes, rate=RATE):
    return (b"RIFF" + struct.pack("<I", 36 + nbytes) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", nbytes))


# ------------------------------------------------------------------ talking to the brain (plain HTTP)
def _where():
    url = config.BRAIN.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = url.partition(":")
    return host, int(port or 80)


def _open(method, path, body=(), length=0):
    host, port = _where()
    s = socket.socket()
    s.settimeout(330)                          # a long story can take minutes on the Mac
    s.connect(socket.getaddrinfo(host, port)[0][-1])
    head = "%s %s HTTP/1.0\r\nHost: %s\r\nX-Toy-Id: %s\r\nX-Want-Rate: %d\r\n" % (method, path, host, config.TOY_ID, RATE)
    if getattr(config, "LANG", ""):
        head += "X-Lang: %s\r\n" % config.LANG
    if method == "POST":
        head += "Content-Type: audio/wav\r\nContent-Length: %d\r\n" % length
    s.write((head + "\r\n").encode())
    for part in body:
        s.write(part)
    return s


def _headers(s):
    status = s.readline()
    code = int(status.split()[1]) if status else 0
    h = {}
    while True:
        line = s.readline()
        if not line or line == b"\r\n":
            break
        k, _, v = line.decode().partition(":")
        h[k.strip().lower()] = v.strip()
    return code, h


def _unquote(t):
    """The server sends header text URL-encoded (%E0%A4...); turn it back into readable text."""
    out, i = bytearray(), 0
    b = t.encode()
    while i < len(b):
        if b[i] == 37 and i + 3 <= len(b):    # %XX
            try:
                out.append(int(b[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(b[i])
        i += 1
    return out.decode()


def _fill(s, mv):
    """Read until mv is full (or the reply ends). Returns bytes read."""
    got = 0
    while got < len(mv):
        n = s.readinto(mv[got:])
        if not n:
            break
        got += n
    return got


def _skip(s, n):
    tmp = bytearray(min(n, 512))
    while n > 0:
        k = _fill(s, memoryview(tmp)[:min(n, len(tmp))])
        if not k:
            return
        n -= k


def play_stream(s, stoppable=True):
    """Download the whole reply first, then play it in one smooth pass. Interleaving network reads with
    audio writes (the old approach) lets any stall on the Mac's side show up as a click or crackle in the
    speaker output; downloading to memory first means nothing but this loop's own writes can affect the
    sound once playback starts. Pressing BOOT stops it."""
    head = bytearray(12)
    if _fill(s, memoryview(head)) < 12 or head[:4] != b"RIFF":
        log("reply is not audio")
        return
    rate, size = RATE, 0
    ch = bytearray(8)
    while True:                                # walk the chunks to "data"
        if _fill(s, memoryview(ch)) < 8:
            return
        cid, n = bytes(ch[:4]), struct.unpack("<I", ch[4:])[0]
        if cid == b"fmt ":
            fmt = bytearray(n)
            _fill(s, memoryview(fmt))
            rate = struct.unpack("<I", fmt[4:8])[0]
        elif cid == b"data":
            size = n
            break
        else:
            _skip(s, n + (n & 1))
    pcm = bytearray(size)
    got = _fill(s, memoryview(pcm))
    if got < size:                             # the reply was cut short: play only what arrived
        pcm = pcm[: got - (got & 1)]
    mv = memoryview(pcm)
    vol = getattr(config, "VOLUME_DOWN", 1)    # each step halves the loudness (protects a small battery)
    if vol and len(pcm):
        I2S.shift(buf=mv, bits=16, shift=-vol)
    a = config.AMP
    amp = I2S(1, sck=Pin(a["sck"]), ws=Pin(a["ws"]), sd=Pin(a["sd"]), mode=I2S.TX, bits=16,
              format=I2S.MONO, rate=rate, ibuf=40000)
    btn = button()
    released = btn.value() == 1
    try:
        pos, left, chunk = 0, len(pcm), 4096
        while left > 0:
            k = min(chunk, left)
            amp.write(mv[pos:pos + k])
            pos += k; left -= k
            if stoppable:
                if btn.value():
                    released = True
                elif released:                 # pressed again while talking: stop
                    log("stopped by the button")
                    break
        amp.write(bytearray(3200))             # 0.1 s of silence so the last word isn't cut
    finally:
        amp.deinit()


def filler(lang, kind):
    """A short ready-made "Hmm, let me think!" (the server answers 204 if none is recorded)."""
    try:
        s = _open("GET", "/filler?lang=%s&kind=%s" % (lang, kind))
        try:
            code, _ = _headers(s)
            if code == 200:
                play_stream(s, stoppable=False)
        finally:
            s.close()
    except Exception as e:
        log("filler skipped:", e)


def talk(pcm, nbytes):
    global _last_lang
    led("think")
    s = _open("POST", "/talk", (wav_header(nbytes), memoryview(pcm)[:nbytes]), 44 + nbytes)
    try:
        filler(_last_lang, "start")
        p = select.poll()
        p.register(s, select.POLLIN)
        while not p.poll(WAIT_FILLER_MS):      # still thinking
            filler(_last_lang, "wait")
        code, h = _headers(s)
        if code != 200:
            log("brain answered", code)
            led("error")
            time.sleep(1)
            return
        _last_lang = h.get("x-lang", _last_lang) or _last_lang
        log("heard:", _unquote(h.get("x-heard", "")), "| status:", _unquote(h.get("x-status", "")))
        led("talk")
        play_stream(s)
    finally:
        s.close()


def run():
    led("idle")
    while True:
        try:
            wifi()
            break
        except Exception as e:
            log(e)
            led("error")
            time.sleep(5)
    btn = button()
    log("ready: hold BOOT and talk, let go to send. Brain:", config.BRAIN)
    while True:
        led("idle")
        while btn.value():
            time.sleep_ms(20)
        led("listen")
        pcm, n = record()
        if n < MIN_BYTES:
            log("too short, ignored")
            continue
        try:
            wifi()
            talk(pcm, n)
        except Exception as e:
            log("could not reach Dikkey's brain:", e)
            led("error")
            time.sleep(2)
        gc.collect()


# ------------------------------------------------------------------ tests (run from the web tool)
def info():
    w = network.WLAN(network.STA_IF)
    gc.collect()
    print("wifi:", "connected " + w.ifconfig()[0] if w.isconnected() else "not connected",
          "| network:", config.WIFI_SSID, "| brain:", config.BRAIN, "| toy id:", config.TOY_ID,
          "| free memory: %d KB" % (gc.mem_free() // 1024))


def led_test():
    for state in ("idle", "listen", "think", "talk", "error", "off"):
        print("LED", state)
        led(state)
        time.sleep_ms(700)


def beep(hz=440, seconds=0.6):
    """A tone on the speaker: proves the amp and speaker wiring."""
    import math
    period = RATE // hz
    one = bytearray(period * 2)
    for i in range(period):
        struct.pack_into("<h", one, i * 2, int(8000 * math.sin(2 * math.pi * i / period)))
    a = config.AMP
    amp = I2S(1, sck=Pin(a["sck"]), ws=Pin(a["ws"]), sd=Pin(a["sd"]), mode=I2S.TX, bits=16,
              format=I2S.MONO, rate=RATE, ibuf=8000)
    try:
        for _ in range(int(seconds * hz)):
            amp.write(one)
        amp.write(bytearray(3200))
    finally:
        amp.deinit()
    print("beep done: did you hear it?")


def mic_test(seconds=3):
    """Records a few seconds and prints how loud it was: proves the mic wiring."""
    print("recording %d s: talk now..." % seconds)
    pcm, n = record(max_s=seconds, until_release=False)
    peak = total = 0
    for i in range(0, n, 2):
        v = abs(struct.unpack_from("<h", pcm, i)[0])
        peak = max(peak, v)
        total += v
    avg = total // max(1, n // 2)
    verdict = ("no sound at all: check the mic wires (SD, SCK, WS, 3V3, GND, L/R to GND)" if peak < 50 else
               "very quiet: talk closer, or raise MIC gain" if peak < 1500 else "mic works")
    print("peak %d, average %d -> %s" % (peak, avg, verdict))
