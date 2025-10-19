#!/usr/bin/python3
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse

import util
from util import run

AUTHENTICATION_FILEPATH = "/home/pi/atxled/hue-zpds-htpasswd"
REGISTRATION_FILEPATH = "./user-data/registration.json"
BASE = "%s/.." % sys.path[0]
os.chdir(BASE)

RAM_DIR = "ramdisk"
KEY_FILEPATH = "./key"
TMP_KEY_FILEPATH = "/tmp/atx-led-key"

KEY_FETCH_TS_PATH = "./user-data/last_key_fetch_at"
KEY_FETCH_INTERVAL_SECS = 3600  # 1 hour

# ----------------------------
# Small shell helpers
# ----------------------------
def run_cmd(*cmd):
    return subprocess.check_call(cmd)

# ----------------------------
# Dataplicity helpers
# ----------------------------
def check_dataplicity_installed():
    dataplicity_path = "/opt/dataplicity/tuxtunnel/auth"
    dataplicity_code_path = "/home/pi/atxled/user-data/dataplicity_code"
    if os.path.exists(dataplicity_path):
        if os.path.exists(dataplicity_code_path):
            with open(dataplicity_code_path, "r") as f:
                return f.read().strip()
        return "no code found"
    return False

def remove_dataplicity():
    print("Removing dataplicity", file=sys.stderr)
    if not check_dataplicity_installed():
        print("dataplicity not installed, nothing to remove", file=sys.stderr)
        return
    run_cmd("sudo", "rm", "-rf", "/opt/dataplicity")
    run_cmd("sudo", "apt", "purge", "-y", "supervisor")
    run_cmd("sudo", "rm", "-rf", "/etc/supervisor")
    code_path = "/home/pi/atxled/user-data/dataplicity_code"
    if os.path.exists(code_path):
        os.remove(code_path)

def install_dataplicity(response_text):
    print("Installing dataplicity from key response", file=sys.stderr)
    match = re.search(r"DP_install=(.*\.py)", response_text)
    if not match:
        print("dataplicity code not found in response text", file=sys.stderr)
        return False
    dataplicity_code = match.group(1)
    installed = check_dataplicity_installed()
    if installed:
        print("dataplicity already installed with code: %s" % installed, file=sys.stderr)
        if installed == dataplicity_code:
            print("dataplicity code unchanged; skipping reinstall", file=sys.stderr)
            return True
        remove_dataplicity()
    try:
        command = "curl https://www.dataplicity.com/%s | sudo python3" % dataplicity_code
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        print("STDOUT: %s" % result.stdout, file=sys.stderr)
        print("STDERR: %s" % result.stderr, file=sys.stderr)
        with open("/home/pi/atxled/user-data/dataplicity_code", "w") as f:
            f.write(dataplicity_code)
        return True
    except Exception as e:
        print("exception installing dataplicity [%s]" % e, file=sys.stderr)
        return False

# ----------------------------
# Device + metadata helpers
# ----------------------------
def get_tag():
    with open("./releases/tag") as f:
        return f.read().strip()

def get_branch():
    if os.path.exists("./branch"):
        with open("./branch", "rb") as f:
            return f.read().strip().decode("utf-8", errors="ignore")
    return None

def get_mac():
    try:
        with open("/sys/class/net/wlan0/address") as f:
            return f.read().strip().replace(":", "")
    except Exception as e:
        print("Could not read MAC address: %s" % e, file=sys.stderr)
        return ""

def read_registration():
    email = None
    alerts = None
    try:
        with open(REGISTRATION_FILEPATH) as f:
            data = json.load(f)
            email = data.get("email")
            alerts = data.get("alerts")
    except Exception as e:
        print("%s %s" % (REGISTRATION_FILEPATH, e), file=sys.stderr)
    return email, alerts

def get_channels():
    import serial
    try:
        channels = 1
        conn = serial.Serial(
            port="/dev/ttyS0",
            baudrate=19200,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.5,
        )
        conn.write(b"v\n")
        line = ""
        while True:
            byte = conn.read(1).decode("ascii")
            if not byte or byte == "\n":
                break
            line += byte
        if len(line) >= 7:
            channels = int(line[5:7])
        return channels
    except Exception as e:
        print("could not determine channel count: %s" % e, file=sys.stderr)
    return 0

# ----------------------------
# Key fetch throttle helpers
# ----------------------------
def _ensure_user_data_dir():
    try:
        os.makedirs("./user-data", exist_ok=True)
    except Exception:
        pass

def _read_last_key_fetch_at():
    try:
        with open(KEY_FETCH_TS_PATH, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def _write_last_key_fetch_at(ts=None):
    _ensure_user_data_dir()
    if ts is None:
        ts = int(time.time())
    try:
        with open(KEY_FETCH_TS_PATH, "w") as f:
            f.write(str(ts))
    except Exception as e:
        print("Failed to write last_key_fetch_at: %s" % e, file=sys.stderr)

def _should_skip_remote_fetch(local_available):
    last = _read_last_key_fetch_at()
    if last <= 0:
        return False
    age = int(time.time()) - last
    if age < KEY_FETCH_INTERVAL_SECS and local_available:
        print("Skipping key URL fetch (last fetch %d seconds ago); using local key." % age, file=sys.stderr)
        return True
    return False

# ----------------------------
# Key handling
# ----------------------------
def load_local_key_response():
    if os.path.exists(KEY_FILEPATH):
        with open(KEY_FILEPATH, "rb") as f:
            return f.read().strip(), KEY_FILEPATH
    if os.path.exists(TMP_KEY_FILEPATH):
        with open(TMP_KEY_FILEPATH, "rb") as f:
            return f.read().strip(), TMP_KEY_FILEPATH
    return None, None

def save_key_response(resp):
    try:
        with open(KEY_FILEPATH, "wb") as f:
            f.write(resp)
    except Exception as e:
        print("Failed to write key file: %s" % e, file=sys.stderr)

def fetch_key_response():
    tag = get_tag()
    mac = get_mac()
    email, alerts = read_registration()
    branch = get_branch()
    args = {"tag": tag, "mac": mac, "channels": get_channels()}
    if email:
        args["email"] = email
    if alerts:
        args["alerts"] = alerts
    if branch:
        args["branch"] = branch
    url = "https://key.dalihub.com/?%s" % urllib.parse.urlencode(args)
    for delay in [1, 5, 10]:
        try:
            with urllib.request.urlopen(url, timeout=10) as f:
                return f.read().strip()
        except Exception as e:
            if delay != 10:  # not last attempt
                time.sleep(delay)

def select_key_response():
    local_resp, local_path = load_local_key_response()
    local_available = local_resp is not None and len(local_resp.strip()) > 0

    # If local key exists but is empty, try fetching from URL
    if local_resp is not None and len(local_resp.strip()) == 0:
        print("Local key file exists but is empty; attempting to fetch from URL.", file=sys.stderr)
        local_available = False

    # Throttle check only if a valid local key exists
    if _should_skip_remote_fetch(local_available):
        return local_resp

    try:
        print("Attempting to fetch key from URL…", file=sys.stderr)
        remote_resp = fetch_key_response()
        if remote_resp and len(remote_resp.strip()) > 0:
            print("Key fetched from URL; persisting to ./key", file=sys.stderr)
            save_key_response(remote_resp)
            _write_last_key_fetch_at()
            return remote_resp
        else:
            print("Fetched key is empty; skipping write.", file=sys.stderr)
            if local_available:
                print("Falling back to local key (%s)" % local_path, file=sys.stderr)
                return local_resp
            print("No valid key available; aborting.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print("Key fetch failed: %s" % e, file=sys.stderr)
        if local_available:
            print("Falling back to local key (%s)" % local_path, file=sys.stderr)
            return local_resp
        print("No local key available and fetch failed; aborting.", file=sys.stderr)
        sys.exit(1)



def process_key_response(key_resp):
    if not key_resp or len(key_resp.strip()) == 0:
        raise ValueError("Empty key response provided")

    text = ""
    try:
        text = key_resp.decode("utf-8", errors="ignore")
    except Exception:
        pass

    if "RESET_BASIC_AUTH" in text:
        print("Key response requests RESET_BASIC_AUTH; removing htpasswd", file=sys.stderr)
        try:
            run_cmd("sudo", "rm", "-f", AUTHENTICATION_FILEPATH)
        except Exception as e:
            print("Failed to remove htpasswd: %s" % e, file=sys.stderr)

    if "DP_install=" in text:
        try:
            install_dataplicity(text)
        except Exception as e:
            print("Dataplicity install error: %s" % e, file=sys.stderr)

    lines = key_resp.splitlines()
    if not lines:
        raise ValueError("No lines found in key response")
    first_line = lines[0].strip()
    if not first_line:
        raise ValueError("Key line is empty")
    return first_line

# ----------------------------
# Runtime prep + launch
# ----------------------------
def prepare_ramdisk():
    while True:
        try:
            run("sudo umount %s" % RAM_DIR)
        except Exception:
            break
    run("mkdir -p %s" % RAM_DIR)
    run("rm -rf ./%s/*" % RAM_DIR)
    try:
        run("sudo mount -t ramfs ramfs %s" % RAM_DIR)
    except Exception as e:
        print("mount ramfs note: %s" % e, file=sys.stderr)
    run("sudo chmod 777 %s" % RAM_DIR)

def decrypt_and_unzip(key):
    with open("./releases/zpds.bin", "rb") as _:
        pass
    out_zip = RAM_DIR + "/zpds.zip"
    util.crypt_f(key, "./releases/zpds.bin", out_zip)
    run("unzip -o %s -d %s" % (out_zip, RAM_DIR))

def main():
    print("Load binary started.", file=sys.stderr)
    print("testing stdout", file=sys.stdout)

    key_resp = select_key_response()
    key = process_key_response(key_resp)

    prepare_ramdisk()
    decrypt_and_unzip(key)

    os.execlp("sh", "sh", "hue/zpds/run.sh")

if __name__ == "__main__":
    main()
