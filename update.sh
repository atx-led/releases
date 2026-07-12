#!/bin/sh
set -e
# cd to .. so we can replace releases/
BASE=`dirname $0`/..
cd $BASE

sudo python3 $BASE/releases/expand.py

INSTALL_DIR=/home/pi/atxled/hue

BRANCH='master'
[ -f branch ] && BRANCH=`cat branch`
if [ "$BRANCH" = "cleanlife" ]; then
    echo "Normalizing cleanlife branch to master."
    rm -f branch
    BRANCH='master'
fi

: "${RELEASE_REPO_URL:=https://github.com/CleanLife-IT/Releases---atxlediot}"
URL="$RELEASE_REPO_URL/archive/$BRANCH.zip"

echo "Grabbing latest code from $URL..."

rm -f releases.zip.tmp
DOWNLOAD_OK=0
for delay in 1 2 5 10 15; do
    if curl --fail -o releases.zip.tmp --location "$URL"; then
        if [ ! -s releases.zip.tmp ]; then
            echo "Download produced an empty releases.zip. Retrying in ${delay}s..."
            sleep $delay
            continue
        fi
        echo "Download succeeded."
        DOWNLOAD_OK=1
        break
    else
        echo "Download failed. Retrying in ${delay}s..."
        sleep $delay
    fi
done

if [ "$DOWNLOAD_OK" != "1" ]; then
    rm -f releases.zip.tmp
    echo "Failed to download after multiple attempts."
    exit 1
fi

mv -f releases.zip.tmp releases.zip
unzip -t releases.zip

rm -rf new-releases.tmp
mkdir new-releases.tmp
unzip -j releases.zip -d new-releases.tmp

for path in choose.py setup.sh update.sh atx-led-updater.service load.py util.py expand.py bundle.zip zpds.bin tag; do
    if [ ! -s new-releases.tmp/$path ]; then
        echo "Downloaded release is missing required file: $path"
        rm -rf new-releases.tmp
        exit 1
    fi
done

unzip -t new-releases.tmp/bundle.zip

# Prevent accidental downgrades on normal release branches.
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "test" ] || [ "$BRANCH" = "beta" ]; then
    if [ -f new-releases.tmp/tag ] && [ -f releases/tag ]; then
        NEW_TAG=`cat new-releases.tmp/tag`
        OLD_TAG=`cat releases/tag`

        # Extract the numeric component from the front of the tags
        NEW_TAG_NUM=${NEW_TAG%%-*}
        OLD_TAG_NUM=${OLD_TAG%%-*}

        # Compare the numeric components
        if [ "$NEW_TAG_NUM" -lt "$OLD_TAG_NUM" ]; then
            rm -rf new-releases.tmp
            echo "New release has an older tag. Exiting."
            exit 1
        fi
    fi
fi

rm -rf $INSTALL_DIR.new
mkdir $INSTALL_DIR.new
unzip new-releases.tmp/bundle.zip -d $INSTALL_DIR.new

for path in ops/install.py ops/cron-boom-health.service ops/cron-boom-health.timer ops/cron-boom-restart.service cron-boom/cron_boom.py sddp/sddp_wrapper.py zpds/run.sh; do
    if [ ! -s $INSTALL_DIR.new/$path ]; then
        echo "New install is missing required file: $path"
        rm -rf $INSTALL_DIR.new new-releases.tmp
        exit 1
    fi
done

# Only replace live files after the release and app bundle have both validated.
rm -rf new-releases
mv new-releases.tmp new-releases

rm -rf releases
mv new-releases releases

rm -rf $INSTALL_DIR
mv $INSTALL_DIR.new $INSTALL_DIR

cd releases

sudo python3 $INSTALL_DIR/ops/install.py
