import copy
import json
import logging
import requests
import socket

from functions import generate_unique_id, light_types, pretty_json

def set_light(address, light, data):
    state = requests.put("http://"+address["ip"]+"/state", json=data, timeout=3)
    return state.text

def get_light_state(address, light):
    state = requests.get("http://"+address["ip"]+"/state", timeout=3)
    return json.loads(state.text)

# Discovery utilities

def iter_ips(args, port):
    host = args.ip.split('.')
    if args.scan_on_host_ip:
        yield ('127.0.0.1', port)
        return
    for addr in range(args.ip_range_start, args.ip_range_end + 1):
        host[3] = str(addr)
        test_host = '%s.%s.%s.%s' % (*host,)
        if test_host != args.ip:
            yield (test_host, port)

def scan_host(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.02) # Very short timeout. If scanning fails this could be increased
    result = sock.connect_ex((host, port))
    sock.close()
    return result

def find_hosts(args, port):
    validHosts = []
    for host, port in iter_ips(args, port):
        if scan_host(host, port) == 0:
            hostWithPort = '%s:%s' % (host, port)
            validHosts.append(hostWithPort)
    return validHosts

def generate_light_name(base_name, light_nr):
    # Light name can only contain 32 characters
    suffix = ' %s' % light_nr
    return '%s%s' % (base_name[:32-len(suffix)], suffix)

def discover(args):
    device_ips = find_hosts(args, 80)
    logging.info(pretty_json(device_ips))
    for ip in device_ips:
        try:
            response = requests.get("http://" + ip + "/detect", timeout=3)
            if response.status_code == 200:
                # XXX JSON validation
                device_data = json.loads(response.text)
                logging.info(pretty_json(device_data))
                if "modelid" in device_data:
                    logging.info('%s is %s', ip, device_data.get('name'))
                    if "protocol" in device_data:
                        protocol = device_data["protocol"]
                    else:
                        protocol = "native"

                    # Get number of lights
                    if "light_ids" in device_data:
                        lights = device_data["light_ids"]
                    else:
                        n_lights = 1
                        if "lights" in device_data:
                            n_lights = device_data["lights"]
                        lights = []
                        for x in range(1, n_lights + 1):
                            light_name = generate_light_name(device_data['name'], x)
                            lights.append({'light_nr': x, 'name': light_name})

                    for item in lights:
                        # Be sure to copy the default state so we're not sharing
                        # any dictionaries between lights
                        default_state = copy.deepcopy(light_types[device_data["modelid"]])

                        light = {
                            "state": default_state["state"],
                            "type": default_state["type"],
                            "name": item['name'],
                            "uniqueid": generate_unique_id(),
                            "modelid": device_data["modelid"],
                            "manufacturername": "Philips",
                            "swversion": default_state["swversion"]
                        }
                        light_address = {
                            "ip": ip,
                            "light_nr": item['light_nr'],
                            "protocol": protocol,
                            "mac": device_data["mac"],
                            "version": device_data.get("version"),
                            "type": device_data.get("type"),
                            "name": item['name'],
                        }
                        yield (light, light_address)

        except Exception as e:
            logging.exception("ip %s is unknown device", ip)
            #raise
