#!/usr/bin/python3
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse


import util
from util import run

AUTHENTICATION_FILEPATH = "/home/pi/atxled/hue-zpds-htpasswd"
REGISTRATION_FILEPATH = "./user-data/registration.json"
OFFLINE_MODE_FILEPATH = "./offline_mode"
BASE = "%s/.." % sys.path[0]
os.chdir(BASE)

ram_dir = "ramdisk"

offline_mode = False
print("Load binary started.", file=sys.stderr)
print("testing stdout", file=sys.stdout)


def run_cmd(*cmd):
    return subprocess.check_call(cmd)


def check_dataplicity_installed():
    dataplicity_path = "/opt/dataplicity/tuxtunnel/auth"
    dataplicity_code_path = "/home/pi/atxled/user-data/dataplicity_code"
    if os.path.exists(dataplicity_path):
        # return the name of the last dataplicity code used, if it exists
        if os.path.exists(dataplicity_code_path):
            with open(dataplicity_code_path, "r") as f:
                return f.read().strip()
        else:
            return "no code found"
    else:
        return False


def remove_dataplicity():
    print("Removing dataplicity", file=sys.stderr)
    if not check_dataplicity_installed():
        print("dataplicity not installed, nothing to remove", file=sys.stderr)
    else:
        run_cmd("sudo", "rm", "-rf", "/opt/dataplicity")
        run_cmd("sudo", "apt", "purge", "-y", "supervisor")
        run_cmd("sudo", "rm", "-rf", "/etc/supervisor")
        # Remove the code used to install dataplicity
        if os.path.exists("/home/pi/atxled/user-data/dataplicity_code"):
            os.remove("/home/pi/atxled/user-data/dataplicity_code")


def install_dataplicity(response_text):
    print("Installing dataplicity from key response", file=sys.stderr)
    match = re.search(r"DP_install=(.*\.py)", response_text)
    if match:
        dataplicity_code = match.group(1)
        dataplicity_installed = check_dataplicity_installed()
        if dataplicity_installed:
            print(
                "dataplicity already installed with code: %s",
                dataplicity_installed,
                file=sys.stderr,
            )
            if dataplicity_installed == dataplicity_code:
                print(
                    "dataplicity already installed with the same code, skipping",
                    file=sys.stderr,
                )
                return True
            remove_dataplicity()
        try:
            command = (
                "curl https://www.dataplicity.com/%s | sudo python3" % dataplicity_code
            )
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            print("STDOUT: %s", result.stdout, file=sys.stderr)
            print("STDERR: %s", result.stderr, file=sys.stderr)
            # Save the code used to install dataplicity, deleting the old one if it exists
            with open("/home/pi/atxled/user-data/dataplicity_code", "w") as f:
                f.write(dataplicity_code)
        except Exception as e:
            print("exception installing dataplicity [%s]: ", e, file=sys.stderr)
            return False
    else:
        print("dataplicity code not found in response text", file=sys.stderr)
        return False
    return True


if len(sys.argv) > 1 and sys.argv[1] == "ol":
    print("Initializing offline mode.", file=sys.stderr)
    while True:
        try:
            run("sudo umount %s" % ram_dir)
        except:
            break

    run("mkdir -p %s" % ram_dir)
    run("rm -rf ./%s/*" % ram_dir)
    run("sudo chmod 777 %s" % ram_dir)

    with open("./releases/zpds.bin", "rb") as f:
        data = f.read()

    with open("./releases/tag") as f:
        tag = f.read().strip()

    key_response = b""

    if os.path.exists("./key"):
        with open("./key", "rb") as f:
            key_response = f.read().strip()
    elif os.path.exists("/tmp/atx-led-key"):
        with open("/tmp/atx-led-key", "rb") as f:
            key_response = f.read().strip()
    else:
        with open("/sys/class/net/wlan0/address") as f:
            mac = f.read().strip().replace(":", "")

        try:
            with open(REGISTRATION_FILEPATH) as f:
                registration_data = json.load(f)

                if "email" in registration_data:
                    email = registration_data["email"]
                else:
                    email = None

                if "alerts" in registration_data:
                    alerts = registration_data["alerts"]
                else:
                    alerts = None
        except Exception as e:
            print(REGISTRATION_FILEPATH, e, file=sys.stderr)
            email = None
            alerts = None

        branch = None
        if os.path.exists("./branch"):
            with open("./branch", "rb") as f:
                branch = f.read().strip()

        args = {"tag": tag + "-offline", "mac": mac, "channels": 0}
        if email:
            args["email"] = email
        if alerts:
            args["alerts"] = alerts
        if branch:
            args["branch"] = branch
        url = "https://key.dalihub.com/?%s" % urllib.parse.urlencode(args)
        try:
            with urllib.request.urlopen(url) as f:
                key_response = f.read().strip()
                print("got key response initializing offline mode", file=sys.stderr)

        except Exception as e:
            print("could not get key NEW: %s" % e, file=sys.stderr)

    key_response_lines = key_response.splitlines()
    key = key_response_lines[0].strip()
    # check to see if key file resets basic auth, too.
    if len(key_response_lines) > 1:
        if key_response_lines[1] == b"RESET_BASIC_AUTH":
            run("rm -f %s" % AUTHENTICATION_FILEPATH)

    util.crypt_f(key, "./releases/zpds.bin", "%s/zpds.zip" % ram_dir)

    run("unzip %s/zpds.zip -d %s" % (ram_dir, ram_dir))
    print("Offline mode initialized.", file=sys.stderr)
    sys.exit(0)
else:
    # check offline mode
    print("Check offline mode.", file=sys.stderr)
    try:
        with open(OFFLINE_MODE_FILEPATH, "r") as file:
            content = file.read().strip()
            if content == "offline mode=True":
                print(
                    "Offline mode file detected. Setting offline mode to True.",
                    file=sys.stderr,
                )
                offline_mode = True
    except FileNotFoundError:
        print(
            "Offline mode file not found. Continuing in online mode.", file=sys.stderr
        )
    except Exception as e:
        print("Error reading offline mode file: {}".format(e), file=sys.stderr)

    print("Script started.")

    # Check if in offline mode and try to reach key URL
    if offline_mode:
        print(
            "Offline mode detected. Attempting to reach key URL for status check...",
            file=sys.stderr,
        )
        try:
            mac = ""
            try:
                with open("/sys/class/net/wlan0/address") as f:
                    mac = f.read().strip().replace(":", "")
            except Exception as e:
                print("Could not read MAC address: %s" % e, file=sys.stderr)

            args = {"mac": mac, "channels": 0}
            # Attempt to connect to the key URL
            url = "https://key.dalihub.com/?%s" % urllib.parse.urlencode(args)
            with urllib.request.urlopen(url) as f:
                key_response = f.read().strip()

            print(
                "Key URL reached successfully. Server is online. Resetting offline mode and restarting script.",
                file=sys.stderr,
            )

            # If successful, reset offline mode and empty ramdisk
            offline_mode = False
            run("rm -rf ./%s/*" % ram_dir)
            run("rm ./offline_mode")

            # Restart script from the beginning
            print("Restarting script...", file=sys.stderr)
        except Exception as e:
            print(
                "Offline mode: Could not reach key server. Error: %s" % e,
                file=sys.stderr,
            )
            print(
                "Proceeding to start server with run.sh assuming necessary files are in the ramdisk folder.",
                file=sys.stderr,
            )
            os.execlp("sh", "sh", "hue/zpds/run.sh")
            sys.exit(1)  # Exit if running the script fails

    print("Proceeding with normal operation (not in offline mode).", file=sys.stderr)

    def get_channels():
        import serial

        channels = 1
        try:
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

    if not offline_mode:
        print("Retrieving and processing key...", file=sys.stderr)
    while True:
        try:
            run("sudo umount %s" % ram_dir)
        except:
            break

    run("mkdir -p %s" % ram_dir)
    run("rm -rf ./%s/*" % ram_dir)
    run("sudo mount -t ramfs ramfs %s" % ram_dir)
    run("sudo chmod 777 %s" % ram_dir)

    with open("./releases/zpds.bin", "rb") as f:
        data = f.read()

    with open("./releases/tag") as f:
        tag = f.read().strip()

    key_response = b""
    key_response_str = ""

    if os.path.exists("./key"):
        with open("./key", "rb") as f:
            key_response = f.read().strip()
    elif os.path.exists("/tmp/atx-led-key"):
        with open("/tmp/atx-led-key", "rb") as f:
            key_response = f.read().strip()
    else:
        with open("/sys/class/net/wlan0/address") as f:
            mac = f.read().strip().replace(":", "")

        try:
            with open(REGISTRATION_FILEPATH) as f:
                registration_data = json.load(f)

                if "email" in registration_data:
                    email = registration_data["email"]
                else:
                    email = None

                if "alerts" in registration_data:
                    alerts = registration_data["alerts"]
                else:
                    alerts = None
        except Exception as e:
            print(REGISTRATION_FILEPATH, e)
            email = None
            alerts = None

        branch = None
        if os.path.exists("./branch"):
            with open("./branch", "rb") as f:
                branch = f.read().strip()

        args = {"tag": tag, "mac": mac, "channels": get_channels()}
        if email:
            args["email"] = email
        if alerts:
            args["alerts"] = alerts
        if branch:
            args["branch"] = branch
        url = "https://key.dalihub.com/?%s" % urllib.parse.urlencode(args)
        try:
            with urllib.request.urlopen(url) as f:
                key_response = f.read().strip()
                key_response_str = key_response.decode("utf-8")
        except Exception as e:
            print("could not get key NEW: %s" % e, file=sys.stderr)
            sys.exit(1)

    key_response_lines = key_response.splitlines()
    key = key_response_lines[0].strip()
    try:
        if "RESET_BASIC_AUTH" in key_response_str:
            print("Contains RESET_BASIC_AUTH", file=sys.stderr)
            run_cmd("sudo", "rm", "-f", AUTHENTICATION_FILEPATH)
    except Exception as e:
        print("Error checking for RESET_BASIC_AUTH: %s" % e, file=sys.stderr)
    try:
        if "DP_install=" in key_response_str:
            print("Installing dataplicity", file=sys.stderr)
            install_dataplicity(key_response_str)
    except Exception as e:
        print("Error installing dataplicity: %s" % e, file=sys.stderr)

    util.crypt_f(key, "./releases/zpds.bin", "%s/zpds.zip" % ram_dir)

    run("unzip %s/zpds.zip -d %s" % (ram_dir, ram_dir))

    os.execlp("sh", "sh", "hue/zpds/run.sh")
