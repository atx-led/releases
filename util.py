import hashlib
import subprocess as sp

# Check out my new mixtape, it's called: Roll Your Own Crypto, Vol. 1

# Basically, I just want a simple encryption/decryption function that doesn't
# rely on external code. From what I know about cryptography, this should be
# quite strong. It will certainly be a lot easier to get our code in some
# other way than cracking this (such as intercepting syscalls to unmount
# our ramdisk, and deobfuscating the code from there)

def keystream(key):
    while True:
        hasher = hashlib.sha3_512(key)
        key = hasher.digest()
        hasher.update(b'output')
        yield from hasher.digest()

def crypt(key, data):
    return bytes(k ^ d for k, d in zip(keystream(key), data))

def crypt_f(key, path_in, path_out):
    with open(path_in, 'rb') as f_in:
        with open(path_out, 'wb') as f_out:
            f_out.write(crypt(key, f_in.read()))

def run(args, shell=True, check=0, stdout=sp.PIPE, stderr=sp.PIPE, **kwargs):
    proc = sp.run(args, shell=shell, check=check, stdout=stdout,
            stderr=stderr, **kwargs)
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr)
        assert 0
    return proc
