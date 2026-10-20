"""Read-only extraction/disassembly of the known CODE_PL from one's own dump."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from u15l.prepare import unpack
from u15l.profiles import L01,PROFILES,get_profile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
p=argparse.ArgumentParser(description='只读反汇编：严格核对所选固件原版指纹。')
p.add_argument('backup')
p.add_argument('--firmware',choices=tuple(PROFILES),default=L01.firmware,
               help='完整原固件版本；默认 L01 保留原调用方式')
p.add_argument('--address',type=lambda x:int(x,0),help='默认使用所选版本的校验函数入口')
p.add_argument('--length',type=lambda x:int(x,0),default=0x300)
a=p.parse_args()
profile=get_profile(L01.board,L01.soc,a.firmware)
plain,_=unpack(Path(a.backup).read_bytes(),profile)
address=profile.load_address+profile.patch_offset if a.address is None else a.address
at=address-profile.load_address
if a.length<=0 or at<0 or at+a.length>len(plain):raise SystemExit('Address outside known CODE_PL')
for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(plain[at:at+a.length],address):print(f'{i.address:08x} {i.mnemonic:8} {i.op_str}')
