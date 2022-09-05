#!/bin/sh
set -e
BASE=`dirname $0`/../..
echo $BASE
cd $BASE

. venv/diy-hue/bin/activate

MAC=`cat /sys/class/net/wlan0/address`
echo $MAC

#cd loader
cd hue/diy-hue/BridgeEmulator
python HueEmulator3.py --scan-on-host-ip --http-port 5500 --debug --no-link-button --no-serve-https --config-dir /home/pi/atxled/user-data --mac "$MAC"
