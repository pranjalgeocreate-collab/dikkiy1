# Written by the web tool (Dikkey dashboard -> Toy board -> Set up). Example only.
WIFI_SSID = "MyHomeWifi"          # 2.4 GHz network
WIFI_PASS = "********"
BRAIN = "http://192.168.1.50:8700" # the Mac running Dikkey
TOY_ID = "dikkey-toy"
LANG = ""                          # "" = Dikkey works out the language; or "en", "hi", "as", "mr"
MIC = {"sck": 5, "ws": 6, "sd": 7}       # INMP441: SCK, WS, SD  (L/R -> GND, VDD -> 3V3)
AMP = {"sck": 15, "ws": 16, "sd": 17}    # MAX98357A: BCLK, LRC, DIN (VIN -> 5V)
BUTTON = 0                         # BOOT button
LED = 48                           # on-board RGB LED: GPIO48 (DevKitC-1 v1.0) or GPIO38 (v1.1)
VOLUME_DOWN = 1                    # 0 = loudest; each step halves the loudness
MIC_SHIFT = 14                     # 16 = quieter mic, 13 = louder
