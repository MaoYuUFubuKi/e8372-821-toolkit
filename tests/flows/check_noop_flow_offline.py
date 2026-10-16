"""Fail-closed transport fixtures for the zero-image metadata test."""
import json,struct
from u15l_noop_flow import run_noop,ALLOWED,TIM,FBF,frame,PREAMBLE
assert struct.unpack_from('<I',TIM,0x28)[0]==0x5350491b
assert struct.unpack_from('<I',TIM,56+8)[0]==0xffffffff
assert struct.unpack_from('<I',FBF,0x144)[0]==0
assert struct.unpack_from('<I',FBF,0x148)[0]==0
assert struct.unpack_from('<I',FBF,0x1f0)[0]==0

def case(kind):
    sent=[];completed=0;ready=False
    def exchange(req):
        nonlocal completed,ready
        assert req in ALLOWED
        sent.append(req)
        if req==PREAMBLE:return PREAMBLE
        op,seq=req[:2]
        def reply(data=b'',status=0):return bytes([op,seq,0,status,0,len(data)])+data
        if op==0x2b:
            if completed==2 and not ready:
                ready=True
                if kind=='no_ready':return reply(status=1)
                if kind=='device_error':return reply(bytes([1,0])+struct.pack('<I',0x10))
                if kind=='unexpected_erase_notice':return reply(bytes([0,0])+struct.pack('<I',4))
                return reply(bytes([0,0])+struct.pack('<I',2))
            return reply(status=1)
        if op==0x20:return reply(bytes.fromhex('313133331420010633415a4e'))
        if op==0x26:
            iid=0x54494d48 if completed==0 else 0x46424630
            if kind=='wrong_image' and completed==1:iid=0x4f424d49
            return reply(struct.pack('<I',iid))
        if op==0x27:return reply()
        if op==0x2a:
            if kind=='header_nack':return reply(status=1)
            return reply(struct.pack('<I',512 if kind=='small_buffer' else 8184))
        if op==0x22:
            assert req[8:]==(TIM if completed==0 else FBF)
            if kind=='data_nack':return reply(status=1)
            if kind=='wrong_sequence':return bytes([0x22,9,0,0,0,0])
            return reply()
        if op==0x30:completed+=1;return reply()
        raise AssertionError(op)
    failed=False
    try:result=run_noop(exchange,delay=lambda _:None)
    except RuntimeError:failed=True
    assert failed==(kind!='success'),kind
    if kind in ('header_nack','small_buffer'):assert not any(f[0]==0x22 for f in sent)
    assert all(f in ALLOWED for f in sent)
    return {'case':kind,'expected_result':True,'transferred_metadata_bytes':sum(len(f)-8 for f in sent if f[0]==0x22)}

if __name__=='__main__':
    cases=['success','wrong_image','header_nack','small_buffer','data_nack','wrong_sequence','no_ready','device_error','unexpected_erase_notice']
    print(json.dumps([case(c) for c in cases],indent=2))
