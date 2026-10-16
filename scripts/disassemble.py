"""Read-only extraction/disassembly of the known CODE_PL from one's own dump."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from u15l.prepare import unpack
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
p=argparse.ArgumentParser();p.add_argument('backup');p.add_argument('--address',type=lambda x:int(x,0),default=0x0690acfa);p.add_argument('--length',type=lambda x:int(x,0),default=0x300);a=p.parse_args()
plain,_=unpack(Path(a.backup).read_bytes());base=0x06882000;at=a.address-base
if at<0 or at+a.length>len(plain):raise SystemExit('Address outside known CODE_PL')
for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(plain[at:at+a.length],a.address):print(f'{i.address:08x} {i.mnemonic:8} {i.op_str}')
