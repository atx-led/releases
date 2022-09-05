#!/usr/bin/python3
import os
import subprocess as sp
import sys

NEED_REBOOT = False

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

def gen_ssl_cert(cert_path):
    # Get mac address as an int
    mac = get_mac_address()
    mac = mac[:6] + 'fffe' + mac[6:]
    mac_int = int(mac, 16)

    if os.path.exists(cert_path):
        print('Cert exists, verifying serial...')
        proc = run('openssl x509 -issuer -noout -in %s' % cert_path)
        if mac in proc.stdout.decode('utf-8'):
            print('Serial matches.')
            return
        else:
            print('Serial does not match.')
    print('Generating cert...')

    run('openssl req -new -days 3650 -config ops/openssl.conf -nodes -x509 '
            '-newkey ec -pkeyopt ec_paramgen_curve:P-256 -pkeyopt '
            'ec_param_enc:named_curve -subj "/C=NL/O=Philips Hue/CN=%s" -keyout %s '
            '-out /tmp/public.crt -set_serial %s' % (mac, cert_path, mac_int))
    run('sh -c "cat /tmp/public.crt >> %s"' % cert_path)
    run('rm /tmp/public.crt')
    run('chmod 600 %s' % cert_path)

def expand_fs():
    global NEED_REBOOT
    mac = get_mac_address()
    # Yuck, blacklist one MAC for creating images
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
    NEED_REBOOT = True

def install_log2ram():
    global NEED_REBOOT
    # XXX hardcoded path
    log2ram_path = '/usr/local/bin/log2ram'
    if os.path.exists(log2ram_path):
        run('sed -i -e "s/SIZE=.*/SIZE=128M/" /etc/log2ram.conf')
        return

    run('cd log2ram && ./install.sh')

    NEED_REBOOT = True

def install():
    global NEED_REBOOT
    # Install system packages
    PACKAGES = [
        'nginx',
        'nmap',
        'python2', # Add python2 for dataplicity and Murray's scripts
        'python3',
        'python3-requests',
        'python3-setuptools',
        'python3-venv',
        'python3-flask',
        'python3-serial',
        'sqlite3',
        'unzip',

        # On-screen keyboard
        'matchbox-keyboard',

        # Automatic security upgrades
        'unattended-upgrades',

        # For automatic wifi hotspot mode
        'dnsmasq',
        'hostapd',
    ]

    run('apt-get --allow-releaseinfo-change-suite update')

    run('apt-get install -y %s' % ' '.join(PACKAGES))

    # Make sure we can run hostapd
    run('systemctl unmask hostapd')
    run('systemctl disable hostapd dnsmasq')

    # Create virtual environments for both repos
    VENV_PATH = '../venv'
    run('sudo -u pi mkdir -p %s' % VENV_PATH)
    for proj in ['zpds', 'diy-hue']:
        if not os.path.exists('%s/%s' % (VENV_PATH, proj)):
            run('sudo -u pi python3 -m venv %s/%s' % (VENV_PATH, proj))
        run('sudo -u pi sh -c ". {0}/{1}/bin/activate; '
            'cd {1}; pip install -r requirements.txt"'.format(VENV_PATH, proj))

    # Make a directory for persistent user data
    USER_PATH = '../user-data'
    run('sudo -u pi mkdir -p %s' % USER_PATH)

    # Set up logrotate conf
    run('cp ops/logrotate.conf /etc/logrotate.conf')
    run('cp ops/logrotate.timer /lib/systemd/system/')

    # Set up services for both servers
    services = ['zpds', 'hue-emulator', 'cron-boom', 'boot-atxled']
    for service in services:
        run('cp ops/%s.service /lib/systemd/system/' % service)
        run('chmod 644 /lib/systemd/system/%s.service' % service)
    services = ' '.join('%s.service' % service for service in services)
    run('systemctl daemon-reload')
    run('systemctl enable ' + services)
    run('systemctl restart --no-block ' + services)

    # Generate a certificate
    gen_ssl_cert('/etc/nginx/cert.pem')

    # Set up NGINX config
    path_avail = '/etc/nginx/sites-available/server.conf'
    path_enabled = path_avail.replace('available', 'enabled')
    for path in ['default', 'php.conf']:
        if os.path.exists('/etc/nginx/sites-enabled/%s' % path):
            run('rm /etc/nginx/sites-enabled/%s' % path)
    run('cp ops/nginx.conf %s' % path_avail)
    if not os.path.exists(path_enabled):
        run('ln -s %s %s' % (path_avail, path_enabled))
    run('systemctl restart nginx')
    run('cp ops/502.html /var/www/html/502.html')
    run('cp ops/favicon.ico /var/www/html/favicon.ico')

    # Make sure to generate sshd keys if necessary
    if not os.path.exists('/etc/ssh/ssh_host_ed25519_key'):
        run('dpkg-reconfigure openssh-server')

    # Generate a certificate
    gen_ssl_cert('/etc/nginx/cert.pem')

    install_log2ram()

    expand_fs()

    if NEED_REBOOT:
        run('reboot')

if __name__ == '__main__':
    # Ensure we're root
    if os.getuid() != 0:
        run(['sudo', 'python3', sys.argv[0]], shell=False)
        sys.exit(0)

    BASE = '%s/..' % sys.path[0]
    os.chdir(BASE)

    install()
