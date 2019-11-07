#!/bin/sh
set -e
# cd to .. so we can replace releases/
BASE=`dirname $0`/..
cd $BASE

INSTALL_DIR=/home/pi/atxled/hue

BRANCH='master'
[ -f branch ] && BRANCH=`cat branch`

URL="https://github.com/atx-led/releases/archive/$BRANCH.zip"

echo "Grabbing latest code from $URL..."

# Grab code and replace
curl --fail -o releases.zip --location $URL
rm -rf new-releases
unzip -j releases.zip -d new-releases
rm -rf releases
mv new-releases releases

cd releases

rm -rf $INSTALL_DIR
mkdir $INSTALL_DIR
unzip bundle.zip -d $INSTALL_DIR
sudo python3 $INSTALL_DIR/ops/install.py
