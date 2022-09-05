#!/bin/sh
set -e
. venv/zpds/bin/activate

# yuck
mv ramdisk/alembic.ini .
alembic --name alembic_ramdisk upgrade head

gunicorn --pythonpath './ramdisk' --worker-class gthread --threads 4 -w 1 \
    --timeout 180 -u pi -g pi -b 127.0.0.1:5000 'serve:create_app()' --
