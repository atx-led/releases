#!/usr/bin/python3
import collections
import io
import json
import logging
import os
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib
import zipfile

import flask

app = flask.Flask(__name__)

os.chdir(sys.path[0])
#os.chdir('/home/pi')

NETWORK_CONFIG = None
LAST_USE_TIME = None

HOTSPOT_MODE = True
#HOTSPOT_MODE = False

USER_DATA_PATH = '/home/pi/atxled/user-data'
DB_PATH = '%s/zpds.db' % USER_DATA_PATH
STATIC_IP_PATH = '%s/static-ip.txt' % USER_DATA_PATH

# Configuration: load this from the main user database
CRON_BOOM_CONFIG = {}
def reload_config():
    global CRON_BOOM_CONFIG, DB_PATH
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT enable_backups FROM site_settings')
            row = cursor.fetchone()
            CRON_BOOM_CONFIG = {'enable_backups': row[0]}
    except Exception as e:
        logging.error('got exception loading config: %s', e)

def get_mac_address():
    # Get the mac of the wifi adapter. RPi specific-ish
    with open('/sys/class/net/wlan0/address') as f:
        return f.read().strip().replace(':', '')

# Get ip/mac addresses
def get_internet_status():
    try:
        mac = get_mac_address()

        # Kinda hacky: just use the first IP returned by hostname -I, even though
        # they say "Do not make any assumptions about the order of the output"
        ips = subprocess.check_output(['hostname', '-I']).decode('utf-8')
        ip = ips.split()[0]

        # XXX do a read to an ATX-LED-controlled endpoint, to make sure we're
        # not behind a captive portal or some other crap that's pretending we
        # have internet when we don't
        url = 'https://me.atxled.com/ping.html'

        with urllib.request.urlopen(url) as f:
            key = f.read().strip()

            # Failsafe: check ntp.org
            if key != b'Hello World':
                logging.warning('error getting key from atxled, checking ntp.org')

                url = 'https://www.ntp.org/'
                with urllib.request.urlopen(url) as f:
                    resp = f.read().strip()
                    assert b'Network Time Protocol' in resp, (key, resp[:200])

        return {'mac': mac, 'ip': ip}
    except Exception as e:
        logging.error('error getting LAN info: %s', e)
        return None

# Return backup of user data as a BytesIO containing a zip file
def get_db_backup():
    # Create database backup bundle
    backup = io.BytesIO()
    with zipfile.ZipFile(backup, mode='w',
            compression=zipfile.ZIP_DEFLATED) as backup_zip:
        paths = ['%s/%s' % (USER_DATA_PATH, path)
                for path in ['config.json', 'zpds-config.json', 'zpds.db']]
        paths += ['/etc/wpa_supplicant/wpa_supplicant.conf']
        for path in paths:
            status = "doesn't exist"
            if os.path.exists(path):
                backup_zip.write(path)
                with open(path, 'rb') as f:
                    status = '%s bytes' % len(f.read())
            logging.info('file %s: %s', path, status)

    backup.seek(0, 2)
    logging.info('Backing up user data, %s bytes.', backup.tell())
    backup.seek(0)
    return backup

# Send ip/map to me.atxled.com for local redirection
LAST_DATA = None
LAST_UPDATE_TIME = 0
TWO_WEEKS = 14*24*60*60
def update_boom(data):
    global LAST_DATA, LAST_UPDATE_TIME

    import requests

    # Reload the config from the database in case it's changed, and check
    # for database backup opt-out. Return True if opted out so we don't check
    # for two weeks
    reload_config()
    if not CRON_BOOM_CONFIG.get('enable_backups'):
        logging.info('Skipping backup/ping, opted out...')
        return True

    # Check the modification time on the ZPDS database, and backup if it's recent.
    # Otherwise, we only backup if our ip has changed, or two weeks have passed
    db_path = '%s/zpds.db' % USER_DATA_PATH
    try:
        mtime = os.stat(db_path).st_mtime
    except Exception:
        mtime = 0
    now = time.time()
    delta = now - LAST_UPDATE_TIME
    if (mtime < LAST_UPDATE_TIME and data == LAST_DATA and delta < TWO_WEEKS):
        return True

    try:
        logging.info('Updating boomerang service: %s', data)

        backup = get_db_backup()

        response = requests.put('https://me.atxled.com/up/?lan=%s&mac=%s' %
                (data['ip'], data['mac']), data=backup)
        if response.status_code != 200:
            logging.info('could not update boomerang service[%s]: %s',
                    response.status_code, response.text)
            return False
    except Exception as e:
        logging.exception('Could not update boomerang service')
        return False

    # The response from me.atxled.com will indicate whether the public IP
    # has changed. If it's changed, notify zpds that we should refresh the
    # sunrise/sunset data. We try up to 3 times with a sleep between in case
    # the server is down for some reason (this is fairly likely to happen
    # right when the server starts up, cron-boom starts faster than zpds)
    if response.text.startswith('unknown'):
        logging.info('IP has changed, refreshing GPS')
        for i in range(3):
            try:
                response = requests.post('http://localhost/dali/api/clear-gps-cache')
                assert response.status_code == 200
            except Exception as e:
                logging.exception('got error refreshing GPS cache [%s]: %r',
                        response.status_code, response.text)
                time.sleep(10)
                continue
            # Successfully cleared cache, break out
            else:
                break
        else:
            return False

    # Remember when/what we last backed up
    LAST_DATA = data
    LAST_UPDATE_TIME = now

    return True

def run_cmd(*cmd):
    return subprocess.check_call(cmd)

def run_cmd_out(*cmd):
    return subprocess.check_output(cmd).decode('utf-8')

def run_wpa_cli(*args):
    return run_cmd_out('wpa_cli', '-iwlan0', *args)

# Run wpa_cli status and parse the output into a dict
def get_wpa_status():
    result = {}
    for line in run_wpa_cli('status').splitlines():
        k, _, v = line.partition('=')
        result[k] = v
    return result

# Get wifi SSIDs currently being broadcasted
def scan_wifi():
    try:
        scan = run_wpa_cli('scan_results')
        networks = collections.defaultdict(lambda: -100000)
        for line in scan.splitlines():
            try:
                _, _, signal, _, ssid = line.split('\t')
                # Get the maximum signal level for all the networks with the
                # same name
                networks[ssid] = max(networks[ssid], int(signal))
            except Exception:
                pass

        networks = [ssid for [ssid, signal] in
                sorted(networks.items(), key=lambda i: i[1]) if ssid]
        return networks
    except Exception as e:
        logging.error('error getting scanned networks: %s', e)
        return []

def get_conf_networks():
    try:
        network_lines = run_wpa_cli('list_networks').splitlines()
        conf_networks = {}
        for line in network_lines[1:]:
            net_id, ssid, _, _ = line.split('\t')
            conf_networks[ssid] = net_id
        return conf_networks
    except Exception as e:
        logging.error('error getting configured networks: %s', e)
        return {}

# While in hotspot mode, we can still scan for networks. Check if we see
# a network being broadcast that we have a configured password for, so
# we can try connecting to it
def check_maybe_connectable():
    conf_networks = set(get_conf_networks().values())
    avail_networks = set(scan_wifi())

    # Return whether there's any overlap between the two sets
    return conf_networks & avail_networks

# Start up a wifi hotspot
def start_hotspot():
    global NETWORK_CONFIG

    if NETWORK_CONFIG is not None:
        return

    logging.info('Starting wifi hotspot!')

    run_wpa_cli('disconnect')
    run_cmd('sudo', 'cp', './data/dhcpcd.hotspot', '/etc/dhcpcd.conf')
    run_cmd('sudo', 'cp', './data/hostapd.conf', '/etc/hostapd/hostapd.conf')
    run_cmd('sudo', 'cp', './data/dnsmasq.conf', '/etc/dnsmasq.conf')
    run_cmd('sudo', 'systemctl', 'stop', 'dnsmasq')
    run_cmd('sudo', 'systemctl', 'restart', 'dhcpcd')
    # Meh, we need dhcpcd to assign the static IP before we start dnsmasq,
    # but the assignment happens after dhcpcd has gone to the background
    time.sleep(30)
    run_cmd('sudo', 'systemctl', 'restart', 'dnsmasq')
    # Start this up last, otherwise we get this error:
    #  hostapd.service: Can't open PID file /run/hostapd.pid (yet?) after
    #  start: No such file or directory
    # I don't know what this means!
    run_cmd('sudo', 'systemctl', 'restart', 'hostapd')

# Bring down the wifi hotspot, resume normal operation
def stop_hotspot():
    global NETWORK_CONFIG
    logging.info('Stopping wifi hotspot!')

    try:
        # Bring down the AP first, so we don't try to connect to ourselves
        run_cmd('sudo', 'systemctl', 'stop', 'dnsmasq', 'hostapd')
        #run_cmd('sudo', 'systemctl', 'stop', 'dhcpcd')

        # Remove this network from the configuration if it already exists
        if NETWORK_CONFIG is not None:
            ssid = NETWORK_CONFIG['ssid']
            password = NETWORK_CONFIG['password']
            conf_networks = get_conf_networks()
            if ssid in conf_networks:
                net_id = conf_networks[ssid]
                run_wpa_cli('remove_network', net_id)

            # Set the network up and save the config
            net_id = run_wpa_cli('add_network')
            run_wpa_cli('set_network', net_id, 'ssid', '"%s"' % ssid)
            run_wpa_cli('set_network', net_id, 'priority', str(int(time.time())))
            if password:
                run_wpa_cli('set_network', net_id, 'psk', '"%s"' % password)
                run_wpa_cli('set_network', net_id, 'key_mgmt', 'WPA-PSK')
            else:
                run_wpa_cli('set_network', net_id, 'key_mgmt', 'NONE')
            run_wpa_cli('enable_network', net_id)
            run_wpa_cli('save_config')

            NETWORK_CONFIG = None

        run_cmd('sudo', 'cp', './data/dhcpcd.normal', '/etc/dhcpcd.conf')

        # Handle static IP address.
        static_ip = get_static_ip()
        if static_ip:
            dhcpcd_data = '''
# Set static IP address, added by cron-boom.py
interface wlan0
#nohook wpa_supplicant
static ip_address={ip}/{mask}
static routers={router}
static domain_name_servers={dns}
'''.format(**static_ip)
            # Annoying: we need sudo access to append to this file, and
            # so we have to spawn two subshells so the shell redirection
            # happens under sudo. The format of the static IP has been checked
            # in get_static_ip() so no need to escape or anything
            run_cmd('sudo', 'sh', '-c', 'echo "%s" >> /etc/dhcpcd.conf' % dhcpcd_data)

        run_cmd('sudo', 'cp', './data/wlan0.atxled', '/etc/network/interfaces.d/')
        run_cmd('sudo', 'ip', 'link', 'set', 'wlan0', 'down')
        run_cmd('sudo', 'ip', 'link', 'set', 'wlan0', 'up')
        run_cmd('sudo', 'systemctl', 'restart', 'dhcpcd')
        time.sleep(2)
        run_wpa_cli('reassociate')
        return True
    except Exception:
        logging.exception('got exception stopping hotspot')
    return False

def get_static_ip():
    info = None
    try:
        if os.path.exists(STATIC_IP_PATH):
            with open(STATIC_IP_PATH) as f:
                info = json.load(f)
                assert isinstance(info, dict)
                for [k, v] in info.items():
                    assert k in ['ip', 'mask', 'router', 'dns']
                    assert isinstance(v, str)
                    assert re.match('^[0-9a-f.:,]+$', v)
                return info
    except Exception:
        logging.error('bad ip address format: %s', info)
    return None

def set_static_ip(ip):
    if not ip:
        if os.path.exists(STATIC_IP_PATH):
            os.unlink(STATIC_IP_PATH)
        return
    with open(STATIC_IP_PATH, 'w') as f:
        f.write(ip)

# Sleep for X seconds, while checking a condition every 5 seconds
def sleep_check(seconds):
    global NETWORK_CONFIG
    while seconds > 5:
        time.sleep(5)
        seconds -= 5
        if NETWORK_CONFIG is not None:
            return True
    time.sleep(seconds)
    return NETWORK_CONFIG is not None

def run_hotspot_mode():
    start_hotspot()

    time_slept = 0

    while True:
        # Sleep for five minutes, waiting for updates from the web interface
        sleep_time = 5*60
        if sleep_check(sleep_time):
            break
        time_slept += sleep_time

        # Check if there's regular internet connectivity (like through a
        # wired connection)
        data = get_internet_status()
        if data:
            logging.info('Got network connection')
            break

        if not LAST_USE_TIME or (time.time() - LAST_USE_TIME) > 4*60:
            # No updates for five minutes, check if we can see a network that
            # we already have configured
            logging.info('Checking for any wifi networks we can connect to...')
            connectable = check_maybe_connectable()
            if connectable:
                logging.info('Found networks with configuration: %s', connectable)
                break

        # Fail safe: if we're in hotspot mode for over an hour, and we haven't
        # gotten any user input, reboot. This is to prevent hotspot mode accidentally
        # putting the pi into a state where it can't reconnect to the internet,
        # which happened a few times during testing for unknown reasons
        # XXX taking out reboot for now, this triggered on Stuart's system and
        # the pi apparently didn't come back up, and the hotspot errors are
        # quite possibly all fixed
        #if time_slept >= 60*60 and (not LAST_USE_TIME or (time.time() - LAST_USE_TIME) > 20*60):
        #    logging.error('Stopping wifi hotspot AND REBOOTING!')
        #    stop_hotspot()
        #    run_cmd('sudo', 'reboot')

    stop_hotspot()

def check_zpds():
    import requests
    try:
        response = requests.get('http://localhost/dali/api/server-status')
        if response.status_code != 200 or response.text != '{"ok":true}\n':
            logging.info('got bad ZPDS status[%s]: %r',
                    response.status_code, response.text)
            return False
    except Exception as e:
        logging.exception('exception getting ZPDS status')
        return False
    return True

def post_watchdog_failure_message():
    import requests
    try:
        mac = get_mac_address()

        response = requests.post('https://me.atxled.com/why.php?value=watchdog&'
                'mac=%s' % mac)
        if response.status_code != 200:
            logging.info('could not send watchdog fail message [%s]: %s',
                    response.status_code, response.text)
    except Exception as e:
        pass

# This loop is the main internet health check.
def check_internet_loop():
    n_fails = 0
    n_status_fails = 0
    logging.info('starting check loop')
    while True:
        # Always start with a sleep
        sleep_check(30)

        # 4 fails in a row
        if HOTSPOT_MODE:
            if n_fails > 3:
                run_hotspot_mode()
                n_fails = 0
                continue

        data = get_internet_status()
        if not data:
            logging.error('error getting LAN info (n_fails=%s)', n_fails)
            n_fails += 1
            continue

        # Send a backup if necessary. update_boom() makes sure we're sending fresh
        # data before actually backing up.
        if not update_boom(data):
            n_fails += 1
            continue

        n_fails = 0

        # Poll ZPDS for status
        if not check_zpds():
            n_status_fails += 1
            if n_status_fails > 10:
                n_status_fails = 0
                logging.error('watchdog failure, restarting')

                # Post a status update to me.atxled.com so we know there was
                # a failure
                post_watchdog_failure_message()

                # Restart the entire stack, and try updating etc.
                # This will kill us, but that's a sacrifice cron-boom is
                # selflessly willing to make for the good of the system.
                subprocess.check_call('sudo systemctl restart --no-block '
                        'atx-led-updater.service', shell=True)
                # Extra sleep here: this should get interrupted by the restart
                time.sleep(5*60)
            continue
        n_status_fails = 0

        sleep_check(3*60-30)

def run_check_loop():
    while True:
        try:
            check_internet_loop()
        except Exception:
            logging.exception('Got error in check loop!')

@app.before_request
def update_user_time():
    global LAST_USE_TIME
    LAST_USE_TIME = time.time()

@app.route('/')
@app.route('/<path:path>')
def get_wifi_setup(**kwargs):
    networks = scan_wifi()
    return flask.render_template('wifi.html', networks=networks)

@app.route('/setup', methods=['POST'])
def post_wifi_setup():
    global NETWORK_CONFIG

    assert NETWORK_CONFIG is None
    ssid = flask.request.form['ssid'] or flask.request.form['ssid-manual']
    # From what I can gather, wpa_supplicant.conf doesn't allow any
    # escaping, but takes every byte between the first and last quotes on
    # a line, so we basically just have to filter newlines
    ssid = ssid.replace('\n', '')
    password = flask.request.form['password'].replace('\n', '')

    # Remove static IP address, since we have a new network config
    set_static_ip(None)

    NETWORK_CONFIG = {'ssid': ssid, 'password': password}

    return flask.render_template('wifi-done.html')

@app.route('/status')
def get_status():
    data = get_internet_status()
    status = get_wpa_status()
    scan = run_wpa_cli('scan_results')

    return '<html><pre>%s\n%s\n%s' % (data, status, scan)

@app.route('/key')
def get_key_page():
    return flask.render_template('key.html')

@app.route('/key', methods=['POST'])
def post_key():
    key = flask.request.form['key']
    #path = '/home/pi/atxled/key'
    path = '/tmp/atx-led-key'
    with open(path, 'wt') as f:
        f.write(key)

    return 'Done.'

@app.route('/restart')
def restart():
    run_cmd('sudo', 'systemctl', 'restart', 'atx-led-updater.service')
    return 'Done.'

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    if len(sys.argv) > 1:
        if sys.argv[1] == 'start':
            start_hotspot()
        elif sys.argv[1] == 'stop':
            stop_hotspot()
        elif sys.argv[1] == 'backup':
            data = get_internet_status()
            update_boom(data)
        elif sys.argv[1] == 'hotspot':
            threading.Thread(target=run_hotspot_mode).start()
            app.run('0.0.0.0', port=5100)
        elif sys.argv[1] == 'set-static-ip':
            # Write the static IP to a file and then "stop hotspot", which puts
            # the internet back to normal mode, respecting the static IP
            set_static_ip(sys.argv[2])
            if not stop_hotspot():
                sys.exit(1)
        elif sys.argv[1] == 'get-static-ip':
            ip = get_static_ip()
            if not ip:
                sys.exit(1)
            print(json.dumps(ip))
        else:
            assert 0, 'bad argument: %s' % (sys.argv)
        sys.exit(0)

    # Make sure the hotspot isn't up
    if HOTSPOT_MODE:
        stop_hotspot()

    # Launch a background thread to check internet status
    threading.Thread(target=run_check_loop).start()
    app.run('0.0.0.0', port=5100)
