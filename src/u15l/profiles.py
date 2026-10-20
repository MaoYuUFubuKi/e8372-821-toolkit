"""Exact, immutable firmware profiles; a similar version name is never enough."""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class FirmwareProfile:
    id: str
    board: str
    soc: str
    firmware: str
    plain_sha256: str
    plain_bytes: int
    compressed_header_hex: str
    patch_offset: int
    patch_original_hex: str
    patch_replacement_hex: str
    load_address: int
    emulation: Mapping

    def __post_init__(self):
        object.__setattr__(self, 'emulation', MappingProxyType(dict(self.emulation)))

    def to_record(self):
        return {name: dict(value) if name == 'emulation' else value
                for name, value in vars(self).items()}


L01 = FirmwareProfile(
    id='u15l-c01-mt02b01v15-l01',
    board='8BC010-U15L_V1.03',
    soc='ASR1803S',
    firmware='U15L-MT02B01V15-L01',
    plain_sha256='e42836f86fdcef5c1ab13061efa0429c9f9ee4c7e4f4daf2ec7b47a85d7c2daf',
    plain_bytes=0x294fb4,
    compressed_header_hex='5d00001000b44f290000000000',
    patch_offset=0x88cfa,
    patch_original_hex='2de9f043',
    patch_replacement_hex='01207047',
    load_address=0x06882000,
    emulation={
        'variant': 'l01',
        'task_start': 0x0690ae52,
        'task_end': 0x0690af7a,
        'url_selection_literal': 0x0690afe8,
        'dedicated_url': 0x06b162bb,
        'callsites': (0x0690af00, 0x0690af0a),
        'delay': 0x0699ac68,
        'memset': 0x0696b2ec,
        'configuration': 0x066d3894,
        'readiness': (0x069a26b8, 0x066d3ce8),
        'logging': 0x0699d68c,
        'disconnect': 0x0663db14,
        'deny_flag': 0x06b72d1c,
    },
)

M02 = FirmwareProfile(
    id='u15l-c01-mt02b01v15-m02',
    board='8BC010-U15L_V1.03',
    soc='ASR1803S',
    firmware='U15L-MT02B01V15-M02',
    plain_sha256='ef0506f5e4669e9501370e459f5987c12cc6fe2019d7e02158ba869cbc5054e4',
    plain_bytes=2707040,
    compressed_header_hex='5d00001000604e290000000000',
    patch_offset=0x88cee,
    patch_original_hex='2de9f043',
    patch_replacement_hex='01207047',
    load_address=0x06882000,
    emulation={
        'variant': 'm02',
        'task_start': 0x0690ae54,
        'task_end': 0x0690af4a,
        'url_selection_literal': 0x0690afb0,
        'url_table_offset': 8,
        'callsites': (0x0690aeee,),
        'delay': 0x0699d268,
        'memset': 0x0696d8e0,
        'configuration': 0x066d3894,
        'readiness': (0x069a4cb8, 0x066d3ce8),
        'logging': 0x0699fc8c,
        'disconnect': 0x0663db14,
        'deny_flag': 0x06b72d1c,
    },
)

# New firmware is registered only after its instructions and task are verified.
PROFILES = MappingProxyType({p.firmware: p for p in (L01, M02)})


def require_profile(profile=None):
    profile = L01 if profile is None else profile
    if not isinstance(profile, FirmwareProfile) or PROFILES.get(profile.firmware) is not profile:
        raise RuntimeError('固件配置未注册；不能通过自定义参数跳过版本验证。')
    return profile


def get_profile(board, soc, firmware):
    profile = PROFILES.get(firmware)
    if profile is None or (board, soc) != (profile.board, profile.soc):
        raise RuntimeError('只适配已验证的板号、主控及固件；不要根据外壳或相似后缀推断。')
    return profile
