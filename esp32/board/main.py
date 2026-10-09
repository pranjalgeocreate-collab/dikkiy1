# Runs when the board powers on. The web tool writes config.py (wifi + brain address) first.
try:
    import config  # noqa: F401
except ImportError:
    print("[dikkey] not set up yet: open Dikkey's dashboard on the Mac -> Toy board -> Set up")
else:
    import dikkey
    dikkey.run()
