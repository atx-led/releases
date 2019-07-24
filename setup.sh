set -e

echo 'Installing auto-updater...'

UNIT='atx-led-updater.service'
sudo cp ${UNIT} /lib/systemd/system/
sudo chmod 644 /lib/systemd/system/${UNIT}
sudo systemctl daemon-reload
sudo systemctl enable ${UNIT}
sudo systemctl start ${UNIT}
