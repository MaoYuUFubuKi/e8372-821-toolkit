"""Fixed metadata-only recovery test. Contains ZERO erase/write image entries."""
import struct

def make_noop_package():
    tim=bytearray(1024)
    # TIM 3.4.0 header, QSPI subtype 27, two metadata descriptors, no keys/reserved data.
    struct.pack_into('<14I',tim,0,0x30400,0x54494d48,0,0,0,0,0,0,0,0,0x5350491b,2,0,0)
    struct.pack_into('<7I',tim,56,0x54494d48,0x46424630,0xffffffff,0x06001000,1024,0,0)
    struct.pack_into('<7I',tim,152,0x46424630,0xffffffff,0,0x06001000,4096,0,0)
    fbf=bytearray(4096)
    struct.pack_into('<HHIIIIII',fbf,0x20,11,0,0,0,0,0,1,0)
    struct.pack_into('<I',fbf,0x3c,0x100)
    struct.pack_into('<I',fbf,0x100,27)
    # All other fields zero, specifically EraseAll, ResetBBT, OptValue, nOfImages.
    assert fbf[0x144:0x148]==bytes(4) and fbf[0x1f0:0x1f4]==bytes(4)
    return bytes(tim),bytes(fbf)
