"""Only read flash and send the previously verified metadata-only no-op."""
from pathlib import Path
import datetime,json,os,struct
from .common import case_path,Recorder,save_json,verify_runtime,sha,now

def collect(name,mirror=False):
    verify_runtime()
    import restore_u15l_original as core
    import u15l_backup as reader
    from u15l_noop_flow import ALLOWED,run_noop,PREAMBLE,frame
    case=case_path(name);case.mkdir(parents=True,exist_ok=True)
    if (case/'backup.json').exists():raise RuntimeError('该设备目录已有已验证备份；请使用新目录名，不覆盖旧备份。')
    raw=case/'raw'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');raw.mkdir(parents=True)
    record=Recorder(raw/'acquisition.json')
    try:
        print('这一步只读闪存，再发送无擦写项目的 5 KiB 元数据；需按提示拔插两次。',flush=True)
        policy=core.READ_POLICY | (set(reader.ADDRESS_HEADERS) if mirror else set())
        with core.session(record.log,'备份 1/2 读取自己的设备',policy) as (exchange,port):
            if not mirror:
                core.OUT=raw
                image=core.acquire(exchange,record.log,'backup')
                copies=[raw/f'backup-闪存前16MiB-读取{i}.bin' for i in (1,2)]
            else:
                def query(op):
                    if op not in (0x34,0x35,0x2b):raise RuntimeError('只读阶段禁止其他命令。')
                    return exchange(frame(op))
                def drain():
                    for _ in range(16):
                        r=query(0x2b)
                        if len(r)<6:raise RuntimeError('消息不完整。')
                        if not r[4]&1:return
                    raise RuntimeError('消息异常。')
                def finish():
                    r=exchange(frame(0x30))
                    if len(r)!=6 or r[3]!=0:raise RuntimeError('区域结束失败。')
                    if r[4]&1:drain()
                r=exchange(PREAMBLE)
                if len(r)<4 or r[:3]!=PREAMBLE[:3] or r[3] not in (0,0x2b):raise RuntimeError('握手失败。')
                for op,expected in ((0x34,bytes.fromhex('01010000')),(0x35,None)):
                    r=query(op)
                    if op==0x34 and (len(r)!=10 or r[3]!=0 or r[6:]!=expected):raise RuntimeError('协议不符。')
                    if op==0x35 and (len(r)!=22 or r[3]!=0 or r[6:10]!=bytes.fromhex('00200000')):raise RuntimeError('参数不符。')
                    if r[4]&1:drain()
                reader.acquire(exchange,query,drain,finish,record.log,raw,'capture',address_space=True)
                copies=[]
                for i in (1,2):
                    image=(raw/f'capture-零至32MiB地址记录-读取{i}.bin').read_bytes()
                    if image[:0x1000000]!=image[0x1000000:]:raise RuntimeError('高低地址不重复；当前仅支持已识别的 16 MiB 配置。')
                    dest=raw/f'backup-闪存前16MiB-读取{i}.bin';dest.write_bytes(image[:0x1000000]);copies.append(dest)
        with core.session(record.log,'备份 2/2 核对恢复通道和容量',ALLOWED,port) as (exchange,_):
            probe=run_noop(exchange)
        if not {'type':4,'value':0x1000000} in probe['notifications']:
            raise RuntimeError('启动程序未报告预期的 16 MiB 容量，禁止准备修改版。')
        blobs=[p.read_bytes() for p in copies]
        if blobs[0]!=blobs[1] or len(blobs[0])!=0x1000000:raise RuntimeError('备份不一致。')
        for p in copies:p.chmod(0o400)
        result={'profile':None,'hardware_profile':'u15l-asr1803s-16mib','captured_at':now(),
                'copies':[str(p.relative_to(case)) for p in copies],'source_sha256':sha(blobs[0]),
                'bytes_per_copy':0x1000000,'metadata_noop':probe,
                'physical_port':port,'mirror_test':mirror,'otp_included':False}
        save_json(case/'backup.json',result)
        record.log('complete',source_sha256=result['source_sha256'])
        print('自己的两份主闪存备份一致，恢复通道和报告容量已匹配。请重新拔插让设备正常启动。')
        print('下一步：核对管理页固件版本，再运行 ./run.sh prepare '+name+' --board 8BC010-U15L_V1.03 --soc ASR1803S --firmware <实际完整版本>')
    except Exception as e:
        record.log('stopped',error=str(e));raise
