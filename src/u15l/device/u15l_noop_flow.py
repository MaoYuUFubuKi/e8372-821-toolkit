"""Exact fixed metadata transfer; no images, erase ranges or executable code."""
import hashlib, struct, time
from u15l_noop_package import make_noop_package
PREAMBLE=bytes.fromhex('00d3022b')
TIM,FBF=make_noop_package()
assert hashlib.sha256(TIM).hexdigest()=='41b7b621959211798891193470b77a4298fe11b48e1af1e3c5268f89fc2e2c9a'
assert hashlib.sha256(FBF).hexdigest()=='9e5fcd1182de4043f0983fa7aa53fbad64db73b3a26f160e13938d4712c69c9a'
def frame(op,seq=0,data=b''):return struct.pack('<BBBBI',op,seq,0,0,len(data))+data
ALLOWED={PREAMBLE,frame(0x20),frame(0x26),frame(0x2b),frame(0x27,data=b'\0'),frame(0x30)}
for payload in (TIM,FBF):
    ALLOWED.add(frame(0x2a,1,struct.pack('<I',len(payload))))
    ALLOWED.add(frame(0x22,2,payload))

def run_noop(exchange,delay=time.sleep):
    notifications=[]
    def query(request):
        assert request in ALLOWED
        r=exchange(request)
        if request==frame(0x2b) and r==bytes.fromhex('2b0000010000'):return r
        if len(r)<6 or r[:3]!=request[:3] or r[3]!=0 or len(r)!=6+r[5]:
            raise RuntimeError('启动回应被拒绝、次序不符或不完整，已停止。')
        return r
    def messages():
        for _ in range(16):
            r=query(frame(0x2b))
            if r[5]:
                if r[5]!=6:raise RuntimeError('启动通知格式不符，已停止。')
                typ,_,code=struct.unpack('<BBI',r[6:])
                notifications.append({'type':typ,'value':code})
                if typ==1:raise RuntimeError(f'设备报告错误 0x{code:x}，已停止。')
                if typ==0 and code in (3,4,6,7,8,9,10):
                    raise RuntimeError('收到与空操作不符的通知，已停止。')
            if not r[4]&1:return
        raise RuntimeError('启动消息过多，已停止。')
    def command(request):
        r=query(request)
        if r[4]&1:messages()
        return r
    for image_id,payload in ((0x54494d48,TIM),(0x46424630,FBF)):
        r=exchange(PREAMBLE)
        if len(r)<4 or r[:3]!=PREAMBLE[:3] or r[3] not in (0,0x2b):raise RuntimeError('启动握手不符。')
        messages()
        version=command(frame(0x20))
        if version[6:]!=bytes.fromhex('313133331420010633415a4e'):raise RuntimeError('原机启动版本不匹配。')
        selected=command(frame(0x26))
        if selected[6:]!=struct.pack('<I',image_id):raise RuntimeError('设备请求的镜像与空操作包不符，停止传送。')
        command(frame(0x27,data=b'\0'))
        capacity=command(frame(0x2a,1,struct.pack('<I',len(payload))))
        if len(capacity)!=10 or not len(payload)<=struct.unpack('<I',capacity[6:])[0]<=8192:
            raise RuntimeError('设备接收缓冲区不符合已核对的流程，停止传送。')
        command(frame(0x22,2,payload))
        command(frame(0x30))
    # Completion must be a notification from the parser, not merely an ACK to Data.
    for _ in range(20):
        messages()
        if any(n=={'type':0,'value':2} for n in notifications):break
        delay(.1)
    if not any(n=={'type':0,'value':2} for n in notifications):
        raise RuntimeError('RAM 测试包已传输，但未收到解析完成通知；不能认定恢复传输已通过。')
    return {'metadata_transferred_bytes':len(TIM)+len(FBF), 'image_entries':0,
            'erase_all':False,'flash_written':False,'external_code_loaded':False,
            'metadata_parse_ready':True,'hardware_restore_tested':False,
            'notifications':notifications}
