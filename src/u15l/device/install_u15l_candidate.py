"""Original recovery verification followed immediately by the fixed candidate.

The independent original recovery bundle is unchanged. Five fresh USB sessions
are necessary because the read and download protocols use separate boot sessions.
"""
import datetime
import fcntl
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import sys

from restore_u15l_original import (
    ROOT, OUT, BACKUPS, SOURCE_SHA, READ_POLICY, session, acquire, write_policy,
)
from u15l_noop_flow import PREAMBLE, frame
from u15l_recovery_package import ORIGINAL_SHA, START, SIZE
from u15l_restore_flow import transfer_restore
from u15l_candidate_package import make_candidate_package, CANDIDATE_SHA
from u15l_candidate_flow import transfer_candidate
from u15l_install_flow import install, verify_image, PROTECTED

BUNDLE_MANIFEST_SHA = '__BUNDLE_MANIFEST_SHA__'
ARCHIVE_SHA = '__ARCHIVE_SHA__'
def sha(data): return hashlib.sha256(data).hexdigest()

def preflight():
    originals = [(BACKUPS/f'original-copy{i}.bin').read_bytes() for i in (1, 2)]
    if originals[0] != originals[1] or sha(originals[0]) != SOURCE_SHA:
        raise RuntimeError('两份原机备份校验失败。')
    original = originals[0]
    old = (OUT/'original-window.bin').read_bytes()
    candidate = (OUT/'candidate-window.bin').read_bytes()
    if old != original[START:START+SIZE] or sha(old) != ORIGINAL_SHA:
        raise RuntimeError('原版恢复数据校验失败。')
    make_candidate_package(candidate, old)
    # Confirm the exact four-byte instruction change again before hardware use.
    def unpack(data):
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        plain = decoder.decompress(data[0x1000:0x137000])
        if not decoder.eof or len(plain) != 0x294fb4:
            raise RuntimeError('固件压缩流不完整。')
        return plain
    a, b = unpack(old), unpack(candidate)
    expected = bytearray(a)
    if a[0x88cfa:0x88cfe] != bytes.fromhex('2de9f043'):
        raise RuntimeError('原版函数入口不符。')
    expected[0x88cfa:0x88cfe] = bytes.fromhex('01207047')
    if b != expected or candidate[:0x1000] != old[:0x1000] or candidate[0x137000:] != old[0x137000:]:
        raise RuntimeError('修改范围超出固定候选。')
    bundle = ROOT/'recovery'
    manifest = (bundle/'SHA256SUMS').read_bytes()
    if sha(manifest) != BUNDLE_MANIFEST_SHA:
        raise RuntimeError('独立回滚工具清单校验失败。')
    for line in manifest.decode().splitlines():
        digest, name = line.split('  ', 1)
        path = (bundle/name).resolve()
        if bundle.resolve() not in path.parents or sha(path.read_bytes()) != digest:
            raise RuntimeError('独立回滚工具文件校验失败：'+name)
    archive = ROOT/'recovery.zip'
    if sha(archive.read_bytes()) != ARCHIVE_SHA:
        raise RuntimeError('独立回滚压缩包校验失败。')
    if shutil.disk_usage(OUT).free < 256*1024*1024:
        raise RuntimeError('需至少 256 MiB 可用磁盘空间。')
    return original, candidate

def candidate_policy(candidate, original):
    tim, fbf = make_candidate_package(candidate, original)
    allowed = {PREAMBLE, frame(0x20), frame(0x26), frame(0x2b), frame(0x27, data=b'\0'), frame(0x30)}
    for image in (tim, fbf):
        at = seq = 0
        while at < len(image):
            seq = (seq+1)&255
            allowed.add(frame(0x2a, seq, (len(image)-at).to_bytes(4, 'little')))
            seq = (seq+1)&255
            chunk = image[at:at+8184]
            allowed.add(frame(0x22, seq, chunk))
            at += len(chunk)
    return allowed

def main():
    stem = '修改版刷入-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    report = OUT/(stem+'.json')
    state = {'started': datetime.datetime.now().astimezone().isoformat(), 'events': [],
             'mode': 'restore_verified_then_fixed_candidate',
             'original_restore_verified': False, 'candidate_readback_verified': False,
             'candidate_write_may_have_started': False, 'rollback_after_error_verified': False,
             'device_boot_verified': False, 'own_sim_internet_verified': False}
    active = {'port': None, 'write_kind': None, 'reference': None}
    def log(kind='install', **values):
        if values.get('flash_write_may_start'):
            state[active['write_kind']+'_write_may_have_started'] = True
        state['events'].append({'kind': kind, **values})
        with report.open('w') as f:
            os.chmod(report, 0o600)
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
    def read(number, label):
        with session(log, f'阶段 {number}/5 {label}', READ_POLICY, active['port']) as (exchange, port):
            active['port'] = port
            return acquire(exchange, log, stem+f'-阶段{number}')
    def write(number, kind, payload):
        active['write_kind'] = kind
        old = original[START:START+SIZE]
        if kind == 'candidate':
            if not state['original_restore_verified']:
                raise RuntimeError('原版恢复尚未核验，禁止刷入修改版。')
            policy = candidate_policy(payload, old)
            transfer = lambda ex: transfer_candidate(ex, payload, old, log=lambda **v: log('candidate_write', **v))
            label = '刷入修改版'
        elif kind == 'original':
            policy = write_policy(payload)
            transfer = lambda ex: transfer_restore(ex, payload, log=lambda **v: log('original_write', **v))
            label = '写回原版，验证回滚'
        else:
            raise RuntimeError('未知写入类型。')
        with session(log, f'阶段 {number}/5 {label}，完成前请勿断电', policy, active['port']) as (exchange, _):
            result = transfer(exchange)
            log('transfer_complete_readback_pending', image=kind, result=result)
    def checkpoint(name, data):
        if name in ('original_restore_verified', 'candidate_readback_verified'):
            state[name] = True
        active['reference'] = data
        log(name, whole_readback_sha256=sha(data), window_sha256=sha(data[START:START+SIZE]),
            protected_ranges=[[hex(a), hex(b)] for a, b in PROTECTED])
        if name == 'original_restore_verified':
            print('原版恢复已真实写回并通过两遍读回核验。接下来直接刷入修改版，无需另行确认。', flush=True)
    lock = None
    try:
        lock = (OUT/'修改版刷入.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original, candidate = preflight()
        log('preflight_passed', candidate_sha256=CANDIDATE_SHA, restore_sha256=ORIGINAL_SHA,
            independent_restore_bundle_verified=True, archive_sha256=ARCHIVE_SHA)
        print('本程序会实际写入：先核验原版回滚，再刷入修改版；不需要再运行旧的原版验证程序。', flush=True)
        print('共五个阶段，每阶段按提示拔插一次。看到“请勿断电”时，等窗口提示下一阶段再拔插。', flush=True)
        print('如果原版恢复核验失败，程序会停止，不进入修改版刷入。', flush=True)
        install(original, candidate, read, write, checkpoint)
        print('修改版已刷入：指定区域两遍读回均与候选一致，受保护区域未改变。', flush=True)
        print('请再拔插一次正常启动，并保持自己的有效 SIM 卡在卡槽中；联网状态还需要检查。', flush=True)
        return 0
    except Exception as exc:
        state['error'] = str(exc)
        log('stopped', reason=str(exc))
        print('程序停止：'+str(exc), flush=True)
        if state['candidate_write_may_have_started']:
            print('修改版写入可能已经开始，将转入原版恢复；请继续按下方提示拔插。', flush=True)
            try:
                old = original[START:START+SIZE]
                active['write_kind'] = 'rollback'
                with session(log, '错误恢复 1/2 写回原版，完成前请勿断电', write_policy(old), active['port']) as (exchange, _):
                    transfer_restore(exchange, old, log=lambda **v: log('error_restore', **v))
                with session(log, '错误恢复 2/2 读回核验', READ_POLICY, active['port']) as (exchange, _):
                    restored = acquire(exchange, log, stem+'-错误后恢复')
                verify_image(restored, active['reference'], old)
                state['rollback_after_error_verified'] = True
                log('error_restore_verified', window_sha256=sha(restored[START:START+SIZE]))
                print('已恢复原版并通过两遍读回核验；修改版安装未成功，请把记录交给我分析。', flush=True)
            except Exception as recovery_error:
                state['rollback_error'] = str(recovery_error)
                log('error_restore_stopped', reason=str(recovery_error))
                print('本次恢复尚未核验成功。请保留日志，使用独立的“U15L原版恢复工具/恢复原版.command”。', flush=True)
        elif state.get('original_write_may_have_started') and not state['original_restore_verified']:
            print('原版写回尚未完成核验；修改版未发送。请保留日志，使用独立原版恢复工具。', flush=True)
        return 1
    finally:
        log('finished', time=datetime.datetime.now().astimezone().isoformat())
        print('记录位置：'+str(report), flush=True)
        if lock is not None: lock.close()

if __name__ == '__main__':
    sys.exit(main())
