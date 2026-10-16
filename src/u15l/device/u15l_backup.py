"""Bounded QSPI main-array acquisition. No device writes, RAM loads or reset.

TIMH from this device describes data through 0xb60000. Acquire the first
16 MiB in 1 MiB areas, twice. Physical capacity is NOT yet confirmed, so
even a successful acquisition is labelled a range backup, not full firmware.
"""
import hashlib
import os
import pathlib
import struct

LIMIT = 16 * 1024 * 1024
AREA = 1024 * 1024
PREFIX_SHA256 = 'a03e30e27c254666ea35881a25096723c38f3087eb8b40d230d6ea892f93b78f'
HEADERS = tuple(bytes.fromhex('3200000010000000') +
                struct.pack('<BBBBIIBBBB', 0, 27, 0, 32, offset, AREA, 0, 0, 0, 0)
                for offset in range(0, LIMIT, AREA))
ADDRESS_LIMIT = 32 * 1024 * 1024
ADDRESS_HEADERS = tuple(bytes.fromhex('3200000010000000') +
                        struct.pack('<BBBBIIBBBB', 0, 27, 0, 64, offset, AREA, 0, 0, 0, 0)
                        for offset in range(0, ADDRESS_LIMIT, AREA))
DATA = bytes.fromhex('3300000000000000')


def acquire(exchange, query, drain, finish_area, log, out, stem, *, address_space=False):
    limit = ADDRESS_LIMIT if address_space else LIMIT
    headers = ADDRESS_HEADERS if address_space else HEADERS
    label = '零至32MiB地址记录' if address_space else '闪存前16MiB'
    paths = []
    digests = []
    first_hashes = []
    for pass_no in (1, 2):
        dest = pathlib.Path(out) / f'{stem}-{label}-读取{pass_no}.bin'
        partial = dest.with_suffix('.bin.partial')
        total_hash = hashlib.sha256()
        with partial.open('xb') as fp:
            partial.chmod(0o600)
            for index, header in enumerate(headers):
                offset = index * AREA
                if pass_no != 1 or index != 0:
                    preamble = exchange(bytes.fromhex('00d3022b'), 'Preamble')
                    if preamble[:3] != bytes.fromhex('00d302') or preamble[3] not in (0, 0x2b):
                        raise RuntimeError('下一段读取握手异常，已停止并保留部分文件。')
                    proto = query(0x34)
                    if len(proto) != 10 or proto[3] != 0 or proto[6:] != bytes.fromhex('01010000'):
                        raise RuntimeError('读取协议变化，已停止。')
                    if proto[4] & 1: drain()
                    params = query(0x35)
                    if len(params) != 22 or params[3] != 0 or params[6:10] != bytes.fromhex('00200000'):
                        raise RuntimeError('读取缓冲参数变化，已停止。')
                    if params[4] & 1: drain()
                response = exchange(header, f'UploadDataHeader: QSPI 0x{offset:x} length {AREA}')
                if len(response) != 6 or response[3] != 0:
                    log('backup_header_rejected', pass_number=pass_no, offset=offset,
                        response_hex=response.hex())
                    raise RuntimeError('设备拒绝这一段读取，已停止；部分文件不是完整备份。')
                if response[4] & 1: drain()
                buf = bytearray()
                while len(buf) < AREA:
                    expected = min(8186, AREA - len(buf))
                    data = exchange(DATA, 'UploadData: backup device to host')
                    if len(data) != expected + 6 or data[3] != 0:
                        log('backup_data_error', pass_number=pass_no, offset=offset+len(buf),
                            expected=expected, actual=len(data), response_prefix=data[:10].hex())
                        raise RuntimeError('数据回应长度或状态异常，已停止，不补零或跳过。')
                    buf.extend(data[6:])
                    if offset == 0 and len(buf) >= 4096 and len(buf) - expected < 4096:
                        if hashlib.sha256(buf[:4096]).hexdigest() != PREFIX_SHA256:
                            raise RuntimeError('开头数据与已验证的本机样本不同，已停止。')
                    if data[4] & 1: drain()
                finish_area()
                area_hash = hashlib.sha256(buf).hexdigest()
                if pass_no == 2 and area_hash != first_hashes[index]:
                    fp.write(buf)
                    log('backup_mismatch', offset=offset, pass_number=pass_no)
                    raise RuntimeError('两次读取不一致，已停止；不能作为可靠备份。')
                if pass_no == 1: first_hashes.append(area_hash)
                fp.write(buf)
                fp.flush()
                total_hash.update(buf)
                log('backup_area_saved', pass_number=pass_no, offset=offset,
                    bytes=AREA, sha256=area_hash, verified_against_first=(pass_no == 2))
                print(f'第 {pass_no}/2 遍：已读取 {(offset+AREA)//AREA}/{limit//AREA} MiB 地址范围。', flush=True)
            os.fsync(fp.fileno())
        partial.rename(dest)
        paths.append(dest.name)
        digests.append(total_hash.hexdigest())
        log('backup_pass_saved', pass_number=pass_no, path=dest.name, bytes=limit,
            sha256=digests[-1], full_firmware_read=False)
    if digests[0] != digests[1]:
        raise RuntimeError('整段校验失败，不能作为可靠备份。')
    log('range_backup_verified', paths=paths, bytes_per_copy=limit, sha256=digests[0],
        identical=True, capacity_confirmed=False, full_firmware_read=False)
    if address_space:
        capture = (pathlib.Path(out) / paths[0]).read_bytes()
        lower, upper = capture[:LIMIT], capture[LIMIT:]
        mirror = lower == upper
        log('same_session_address_comparison', identical_halves=mirror,
            lower_sha256=hashlib.sha256(lower).hexdigest(),
            upper_sha256=hashlib.sha256(upper).hexdigest(),
            first_and_second_pass_identical=True, capacity_confirmed=False,
            note='Exact repetition is consistent with address aliasing, not a JEDEC capacity reading.')
        print('同次上电的低、高 16 MiB ' + ('逐字节完全重复，符合 16 MiB 地址回绕。' if mirror else
              '内容不同，已保存两份完整地址记录，等待核对。'), flush=True)
        print('这是地址空间记录，仍不自动认定物理容量，不可直接当作刷机包。', flush=True)
    else:
        print('两份 16 MiB 范围备份完全一致。尚需确认芯片总容量，暂不称为完整固件备份。', flush=True)
