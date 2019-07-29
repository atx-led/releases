#!/bin/sh
set -e

INSTALL_DIR=/home/pi/atxled/hue

echo 'Grabbing updates...'
# Ignore all local changes, oh what fun!
git reset --hard
git fetch
git checkout origin/master
rm -rf $INSTALL_DIR
mkdir $INSTALL_DIR
unzip bundle.zip -d $INSTALL_DIR
python3 $INSTALL_DIR/ops/install.py
