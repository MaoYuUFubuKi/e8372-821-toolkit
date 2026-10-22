"""Offline preparation: build from TWO backups of the user's own matching device.

Generated writers retain exact payload hashes, original-only recovery, fixed flash
bounds, and five-stage restore-before-patch behavior from the successful case.
"""
from pathlib import Path
import json,lzma,os,shutil,zipfile
from .common import *
from .fixed import load_fixed,validate_payload
from .profiles import get_profile,require_profile

def unpack(blob,profile=None):
    profile=require_profile(profile)
    if len(blob)!=0x1000000:raise RuntimeError('只接受 16 MiB 主闪存备份。')
    if sha(blob[:4096])!=PREFIX_SHA or sha(blob[0x6000:0x6000+0x165ac])!=OBM_SHA:
        raise RuntimeError('TIM/原机 OBM 指纹不匹配；不支持此固件，不能强行跳过。')
    packed=blob[0x481000:0x5b7000]
    if packed[:13]!=bytes.fromhex(profile.compressed_header_hex):raise RuntimeError('压缩头与所选固件不匹配。')
    d=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE);plain=d.decompress(packed,max_length=profile.plain_bytes+1)
    if not d.eof or len(plain)!=profile.plain_bytes or sha(plain)!=profile.plain_sha256:
        raise RuntimeError('CODE_PL 版本指纹不匹配；只能研究，不能刷写。')
    at=profile.patch_offset;expected=bytes.fromhex(profile.patch_original_hex)
    if plain[at:at+len(expected)]!=expected:raise RuntimeError('函数入口指令不匹配。')
    return plain,packed[:13]

def patch(blob,profile=None):
    profile=require_profile(profile)
    plain,header=unpack(blob,profile);patched=bytearray(plain)
    at=profile.patch_offset;replacement=bytes.fromhex(profile.patch_replacement_hex)
    if len(replacement)!=len(bytes.fromhex(profile.patch_original_hex)):raise RuntimeError('补丁指令长度不匹配。')
    patched[at:at+len(replacement)]=replacement
    filters=[{'id':lzma.FILTER_LZMA1,'dict_size':1<<20,'lc':3,'lp':0,'pb':2,
              'mode':lzma.MODE_NORMAL,'mf':lzma.MF_BT4,'nice_len':64}]
    compressed=lzma.compress(bytes(patched),format=lzma.FORMAT_ALONE,filters=filters)
    # Python 3.14 的 lzma 拒绝“已知大小头+EOSM 数据”的组合；分别校验两端即可：
    # 压缩流自身用 FORMAT_ALONE，换头后的数据段用 FORMAT_RAW。
    if lzma.decompress(compressed,format=lzma.FORMAT_ALONE)!=patched:
        raise RuntimeError('重压缩数据校验失败。')
    packed=header+compressed[13:]
    if len(packed)>0x136000:
        raise RuntimeError('重压缩后大小超出窗口。')
    decoder=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=filters)
    if decoder.decompress(compressed[13:],max_length=len(patched)+1)!=patched:
        raise RuntimeError('换头后数据校验失败。')
    candidate=bytearray(blob);candidate[0x481000:0x5b7000]=packed+bytes(0x136000-len(packed))
    if candidate[:0x481000]!=blob[:0x481000] or candidate[0x5b7000:]!=blob[0x5b7000:]:raise RuntimeError('越界修改。')
    return bytes(candidate),bytes(patched),plain

def select_candidate(blob,method='auto',profile=None):
    profile=require_profile(profile)
    if method not in ('auto','fixed','local'):raise ValueError('未知准备方式。')
    # Validate the user's original before considering either route.
    plain,header=unpack(blob,profile)
    if method!='local':
        payload=load_fixed(profile=profile)
        if payload is not None:
            patched=validate_payload(payload,profile)
            at=profile.patch_offset;replacement=bytes.fromhex(profile.patch_replacement_hex)
            expected=bytearray(plain);expected[at:at+len(replacement)]=replacement
            if patched!=expected or payload[:13]!=header:raise RuntimeError('固定组件与本机原代码的差异超出已验证修改。')
            candidate=bytearray(blob)
            candidate[0x481000:0x5b7000]=payload+bytes(0x136000-len(payload))
            if candidate[:0x481000]!=blob[:0x481000] or candidate[0x5b7000:]!=blob[0x5b7000:]:
                raise RuntimeError('固定组件越界修改。')
            return bytes(candidate),patched,plain,'fixed'
        if method=='fixed':raise RuntimeError('未附带固定组件；可用 --method local 从自己的备份生成。')
    candidate,patched,plain=patch(blob,profile)
    return candidate,patched,plain,'local'

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(data)
    path.chmod(0o400)

def launcher(path,target):
    path.write_text('#!/bin/zsh\ncd -- "${0:A:h}" || exit 1\nPYTHONPATH="$PWD/runtime" "${U15L_PYTHON:-python3}" '+target+'\nu15l_exit_code=$?\nread -r \'?按回车关闭窗口。\'\nexit "$u15l_exit_code"\n')
    path.chmod(0o700)

def manifest(folder):
    lines=[]
    for p in sorted(folder.rglob('*')):
        if p.is_file() and p.name!='SHA256SUMS' and '__pycache__' not in p.parts:
            lines.append(sha(p.read_bytes())+'  '+p.relative_to(folder).as_posix())
    data=('\n'.join(lines)+'\n').encode();(folder/'SHA256SUMS').write_bytes(data);return sha(data)

def prepare(name,board,soc,firmware,method='auto'):
    profile=get_profile(board,soc,firmware)
    verify_runtime();case=case_path(name);record=json.loads((case/'backup.json').read_text())
    blobs=[]
    for rel in record['copies']:
        p=(case/rel).resolve()
        if case.resolve() not in p.parents:raise RuntimeError('备份路径越界。')
        blobs.append(p.read_bytes())
    if len(blobs)!=2 or blobs[0]!=blobs[1] or sha(blobs[0])!=record['source_sha256']:raise RuntimeError('两份自己的备份不一致。')
    probe=record['metadata_noop']
    if (probe.get('image_entries')!=0 or probe.get('flash_written') is not False or
        not probe.get('metadata_parse_ready') or {'type':4,'value':0x1000000} not in probe['notifications']):
        raise RuntimeError('恢复通道/容量证据不符。')
    original=blobs[0];candidate,patched,plain,selected=select_candidate(original,method,profile)
    target=case/'prepared'
    if target.exists():raise RuntimeError('prepared 已存在，不覆盖；请保留旧恢复包。')
    old,new=original[START:END],candidate[START:END]
    # Complete the private workspace first; incomplete preparation is not executable.
    target.mkdir()
    profile_json=json.dumps(profile.to_record(),sort_keys=True,separators=(',',':'))
    replacements={'__SOURCE_SHA__':sha(original),'__ORIGINAL_SHA__':sha(old),'__CANDIDATE_SHA__':sha(new),
                  '__FIRMWARE_PROFILE_JSON__':profile_json.replace('\\','\\\\').replace("'","\\'")}
    for i in (1,2):write(target/f'outputs/backup/original-copy{i}.bin',original)
    for filename,data in [('original-window.bin',old),('candidate-window.bin',new)]:write(target/'outputs/firmware'/filename,data)
    for filename,data in [('u15l-original-obm.bin',original[0x6000:0x6000+0x165ac]),('u15l-decompressed-481000.bin',plain),('u15l-code-pl-patched.bin',patched),('u15l-candidate-window-only-replaced-16MiB.bin',candidate)]:
        write(target/'work/research'/filename,data)
    code=target/'work/device';code.mkdir(parents=True)
    for p in list(ENGINE.glob('*.py'))+list((ROOT/'tests/flows').glob('*.py')):
        s=p.read_text()
        for a,b in replacements.items():s=s.replace(a,b)
        (code/p.name).write_text(s)
    shutil.copytree(RUNTIME/'python',target/'runtime',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    recovery=target/'recovery';recovery.mkdir()
    shutil.copytree(target/'runtime',recovery/'runtime')
    shutil.copytree(RUNTIME/'licenses',recovery/'licenses')
    shutil.copytree(target/'outputs/backup',recovery/'outputs/backup')
    (recovery/'outputs/firmware').mkdir(parents=True)
    shutil.copy2(target/'outputs/firmware/original-window.bin',recovery/'outputs/firmware/original-window.bin')
    (recovery/'work/device').mkdir(parents=True)
    for name_ in ('restore_u15l_original.py','u15l_recovery_package.py','u15l_restore_flow.py','u15l_noop_flow.py','u15l_noop_package.py','u15l_backup.py'):
        shutil.copy2(code/name_,recovery/'work/device'/name_)
    launcher(recovery/'恢复原版.command','./work/device/restore_u15l_original.py')
    (recovery/'README.md').write_text('这是从你自己的备份生成的原版恢复包。双击恢复原版.command，依次按提示完成备份、恢复、读回三次拔插。实际恢复验证以本机日志 restore_readback_verified 为准。此包包含设备私有数据，不要发布。\n')
    bundle_sha=manifest(recovery)
    archive=target/'recovery.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(recovery.rglob('*')):
            if p.is_file():z.write(p,'recovery/'+p.relative_to(recovery).as_posix())
    archive_sha=sha(archive.read_bytes())
    p=code/'install_u15l_candidate.py';s=p.read_text().replace('__BUNDLE_MANIFEST_SHA__',bundle_sha).replace('__ARCHIVE_SHA__',archive_sha);p.write_text(s)
    launcher(target/'刷入修改版.command','./work/device/install_u15l_candidate.py')
    result={'profile':profile.id,'firmware_profile':profile.to_record(),'backup_profile_hint':record.get('profile'),
            'preparation_method':selected,'requested_method':method,'prepared_at':now(),'source_sha256':sha(original),'original_range_sha256':sha(old),
            'candidate_range_sha256':sha(new),'candidate_full_sha256':sha(candidate),'recovery_archive_sha256':archive_sha,
            'range_start':'0x480000','range_end_exclusive':'0x5c0000','bytes':END-START,
            'own_original_backup_required':True,'actual_write_performed':False}
    save_json(target/'manifest.json',result)
    print(('已使用固定程序组件' if selected=='fixed' else '已从自己的原版生成修改程序')+'，并用自己的两份备份生成独立恢复包；尚未刷写。')
    print('下一步：./run.sh check '+name+'；通过后 ./run.sh install '+name+' --write')
    return target
