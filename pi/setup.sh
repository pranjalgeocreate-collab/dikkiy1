#!/bin/sh
# Run ON THE PI, from the folder you copied (e.g. /home/pi/talktoy):  sh setup.sh
set -e
sudo apt-get update
sudo apt-get install -y alsa-utils python3-gpiozero

# Compact I2S build (INMP441 mic + MAX98357A amp) only: enable the sound overlay.
if [ "$1" = "i2s" ]; then
  CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
  grep -q googlevoicehat "$CFG" || echo "dtoverlay=googlevoicehat-soundcard" | sudo tee -a "$CFG"
  sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CFG"
  echo "I2S overlay added; reboot, then run setup.sh again without 'i2s'."
  exit 0
fi

echo "--- microphones"; arecord -l || true
echo "--- speakers";    aplay -l || true

sudo cp talktoy.service /etc/systemd/system/talktoy.service
sudo sed -i "s#/home/pi/talktoy#$(pwd)#g; s#User=pi#User=$(whoami)#" /etc/systemd/system/talktoy.service
sudo systemctl daemon-reload
sudo systemctl enable --now talktoy
echo "talktoy running. Web page: http://$(hostname -I | cut -d' ' -f1):8080"
