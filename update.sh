#!/bin/sh
set -e

INSTALL_DIR=/home/pi/atxled/hue

echo 'Grabbing updates...'
git pull
rm -rf $INSTALL_DIR
mkdir $INSTALL_DIR
unzip bundle.zip -d $INSTALL_DIR
python3 $INSTALL_DIR/ops/install.py
