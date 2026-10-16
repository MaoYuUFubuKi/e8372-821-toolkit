"""Check the restore-before-patch gate, bounds, and failures with fake flash."""
import json
from install_u15l_candidate import preflight
from u15l_install_flow import install
from u15l_recovery_package import START, SIZE

original, candidate = preflight()
def case(kind):
    flash = bytearray(original)
    writes, checkpoints = [], []
    def read(number, label):
        if kind == 'pre_read_failure' and number == 1: raise RuntimeError('read failure')
        if kind == 'restore_read_failure' and number == 3: raise RuntimeError('read failure')
        if kind == 'patch_read_failure' and number == 5: raise RuntimeError('read failure')
        if kind == 'wrong_device' and number == 1: flash[0x7000] ^= 1
        if kind == 'unknown_existing_firmware' and number == 1: flash[START] ^= 1
        if kind == 'restore_mismatch' and number == 3: flash[START] ^= 1
        if kind == 'restore_outside_change' and number == 3: flash[0x80000] ^= 1
        if kind == 'patch_mismatch' and number == 5: flash[START+100] ^= 1
        if kind == 'patch_outside_change' and number == 5: flash[0x80000] ^= 1
        if kind == 'runtime_config_change' and number in (3, 5): flash[0x990000] ^= 1
        return bytes(flash)
    def write(number, which, payload):
        if which == 'candidate': assert 'original_restore_verified' in checkpoints
        writes.append(which)
        if kind == 'restore_transfer_failure' and number == 2: raise RuntimeError('write failure')
        if kind == 'patch_transfer_failure' and number == 4: raise RuntimeError('write failure')
        flash[START:START+SIZE] = payload
    def checkpoint(name, data): checkpoints.append(name)
    failure = False
    try: install(original, candidate, read, write, checkpoint)
    except RuntimeError: failure = True
    assert failure == (kind not in ('success', 'runtime_config_change')), kind
    before_patch_failures = ('pre_read_failure', 'restore_read_failure', 'wrong_device',
                            'unknown_existing_firmware', 'restore_mismatch',
                            'restore_outside_change', 'restore_transfer_failure')
    if kind in before_patch_failures:
        assert 'candidate' not in writes and 'original_restore_verified' not in checkpoints
    if not failure:
        assert writes == ['original', 'candidate']
        assert checkpoints[-2:] == ['original_restore_verified', 'candidate_readback_verified']
    return {'case': kind, 'passed': True, 'writes_attempted': writes}

if __name__ == '__main__':
    cases = ('success', 'runtime_config_change', 'pre_read_failure', 'wrong_device',
             'unknown_existing_firmware', 'restore_transfer_failure', 'restore_read_failure',
             'restore_mismatch', 'restore_outside_change', 'patch_transfer_failure',
             'patch_read_failure', 'patch_mismatch', 'patch_outside_change')
    print(json.dumps([case(k) for k in cases], indent=2))
