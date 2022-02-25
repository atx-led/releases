#!/usr/bin/env python3
import sys
import os

print('Loading for version %s' % (sys.version.split()[0]))
if sys.version.startswith('3.9'):
    os.system('./load-3.9.bin')
else:
    os.system('./load.bin')
