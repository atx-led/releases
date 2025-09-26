#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path

print('Loading for version %s' % sys.version.split()[0])

cffi_backend_path = Path('/usr/lib/python3/dist-packages/_cffi_backend.cpython-39-arm-linux-gnueabihf.so')

def backup_cffi_backend():
    backup_path = cffi_backend_path.with_name(cffi_backend_path.name + '.backup')
    if cffi_backend_path.exists():
        print('Backing up %s to %s' % (cffi_backend_path, backup_path))
        # Use sudo to move the file (non-fatal if it fails)
        subprocess.run(['sudo', 'mv', str(cffi_backend_path), str(backup_path)], check=False)
    else:
        print('%s does not exist, no action taken.' % cffi_backend_path)

backup_cffi_backend()

here = Path(__file__).resolve().parent
load_py = here / 'load.py'
if not load_py.exists():
    print('ERROR: %s not found' % load_py)
    sys.exit(1)

cmd = [sys.executable, str(load_py), *sys.argv[1:]]
result = subprocess.run(cmd, cwd=str(here))
sys.exit(result.returncode)
