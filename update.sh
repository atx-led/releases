#!/bin/sh
set -e
# cd to .. so we can replace releases/
BASE=`dirname $0`/..
cd $BASE

sudo python3 $BASE/releases/expand.py

INSTALL_DIR=/home/pi/atxled/hue

BRANCH='master'
[ -f branch ] && BRANCH=`cat branch`

URL="https://github.com/atx-led/releases/archive/$BRANCH.zip"

echo "Grabbing latest code from $URL..."

# Grab code and replace
curl --fail -o releases.zip --location $URL
rm -rf new-releases
unzip -j releases.zip -d new-releases

# Check if the BRANCH is 'prod'
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "test" ] || [ "$BRANCH" = "beta" ]; then
    if [ -f new-releases/tag ] && [ -f releases/tag ]; then
        NEW_TAG=`cat new-releases/tag`
        OLD_TAG=`cat releases/tag`
        
        # Extract the numeric component from the front of the tags
        NEW_TAG_NUM=${NEW_TAG%%-*}
        OLD_TAG_NUM=${OLD_TAG%%-*}
        
        # Compare the numeric components
        if [ "$NEW_TAG_NUM" -lt "$OLD_TAG_NUM" ]; then
            rm -rf new-releases
            echo "New release has an older tag. Exiting."
            exit 1
        fi
    fi
fi

rm -rf releases
mv new-releases releases

cd releases

rm -rf $INSTALL_DIR
mkdir $INSTALL_DIR
unzip bundle.zip -d $INSTALL_DIR
sudo python3 $INSTALL_DIR/ops/install.py
