# talktoy — a talking toy on a Raspberry Pi Zero W

The Pi Zero W is too weak to run speech recognition or an LLM, so it is a
thin client: button + mic + speaker + small web page. A "brain" server on the
Mac (same Wi-Fi) does speech-to-text, the LLM, and text-to-speech.

## Flowchart

```
                        ┌──────────────────────────────────────────┐
                        │        RASPBERRY PI ZERO W  (the toy)    │
                        │                                          │
  child presses ───────►│ 1. Button held (GPIO17)                  │
  and holds button      │        │                                 │
                        │        ▼                                 │
  child speaks ────────►│ 2. Record mic → WAV (16 kHz mono)        │
                        │        │  LED on while listening         │
                        │        ▼                                 │
  child lets go ───────►│ 3. Stop recording                        │
                        │        │                                 │
                        │        ▼                                 │
                        │ 4. POST WAV to brain  ───────────────────┼──┐
                        │                                          │  │ Wi-Fi
                        │ 7. Receive reply WAV  ◄──────────────────┼──┼──┐
                        │        │                                 │  │  │
                        │        ▼                                 │  │  │
  child hears  ◄────────│ 8. Play on speaker → back to step 1      │  │  │
                        │                                          │  │  │
                        │  Web page :8080 — status, last chat,     │  │  │
  parent's phone ──────►│  volume, "talk" button                   │  │  │
                        └──────────────────────────────────────────┘  │  │
                                                                      │  │
                        ┌──────────────────────────────────────────┐  │  │
                        │        BRAIN SERVER  (Mac, :8700)        │  │  │
                        │                                          │  │  │
                        │ 5a. Speech → text   (faster-whisper)  ◄──┼──┘  │
                        │        │                                 │     │
                        │        ▼                                 │     │
                        │ 5b. Empty / noise? ── yes ─► "Say again?"│     │
                        │        │ no                              │     │
                        │        ▼                                 │     │
                        │ 5c. LLM reply  (Ollama, kid-safe persona,│     │
                        │     short answers, last 6 turns memory)  │     │
                        │        │                                 │     │
                        │        ▼                                 │     │
                        │ 6.  Text → speech  (macOS `say` → WAV) ──┼─────┘
                        │                                          │
                        │  Dashboard :8700 — every conversation    │
  parent's browser ────►│  logged (heard / replied / latency)      │
                        └──────────────────────────────────────────┘
```

Failure path: if the brain is unreachable or times out, the Pi plays a
stored "I'm sleepy, try again later" clip instead of hanging.

## Hardware

| Part | Pick | Notes |
|---|---|---|
| Board | Raspberry Pi Zero W (or Zero 2 W — 4× faster, same size) | Pi OS Lite |
| Mic + speaker, easy | USB sound card dongle + micro-USB OTG adapter | plug-and-play in ALSA |
| Mic + speaker, compact | INMP441 I2S mic + MAX98357A I2S amp | `dtoverlay=googlevoicehat-soundcard` |
| Speaker | 3 W, 4–8 Ω | |
| Button | momentary push button | GPIO17 ↔ GND |
| LED (optional) | LED + 330 Ω | GPIO27 |
| Power | 5 V 2 A USB, or LiPo + boost board for a cordless toy | |

## Layout

```
talktoy/
├── README.md
├── server/            runs on the Mac
│   ├── server.py      /talk endpoint + dashboard :8700
│   ├── persona.txt    the toy's character + kid-safety rules
│   └── requirements.txt
└── pi/                runs on the Pi Zero W
    ├── toy.py         button → record → send → play, + web page :8080
    ├── config.env     brain URL, ALSA devices, GPIO pins
    ├── sleepy.wav     offline fallback clip
    ├── setup.sh       apt installs + systemd service
    └── talktoy.service
```
