"""Five-session install gate, independently testable without importing USB."""
from u15l_recovery_package import START, SIZE

PROTECTED = ((0, START), (START + SIZE, 0x980000), (0xb20000, 0x1000000))

def verify_image(actual, reference, payload):
    if len(actual) != 0x1000000 or len(reference) != 0x1000000:
        raise RuntimeError('主闪存读回长度不符。')
    if actual[START:START+SIZE] != payload:
        raise RuntimeError('写入区域与指定数据不一致。')
    if any(actual[a:b] != reference[a:b] for a, b in PROTECTED):
        raise RuntimeError('写入区域外的受保护数据发生变化。')

def install(original, candidate, read, write, checkpoint):
    old = original[START:START+SIZE]
    before = read(1, '备份现状')
    # Do not overwrite an unknown firmware version or an already changed system.
    verify_image(before, original, old)
    checkpoint('identity_verified', before)
    write(2, 'original', old)
    restored = read(3, '核验原版恢复')
    verify_image(restored, before, old)
    checkpoint('original_restore_verified', restored)
    # This call is unreachable on any original restore or readback failure.
    write(4, 'candidate', candidate)
    after = read(5, '核验修改版')
    verify_image(after, restored, candidate)
    checkpoint('candidate_readback_verified', after)
    return after
