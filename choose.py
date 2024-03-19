#!/home/pi/atxled/venv/zpds/bin/python
import sys
import os

print('Loading for version %s' % (sys.version.split()[0]))
if sys.version.startswith('3.9'):
    os.system('./load-3.9.bin')
elif sys.version.startswith('3.11'):
    os.system('./load-3.11.bin')
else:
    os.system('./load.bin')
