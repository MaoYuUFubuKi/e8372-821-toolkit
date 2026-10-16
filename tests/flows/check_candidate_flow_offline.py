"""Exercise chunking, sequence wrap, guards and error handling without USB."""
import json,struct
from pathlib import Path
from u15l_candidate_flow import transfer_candidate

from u15l_candidate_package import make_candidate_package
from install_u15l_candidate import candidate_policy
from u15l_recovery_package import make_restore_package
from restore_u15l_original import OUT
from u15l_noop_flow import PREAMBLE

ORIGINAL=(OUT/'original-window.bin').read_bytes()
PAYLOAD=(OUT/'candidate-window.bin').read_bytes()
TIM,FBF=make_candidate_package(PAYLOAD,ORIGINAL)
def case(kind):
    allowed=candidate_policy(PAYLOAD,ORIGINAL);sent=[];images=[];buf=bytearray();seq=0;remaining=0;ready=False
    def exchange(req):
        nonlocal seq,remaining,ready,buf
        assert req in allowed
        sent.append(req)
        if req==PREAMBLE:return PREAMBLE
        op,qseq=req[:2]
        def reply(data=b'',status=0):return bytes([op,qseq,0,status,0,len(data)])+data
        if op==0x2b:
            if len(images)==2 and not ready:
                ready=True
                if kind=='no_ready':return reply(status=1)
                if kind=='device_error':return reply(bytes([1,0])+struct.pack('<I',0x21))
                return reply(bytes([0,0])+struct.pack('<I',2))
            return reply(status=1)
        if op==0x20:return reply(bytes.fromhex('313133331420010633415a4e'))
        if op==0x26:
            iid=0x54494d48 if not images else 0x46424630
            if kind=='wrong_image' and images:iid=0x4f424d49
            return reply(struct.pack('<I',iid))
        if op==0x27:seq=0;return reply()
        if op==0x2a:
            seq=(seq+1)&255;assert qseq==seq
            remaining=struct.unpack('<I',req[8:])[0]
            assert remaining==len((TIM,FBF)[len(images)])-len(buf)
            size=min(8184,remaining)
            if kind=='buffer_change' and images:size-=1
            return reply(struct.pack('<I',size))
        if op==0x22:
            seq=(seq+1)&255;assert qseq==seq
            assert len(req)-8==min(8184,remaining)
            if kind=='data_error' and images:return reply(status=1)
            buf+=req[8:];return reply()
        if op==0x30:
            assert bytes(buf)==(TIM,FBF)[len(images)]
            images.append(bytes(buf));buf=bytearray();return reply()
        raise AssertionError(op)
    failed=False
    try:result=transfer_candidate(exchange,PAYLOAD,ORIGINAL,delay=lambda _:None)
    except RuntimeError:failed=True
    assert failed==(kind!='success'),kind
    if not failed:
        assert result['transfer_and_device_ready'] and not result['hardware_readback_verified']
        assert len(images)==2
        assert any(f[0]==0x22 and f[1]==0 for f in sent), 'sequence wrap not exercised'
    return {'case':kind,'expected_result':True,'image_count_fully_sent':len(images)}

if __name__=='__main__':
    results=[case(k)for k in ('success','wrong_image','buffer_change','data_error','device_error','no_ready')]
    bad=bytearray(PAYLOAD);bad[0]^=1
    try:make_candidate_package(bytes(bad),ORIGINAL)
    except RuntimeError:results.append({'case':'unrecognized_candidate_rejected_before_usb','expected_result':True})
    else:raise AssertionError('Modified payload accepted')
    print(json.dumps(results,indent=2))
