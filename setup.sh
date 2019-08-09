#!/bin/bash
set -e

echo 'Installing auto-updater...'

UNIT='atx-led-updater.service'
sudo cp ${UNIT} /lib/systemd/system/
sudo chmod 644 /lib/systemd/system/${UNIT}
sudo systemctl daemon-reload
sudo systemctl enable ${UNIT}

SERIAL=$(raspi-config nonint get_serial_hw)

# If serial port is enabled already, start the service
if [ $SERIAL -eq 0 ]; then
    sudo systemctl start ${UNIT}
# Otherwise, enable serial and reboot
else
    # Enable serial port, but not serial console
    # The raspi-config script is kinda weird, and isn't documented much. The first arg has to be 2 and not 1
    # for some reason...
    echo 'Enabling serial port...'
    sudo raspi-config nonint do_serial 2 0

    echo ''
    echo 'To complete installation, the machine must be rebooted.'
    echo -n 'Reboot now? [y/N] ' && read resp
    if [ "$resp" = 'y' ] || [ "$resp" = 'yes' ] || [ "$resp" = 'Y' ]; then
        sudo reboot
    fi
fi
