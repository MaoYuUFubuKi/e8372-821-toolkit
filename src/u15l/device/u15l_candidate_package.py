"""Only this device's fixed four-byte-code-change candidate; no arbitrary input."""
import hashlib
import struct
from u15l_recovery_package import make_restore_package, xor32, SIZE

CANDIDATE_SHA = '__CANDIDATE_SHA__'

def make_candidate_package(payload, original):
    if len(payload) != SIZE or hashlib.sha256(payload).hexdigest() != CANDIDATE_SHA:
        raise RuntimeError('修改候选校验失败，禁止传输。')
    tim, original_fbf = make_restore_package(original)
    fbf = bytearray(original_fbf)
    struct.pack_into('<I', fbf, 0x100 + 0xf4 + 0x30, xor32(payload))
    fbf[4096:] = payload
    # The original-only package defines the address, device and erase bounds.
    assert fbf[:0x224] == original_fbf[:0x224]
    assert fbf[0x228:4096] == original_fbf[0x228:4096]
    return tim, bytes(fbf)
