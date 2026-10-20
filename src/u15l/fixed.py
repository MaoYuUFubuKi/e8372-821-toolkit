"""Optional, pinned CODE_PL component; never a donor's complete flash image."""
import json,lzma
from .common import ROOT,PROFILE,SOURCE_PLAIN_SHA,sha
from .profiles import L01,require_profile

FILENAME='code-pl-u15l-mt02b01v15-l01-patched.lzma'
PAYLOAD_SHA='423e5f4ad63f4b9fe39a6c3929b07679944e4d57d179c4c2f87af2ecc509480b'
PATCHED_PLAIN_SHA='3f74bce775641314d6e57a49a720413d584f37b0dbf286c52739843fb8894a32'
PAYLOAD_BYTES=1268216

def validate_payload(payload,profile=None):
    profile=require_profile(profile)
    if profile is not L01:
        raise RuntimeError('此固件没有已验证的固定组件；请明确选择 --method local。')
    if len(payload)!=PAYLOAD_BYTES or sha(payload)!=PAYLOAD_SHA:
        raise RuntimeError('固定组件损坏或不是已验证的版本；停止，不自动改走另一条刷写路线。')
    d=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    plain=d.decompress(payload,max_length=0x294fb4+1)
    if not d.eof or d.unused_data or len(plain)!=0x294fb4 or sha(plain)!=PATCHED_PLAIN_SHA:
        raise RuntimeError('固定组件解压校验失败。')
    return plain

def load_fixed(root=ROOT,profile=None):
    profile=require_profile(profile)
    # L01's optional component is never considered for another exact profile.
    if profile is not L01:return None
    path=root/'firmware'/FILENAME;manifest=root/'firmware/manifest.json'
    if not path.exists() and not manifest.exists():return None
    if not path.is_file() or not manifest.is_file() or path.is_symlink() or manifest.is_symlink():
        raise RuntimeError('固定组件不完整；请重新取得完整文件，或明确选择 --method local。')
    record=json.loads(manifest.read_text())
    required={'profile':PROFILE,'file':FILENAME,'bytes':PAYLOAD_BYTES,'sha256':PAYLOAD_SHA,
              'source_plain_sha256':SOURCE_PLAIN_SHA,'patched_plain_sha256':PATCHED_PLAIN_SHA,
              'target_start':'0x481000','target_end_exclusive':'0x5b7000'}
    if any(record.get(k)!=v for k,v in required.items()):raise RuntimeError('固定组件清单不匹配。')
    if path.stat().st_size!=PAYLOAD_BYTES:raise RuntimeError('固定组件长度不匹配。')
    payload=path.read_bytes();validate_payload(payload)
    return payload
