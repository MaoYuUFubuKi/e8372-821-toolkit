"""Restore only the hash-pinned original 1.25 MiB range using original OBM.

USB exchange is supplied by the caller. This module has no hardware discovery.
Always verify the whole written range in a fresh readback session afterwards.
"""
import hashlib,struct,time
from u15l_noop_flow import PREAMBLE,frame
from u15l_recovery_package import make_restore_package

def transfer_restore(exchange,payload,log=lambda **_:None,delay=time.sleep):
    tim,fbf=make_restore_package(payload)
    notices=[]
    def query(req):
        r=exchange(req)
        if req==frame(0x2b) and r==bytes.fromhex('2b0000010000'):return r
        if len(r)<6 or r[:3]!=req[:3] or r[3]!=0 or len(r)!=6+r[5]:
            raise RuntimeError('设备拒绝恢复传输，或回应不完整；已停止，不自动重试写入。')
        return r
    def messages():
        for _ in range(64):
            r=query(frame(0x2b))
            if r[5]:
                if r[5]!=6:raise RuntimeError('恢复通知格式错误。')
                typ,_,value=struct.unpack('<BBI',r[6:]);notices.append((typ,value))
                log(notification_type=typ,notification_value=value)
                if typ==1:raise RuntimeError(f'启动程序报告错误 0x{value:x}；需重新上电后核对。')
                if typ==0 and value in (3,4,6,7,8,9,10):
                    raise RuntimeError('出现未允许的全片擦除/熔丝通知，已停止。')
            if not r[4]&1:return
        raise RuntimeError('恢复通知超出限制。')
    def command(req):
        r=query(req)
        if r[4]&1:messages()
        return r
    for iid,image in ((0x54494d48,tim),(0x46424630,fbf)):
        r=exchange(PREAMBLE)
        if len(r)<4 or r[:3]!=PREAMBLE[:3] or r[3] not in (0,0x2b):raise RuntimeError('启动握手失败。')
        messages()
        version=command(frame(0x20))
        if version[6:]!=bytes.fromhex('313133331420010633415a4e'):raise RuntimeError('启动版本不符。')
        selected=command(frame(0x26))
        if selected[6:]!=struct.pack('<I',iid):raise RuntimeError('请求镜像不符；未继续传输。')
        command(frame(0x27,data=b'\0'))
        seq=0;at=0
        while at<len(image):
            seq=(seq+1)&255
            r=command(frame(0x2a,seq,struct.pack('<I',len(image)-at)))
            expected=min(8184,len(image)-at)
            if len(r)!=10 or struct.unpack('<I',r[6:])[0]!=expected or r[4]&4:
                raise RuntimeError('设备缓冲区大小或传输模式不符，停止传输。')
            seq=(seq+1)&255
            command(frame(0x22,seq,image[at:at+expected]))
            at+=expected
        log(image_received_by_device=hex(iid),bytes=len(image),sha256=hashlib.sha256(image).hexdigest())
        if iid==0x46424630:
            log(flash_write_may_start=True,start='0x480000',end_exclusive='0x5c0000')
        command(frame(0x30))
    for _ in range(600):
        messages()
        if (0,2) in notices:break
        delay(.1)
    if (0,2) not in notices:raise RuntimeError('未收到恢复完成通知；必须重新上电读回核对。')
    return {'transfer_and_device_ready':True,'hardware_readback_verified':False,
            'notifications':notices,'written_start':'0x480000','written_end_exclusive':'0x5c0000'}
