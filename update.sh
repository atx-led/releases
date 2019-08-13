#!/bin/sh
set -e

INSTALL_DIR=/home/pi/atxled/hue

BRANCH='origin/master'
[ -f branch ] && BRANCH=`cat branch`

echo 'Grabbing updates...'
# Ignore all local changes, oh what fun!
git reset --hard
git fetch || echo 'Could not fetch!'
git checkout $BRANCH
rm -rf $INSTALL_DIR
mkdir $INSTALL_DIR
unzip bundle.zip -d $INSTALL_DIR
python3 $INSTALL_DIR/ops/install.py
