"""Licence: one PC, one activation, checked offline.

Each PC has a machine code (from its Windows MachineGuid, or /etc/machine-id).
The seller signs a licence for that code with a private key only they hold;
LoomLab checks the signature with the public key shipped in
`licence-public.key`. Nothing is sent anywhere, and a key copied to another
PC does not fit it.

Enforcement is on only when `licence-public.key` exists (or the
LOOMLAB_PUBLIC_KEY variable holds one): a build without it runs open.

Seller's tools (keep the private key off the mill PCs, never in git):
    python -m app.licence keygen [--private PATH]     once: makes the key pair
    python -m app.licence issue --machine CODE --mill "Shree Textiles" [--days 365]
    python -m app.licence machine                     this PC's code

Signatures are Ed25519 (RFC 8032), in plain Python so nothing is installed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PUBLIC_KEY_PATH = Path(os.environ.get('LOOMLAB_PUBLIC_KEY_FILE') or BACKEND / 'licence-public.key')
LICENCE_PATH = Path(os.environ.get('LICENCE_FILE') or BACKEND / 'licence.key')
PREFIX = 'LL1'

# -- Ed25519, RFC 8032 section 6 ---------------------------------------------
_p = 2 ** 255 - 19
_q = 2 ** 252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _p - 2, _p) % _p
_SQRT_M1 = pow(2, (_p - 1) // 4, _p)


def _sha512_modq(b: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b).digest(), 'little') % _q


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q) -> bool:
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _recover_x(y: int, sign: int):
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p:
        x = x * _SQRT_M1 % _p
    if (x * x - x2) % _p:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_gy = 4 * pow(5, _p - 2, _p) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _compress(P) -> bytes:
    zinv = pow(P[2], _p - 2, _p)
    x, y = P[0] * zinv % _p, P[1] * zinv % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, 'little')
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def _expand(secret: bytes):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _sha512_modq(prefix + msg)
    Rs = _compress(_mul(r, _G))
    s = (r + _sha512_modq(Rs + A + msg) * a) % _q
    return Rs + int.to_bytes(s, 32, 'little')


def verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A, R = _decompress(public), _decompress(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= _q:
        return False
    h = _sha512_modq(signature[:32] + public + msg)
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))


# -- this PC ------------------------------------------------------------------
def _raw_machine_id() -> str:
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return winreg.QueryValueEx(k, 'MachineGuid')[0]
        except OSError:
            pass
    for p in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            v = Path(p).read_text().strip()
            if v:
                return v
        except OSError:
            continue
    return f'{uuid.getnode():012x}'


def machine_code(raw: str | None = None) -> str:
    """This PC's code, e.g. 3F2A-91C0-5B7E-D4A8: a hash of its machine id, so
    the id itself is never shown."""
    h = hashlib.sha256(('loomlab:' + (raw or _raw_machine_id())).encode()).hexdigest()[:16].upper()
    return '-'.join(h[i:i + 4] for i in range(0, 16, 4))


# -- keys -----------------------------------------------------------------------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def issue(secret: bytes, machine: str, mill: str, days: int | None = 365, today: date | None = None) -> str:
    today = today or date.today()
    payload = {'mill': mill, 'machine': machine.strip().upper(), 'issued': today.isoformat(),
               'expires': (today + timedelta(days=days)).isoformat() if days else None}
    body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()
    return f'{PREFIX}.{_b64(body)}.{_b64(sign(secret, body))}'


def check(key: str, public: bytes, machine: str, today: date | None = None) -> dict:
    """{valid, reason, mill, expires} for `key` on this `machine`."""
    today = today or date.today()
    out = {'valid': False, 'reason': '', 'mill': None, 'expires': None}
    try:
        tag, body_b64, sig_b64 = key.strip().split('.')
        body, sig = _unb64(body_b64), _unb64(sig_b64)
        payload = json.loads(body)
    except (ValueError, TypeError):
        return out | {'reason': 'This is not a LoomLab licence key. Copy the whole key, it starts with LL1.'}
    if tag != PREFIX or not verify(public, body, sig):
        return out | {'reason': 'This licence key is not genuine, or was changed after it was issued.'}
    out |= {'mill': payload.get('mill'), 'expires': payload.get('expires')}
    if payload.get('machine') != machine:
        return out | {'reason': f"This key is for another PC ({payload.get('machine')}). This PC is {machine}."}
    if payload.get('expires') and date.fromisoformat(payload['expires']) < today:
        return out | {'reason': f"This licence ended on {payload['expires']}. Ask for a renewal."}
    return out | {'valid': True}


class DamagedKey(Exception):
    pass


def load_public() -> bytes | None:
    env = os.environ.get('LOOMLAB_PUBLIC_KEY')
    raw = env or (PUBLIC_KEY_PATH.read_text(encoding='utf-8-sig').strip() if PUBLIC_KEY_PATH.exists() else '')
    if not raw:
        return None
    try:
        key = bytes.fromhex(raw.strip().lstrip('\ufeff'))
    except ValueError:
        key = b''
    if len(key) != 32:
        raise DamagedKey('The licence public key shipped with LoomLab is damaged. Reinstall LoomLab '
                         'or ask your supplier for licence-public.key.')
    return key


_cache: dict = {}


def status() -> dict:
    """{required, valid, machine, mill, expires, reason}. Cached until the
    licence or public key file changes (a check is a few ms of arithmetic)."""
    machine = machine_code()
    try:
        public = load_public()
    except DamagedKey as e:     # locked, and saying why, rather than a server error on every call
        return {'required': True, 'valid': False, 'machine': machine, 'mill': None, 'expires': None,
                'reason': str(e)}
    stamp = (public, LICENCE_PATH.stat().st_mtime_ns if LICENCE_PATH.exists() else None, date.today())
    if _cache.get('stamp') == stamp:
        return _cache['status']
    if public is None:
        st = {'required': False, 'valid': True, 'machine': machine, 'mill': None, 'expires': None, 'reason': ''}
    elif not LICENCE_PATH.exists():
        st = {'required': True, 'valid': False, 'machine': machine, 'mill': None, 'expires': None,
              'reason': f'LoomLab is not activated on this PC. Send this machine code to get a licence key: {machine}'}
    else:
        st = {'required': True, 'machine': machine} | check(LICENCE_PATH.read_text(), public, machine)
    _cache.update(stamp=stamp, status=st)
    return st


def activate(key: str) -> dict:
    """Save `key` if it fits this PC; returns the check."""
    try:
        public = load_public()
    except DamagedKey as e:
        return {'required': True, 'valid': False, 'machine': machine_code(), 'mill': None, 'expires': None,
                'reason': str(e)}
    if public is None:
        return {'required': False, 'valid': True, 'machine': machine_code(), 'mill': None, 'expires': None, 'reason': ''}
    result = check(key, public, machine_code())
    if result['valid']:
        LICENCE_PATH.write_text(key.strip() + '\n', encoding='utf-8')
        _cache.clear()
    return {'required': True, 'machine': machine_code()} | result


# -- seller's command line --------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python -m app.licence', description='LoomLab licences (seller side).')
    sub = ap.add_subparsers(dest='cmd', required=True)
    k = sub.add_parser('keygen', help='make the key pair, once')
    k.add_argument('--private', type=Path, default=Path.home() / 'loomlab-private.key')
    k.add_argument('--public', type=Path, default=PUBLIC_KEY_PATH)
    i = sub.add_parser('issue', help='a licence key for one PC')
    i.add_argument('--machine', required=True)
    i.add_argument('--mill', required=True)
    i.add_argument('--days', type=int, default=365, help='0 = never ends')
    i.add_argument('--private', type=Path, default=Path.home() / 'loomlab-private.key')
    sub.add_parser('machine', help="this PC's machine code")
    a = ap.parse_args(argv)
    if a.cmd == 'machine':
        print(machine_code())
    elif a.cmd == 'keygen':
        if a.private.exists():
            print(f'{a.private} already exists: a new pair would void every key issued. Delete it first if you mean it.')
            return 2
        secret = os.urandom(32)
        a.private.write_text(secret.hex() + '\n')
        try:
            a.private.chmod(0o600)
        except OSError:
            pass
        a.public.write_text(public_key(secret).hex() + '\n')
        print(f'Private key: {a.private}  (keep it safe and secret; never on a mill PC, never in git)')
        print(f'Public key:  {a.public}  (ships with LoomLab; from now on it needs a licence)')
    elif a.cmd == 'issue':
        if not a.private.exists():
            print(f'No private key at {a.private}. Run keygen first, or pass --private.')
            return 2
        secret = bytes.fromhex(a.private.read_text().strip())
        print(issue(secret, a.machine, a.mill, a.days or None))
    return 0


if __name__ == '__main__':
    sys.exit(main())
