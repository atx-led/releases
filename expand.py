#!/usr/bin/python3
import subprocess as sp

def run(args, shell=True, check=0, stdout=sp.PIPE, stderr=sp.PIPE, **kwargs):
    print(args)
    proc = sp.run(args, shell=shell, check=check, stdout=stdout,
            stderr=stderr, **kwargs)
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr)
        assert 0
    return proc

def get_mac_address():
    with open('/sys/class/net/wlan0/address') as f:
        return f.read().strip().replace(':', '')

def expand_fs():
    mac = get_mac_address()
    # Yuck, blacklist MACs of machines for creating images
    if mac in ('b827eba2df99', 'dca632d0364d'):
        print('This is an imaging machine, not expanding')
        return

    proc = run('raspi-config nonint get_can_expand')
    if proc.stdout != b'0\n':
        print('get_can_expand returned false, not expanding')
        return

    # Annoying!! Check if the last partition extends to the last sector,
    # which the raspi-config "get_can_expand" function inexplicably doesn't do
    proc = run('parted /dev/mmcblk0 -ms unit s p')
    lines = proc.stdout.decode('utf-8').splitlines()
    assert lines[1].startswith('/dev/mmcblk0')
    total = lines[1].split(':')[1]
    last = lines[-1].split(':')[2]
    assert total.endswith('s') and last.endswith('s')
    print(int(last[:-1]), int(total[:-1]) - 1)
    if int(last[:-1]) >= int(total[:-1]) - 1:
        print('Disk already expanded, not expanding')
        return

    run('raspi-config nonint do_expand_rootfs')

    run('reboot')

if __name__ == '__main__':
    expand_fs()
