"""Version-pinned range restore package. No arbitrary image/offset interface."""
import hashlib,struct
from u15l_noop_package import make_noop_package
START=0x480000
SIZE=0x140000
ORIGINAL_SHA='__ORIGINAL_SHA__'
def xor32(d):
    result=0
    for (v,) in struct.iter_unpack('<I',d):result^=v
    return result
def make_restore_package(payload):
    if len(payload)!=SIZE or hashlib.sha256(payload).hexdigest()!=ORIGINAL_SHA:
        raise RuntimeError('原版恢复文件校验失败，禁止传输。')
    tim,_=make_noop_package();tim=bytearray(tim)
    fbf=bytearray(4096+len(payload));dev=0x100
    struct.pack_into('<I',tim,152+16,len(fbf))
    struct.pack_into('<HHIIIIII',fbf,0x20,11,0,SIZE,SIZE,SIZE,0,1,0)
    struct.pack_into('<I',fbf,0x3c,dev)
    struct.pack_into('<I',fbf,dev,27)
    struct.pack_into('<I',fbf,dev+0xf0,1)
    struct.pack_into('<13I',fbf,dev+0xf4,0x50434830,0,0,SIZE,3,1,SIZE,START,0,0,0,0,xor32(payload))
    fbf[4096:]=payload
    assert fbf[dev+0x44:dev+0x4c]==bytes(8)
    return bytes(tim),bytes(fbf)
