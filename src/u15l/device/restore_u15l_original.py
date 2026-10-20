"""Original-only recovery, guarded by original boot identity and two-pass readbacks.

Three fresh boot sessions: backup -> original range restore -> readback verification.
No arbitrary input filenames, offsets, chip types, or modified-image mode.
"""
from contextlib import contextmanager
from pathlib import Path
import datetime,hashlib,json,os,shutil,sys,time
import u15l_backup
from u15l_noop_flow import frame,PREAMBLE
from u15l_recovery_package import make_restore_package,ORIGINAL_SHA,START,SIZE
from u15l_restore_flow import transfer_restore

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/firmware'
BACKUPS=ROOT/'outputs/backup'
SOURCE_SHA='__SOURCE_SHA__'
def sha(b):return hashlib.sha256(b).hexdigest()

@contextmanager
def session(log,phase,policy,expected_port=None):
    import libusb_package
    import usb.core
    import usb.util
    backend=libusb_package.get_libusb1_backend()
    if backend is None:raise RuntimeError('无法加载 USB 通信库。')
    if not list(usb.core.find(find_all=True,backend=backend)):raise RuntimeError('USB 不可访问，请手动运行恢复程序。')
    def find():
        ds=list(usb.core.find(find_all=True,backend=backend,idVendor=0x2ecc,idProduct=0x3001))
        if len(ds)>1:raise RuntimeError('发现多台启动设备，已停止。')
        return ds
    print(f'\n{phase}：程序已就绪。请拔下设备，等 3 秒，再插回同一接口。',flush=True)
    print('不要按复位键。按本窗口提示操作，保持连接直到本阶段结束。',flush=True)
    deadline=time.monotonic()+180;dev=None;claimed=False
    try:
        while find():
            if time.monotonic()>deadline:raise RuntimeError('等待拔插超时。')
            time.sleep(.05)
        while time.monotonic()<deadline:
            ds=find()
            if not ds:time.sleep(.05);continue
            dev=ds[0]
            try:
                if dev.product!='WUKONG':raise RuntimeError('USB 设备名不符。')
                try:cfg=dev.get_active_configuration()
                except usb.core.USBError as exc:
                    if 'Configuration not set' not in str(exc):raise
                    dev.set_configuration(1);cfg=dev.get_active_configuration()
                itf=cfg[(0,0)]
                if cfg.bConfigurationValue!=1 or sorted((e.bEndpointAddress,e.bmAttributes&3,e.wMaxPacketSize) for e in itf)!=[(2,2,512),(129,2,512)]:
                    raise RuntimeError('USB 接口布局不符。')
                usb.util.claim_interface(dev,0);claimed=True;break
            except usb.core.USBError as exc:
                log('open_retry',error=str(exc));usb.util.dispose_resources(dev);dev=None;time.sleep(.05)
        if not claimed:raise RuntimeError('捕获启动接口超时。')
        port=(dev.bus,tuple(dev.port_numbers or ()))
        if expected_port is not None and expected_port!=port:raise RuntimeError('USB 物理端口变化，已停止。')
        log('usb_session',phase=phase,physical_port=port)
        count=0
        def exchange(data,label=''):
            nonlocal count
            if data not in policy or count>=16000:raise RuntimeError('拒绝未允许的通信数据。')
            count+=1
            if data[0]!=0x33:log('request',phase=phase,op=hex(data[0]),size=len(data),sha256=sha(data))
            if dev.write(2,data,timeout=10000)!=len(data):raise RuntimeError('USB 数据发送不完整，停止。')
            reply=bytes(dev.read(0x81,8192,timeout=30000))
            if data[0]!=0x33:log('response',phase=phase,hex=reply[:64].hex(),size=len(reply))
            if not reply or reply[0]!=data[0]:raise RuntimeError('USB 回应次序不匹配，停止。')
            return reply
        yield exchange,port
    finally:
        if dev is not None:
            if claimed:
                try:usb.util.release_interface(dev,0)
                except usb.core.USBError:pass
            usb.util.dispose_resources(dev)

READ_POLICY={PREAMBLE,frame(0x34),frame(0x35),frame(0x2b),frame(0x30),frame(0x33),*u15l_backup.HEADERS}
def acquire(exchange,log,stem):
    def query(op):
        if op not in (0x34,0x35,0x2b):raise RuntimeError('读取阶段拒绝其他命令。')
        return exchange(frame(op),'read query')
    def drain():
        for _ in range(16):
            r=query(0x2b)
            if len(r)<6:raise RuntimeError('读取消息不完整。')
            if not r[4]&1:return
        raise RuntimeError('读取通知过多。')
    def finish():
        r=exchange(frame(0x30),'read done')
        if len(r)!=6 or r[3]!=0:raise RuntimeError('读取区域未正常结束。')
        if r[4]&1:drain()
    r=exchange(PREAMBLE,'read preamble')
    if len(r)<4 or r[:3]!=PREAMBLE[:3] or r[3] not in (0,0x2b):raise RuntimeError('读取握手失败。')
    proto=query(0x34)
    if len(proto)!=10 or proto[3]!=0 or proto[6:]!=bytes.fromhex('01010000'):raise RuntimeError('读取协议不符。')
    if proto[4]&1:drain()
    params=query(0x35)
    if len(params)!=22 or params[3]!=0 or params[6:10]!=bytes.fromhex('00200000'):raise RuntimeError('读取缓冲参数不符。')
    if params[4]&1:drain()
    u15l_backup.acquire(exchange,query,drain,finish,log,OUT,stem)
    return (OUT/f'{stem}-闪存前16MiB-读取1.bin').read_bytes()

def write_policy(payload):
    tim,fbf=make_restore_package(payload)
    allowed={PREAMBLE,frame(0x20),frame(0x26),frame(0x2b),frame(0x27,data=b'\0'),frame(0x30)}
    for image in (tim,fbf):
        at=0;seq=0
        while at<len(image):
            seq=(seq+1)&255
            allowed.add(frame(0x2a,seq,(len(image)-at).to_bytes(4,'little')))
            seq=(seq+1)&255;chunk=image[at:at+8184]
            allowed.add(frame(0x22,seq,chunk));at+=len(chunk)
    return allowed

def main():
    stem='原版恢复-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    report=OUT/(stem+'.json')
    state={'started':datetime.datetime.now().astimezone().isoformat(),'events':[],
           'mode':'original_only','flash_write_may_have_started':False,'restore_readback_verified':False}
    def log(kind='restore',**values):
        if values.get('flash_write_may_start'):state['flash_write_may_have_started']=True
        state['events'].append({'kind':kind,**values})
        report.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');report.chmod(0o600)
    try:
        originals=[(BACKUPS/f'original-copy{i}.bin').read_bytes() for i in (1,2)]
        if originals[0]!=originals[1] or sha(originals[0])!=SOURCE_SHA:raise RuntimeError('两份原机备份核验失败。')
        original=originals[0]
        payload=(OUT/'original-window.bin').read_bytes()
        if payload!=original[START:START+SIZE] or sha(payload)!=ORIGINAL_SHA:raise RuntimeError('原版恢复数据核验失败。')
        make_restore_package(payload)
        if shutil.disk_usage(OUT).free<160*1024*1024:raise RuntimeError('剩余磁盘空间不足，停止。')
        log('preflight_ok',source_sha256=SOURCE_SHA,restore_sha256=ORIGINAL_SHA)
        print('本程序会实际恢复原版固件的 1.25 MiB 区域；没有修改版刷入功能。',flush=True)
        print('分三阶段，每阶段需按提示拔插一次：备份现状 → 恢复原版 → 重新读回核验。',flush=True)
        with session(log,'阶段 1/3 备份现状',READ_POLICY) as (exchange,port):
            before=acquire(exchange,log,stem+'-写入前')
        if before[:0x20000]!=original[:0x20000]:raise RuntimeError('当前设备启动程序与原机备份不符，禁止写入。')
        state['prewrite_window_was_original']=before[START:START+SIZE]==payload
        log('device_identity_verified',boot_sha256=sha(before[:0x20000]))
        with session(log,'阶段 2/3 恢复原版，完成前请勿断电',write_policy(payload),port) as (exchange,_):
            state['write_result']=transfer_restore(exchange,payload,log=lambda **v:log('write_progress',**v))
        print('原版恢复命令已完成；接下来必须完整读回核验，不能仅凭写入通知认定成功。',flush=True)
        with session(log,'阶段 3/3 读回核验',READ_POLICY,port) as (exchange,_):
            after=acquire(exchange,log,stem+'-写入后')
        if after[START:START+SIZE]!=payload:raise RuntimeError('恢复区间读回不一致；停止，保留日志并重新核对。')
        protected=[(0,START),(START+SIZE,0x980000),(0xb20000,0x1000000)]
        if any(before[a:b]!=after[a:b] for a,b in protected):raise RuntimeError('写入范围外的受保护数据发生变化，需分析日志。')
        state['restore_readback_verified']=True
        state['restored_window_sha256']=sha(after[START:START+SIZE])
        state['protected_ranges_unchanged']=[[hex(a),hex(b)] for a,b in protected]
        state['changed_64KiB_blocks']=[hex(i)for i in range(0,len(after),0x10000)if before[i:i+0x10000]!=after[i:i+0x10000]]
        log('restore_verified')
        print('原版恢复成功：写入范围两遍读回一致，并与原版逐字节相同；受保护区域未改变。',flush=True)
        return 0
    except Exception as exc:
        state['error']=str(exc);log('stopped',reason=str(exc))
        print('程序停止：'+str(exc),flush=True)
        if state['flash_write_may_have_started']:
            print('写入阶段已经开始过；请保留本记录。此程序可在重新上电后再次恢复同一原版区间。',flush=True)
        return 1
    finally:
        log('finished',time=datetime.datetime.now().astimezone().isoformat())
        print('记录位置：'+str(report),flush=True)
        print('结束后拔下再插入，让设备正常启动。',flush=True)

if __name__=='__main__':sys.exit(main())
