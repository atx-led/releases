#!/usr/bin/env python3
import sys
import os

# Define the path to the _cffi_backend file
cffi_backend_path = '/usr/lib/python3/dist-packages/_cffi_backend.cpython-39-arm-linux-gnueabihf.so'

print('Loading for version %s' % sys.version.split()[0])

def backup_cffi_backend():
    backup_path = cffi_backend_path + '.backup'
    if os.path.exists(cffi_backend_path):
        print('Backing up %s to %s' % (cffi_backend_path, backup_path))
        # Use sudo to move the file
        move_command = 'sudo mv ' + cffi_backend_path + ' ' + backup_path
        os.system(move_command)
    else:
        print('%s does not exist, no action taken.' % cffi_backend_path)

# Check and backup _cffi_backend if necessary
backup_cffi_backend()

# Load different binaries based on Python version
if sys.version.startswith('3.9'):
    os.system('./load-3.9.bin')
elif sys.version.startswith('3.11'):
    os.system('./load-3.11.bin')
else:
    os.system('./load.bin')