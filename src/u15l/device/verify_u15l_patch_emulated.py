"""Runs original ARM/Thumb code offline in Unicorn; never opens USB."""
from pathlib import Path
import hashlib, json, random, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
from build_u15l_patch_offline import ROOT, BACKUPS, OUT, EXPECTED, LOAD, ENTRY, WINDOW_START, WINDOW_END, PROFILE
from u15l_noop_package import make_noop_package

REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR]
def sha(d): return hashlib.sha256(d).hexdigest()
def p32(v): return struct.pack('<I', v)
def u32(d, at=0): return struct.unpack_from('<I', d, at)[0]
def xor32(d):
    result = 0
    for (v,) in struct.iter_unpack('<I', d): result ^= v
    return result

def patch_abi(patched):
    results=[]
    for seed in range(32):
        uc=Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        uc.mem_map(LOAD, 0x2a0000)
        uc.mem_write(LOAD, patched)
        rng=random.Random(seed)
        before=[rng.getrandbits(32) for _ in REGS]
        before[13]=0x07008000; before[14]=0x07000001
        for r,v in zip(REGS,before): uc.reg_write(r,v)
        uc.emu_start(ENTRY|1,0x07000000,count=3)
        after=[uc.reg_read(r) for r in REGS]
        assert after[0]==1 and after[1:]==before[1:]
        assert uc.reg_read(UC_ARM_REG_PC)==0x07000000
        results.append(seed)
    return {'random_register_cases':len(results),'return':1,'registers_and_stack_preserved':True}

def task_case(code, forced_response, dedicated_url, slot=1, ready_returns=None,
              expect_complete=True):
    addresses=PROFILE['emulation']
    variant=addresses['variant']
    uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    uc.mem_map(0x06000000,0x01100000)
    uc.mem_write(LOAD,code)
    uc.reg_write(UC_ARM_REG_SP,0x070f0000)
    uc.reg_write(UC_ARM_REG_LR,0x07000001)
    # Execute the actual task; external system calls and URL state are fixtures.
    sl=u32(code,addresses['url_selection_literal']-LOAD)
    if variant=='l01':
        uc.mem_write(sl+0x14,p32(addresses['dedicated_url'] if dedicated_url else 0))
    elif variant=='m02':
        fixture_url=0x07010000
        uc.mem_write(fixture_url,b'http://fixture.invalid/check\0')
        for index in (0,1):
            uc.mem_write(sl+addresses['url_table_offset']+index*4,
                         p32(fixture_url if dedicated_url else 0))
    else:
        raise AssertionError('Unsupported task emulator profile')
    cfg=[]; disconnected=[]; callsites=[]; delays=[]; responses=[]
    pending=list(forced_response) if isinstance(forced_response,(list,tuple)) else None
    readiness=list(ready_returns or [1])
    def cstr(addr):return bytes(uc.mem_read(addr,96)).split(b'\0')[0].decode(errors='replace')
    def hook(u,addr,size,_):
        if addr in addresses['callsites']: callsites.append(hex(addr))
        ret=None
        if addr==ENTRY and forced_response is not None:
            if pending is not None:
                assert pending, 'Unexpected extra request'
                ret=pending.pop(0)
            else:
                ret=forced_response
            responses.append(ret)
        elif addr==addresses['delay']:
            delays.append(u.reg_read(UC_ARM_REG_R0));ret=0
        elif addr==addresses['memset']:
            u.mem_write(u.reg_read(UC_ARM_REG_R0),bytes(u.reg_read(UC_ARM_REG_R1)));ret=0
        elif addr==addresses['configuration']:
            cfg.append([cstr(u.reg_read(r)) for r in (UC_ARM_REG_R0,UC_ARM_REG_R2,UC_ARM_REG_R3)]);ret=0
        elif addr==addresses['readiness'][0]:ret=slot
        elif addr==addresses['readiness'][1]:
            ret=readiness.pop(0) if len(readiness)>1 else readiness[0]
        elif addr==addresses['logging']:ret=0
        elif addr==addresses['disconnect']:disconnected.append(True);ret=0
        if ret is not None:
            u.reg_write(UC_ARM_REG_R0,ret&0xffffffff)
            u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        elif not (addresses['task_start']<=addr<addresses['task_end'] or ENTRY<=addr<ENTRY+4
                  or (variant=='m02' and slot is None
                      and addresses['readiness'][0]<=addr<addresses['readiness'][0]+4)):
            raise AssertionError(f'Unexpected execution {addr:x}')
    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(addresses['task_start']|1,0x07000000,count=2000)
    completed=uc.reg_read(UC_ARM_REG_PC)==0x07000000
    assert completed==expect_complete
    if pending is not None:assert not pending
    deny=u32(uc.mem_read(addresses['deny_flag'],4))
    return {'deny_flag':deny,'configuration_calls':cfg,'disconnect_calls':len(disconnected),
            'callsites':callsites,'delays':delays,'responses':responses,'completed':completed}

def make_fbf(payload):
    # A fixture for the original OBM parser, not a USB download package.
    b=bytearray(0x1000+len(payload)); dev=0x100
    struct.pack_into('<HHIIIIII',b,0x20,11,0,len(payload),len(payload),len(payload),0,1,0)
    struct.pack_into('<I',b,0x3c,dev)
    # EraseAll, ResetBBT, skip blocks, ProductionMode and reset flags all zero.
    struct.pack_into('<I',b,dev+0xf0,1)
    struct.pack_into('<13I',b,dev+0xf4,
        0x50434830,0,len(payload),len(payload),3,1,len(payload),WINDOW_START,
        0,0,0,0,xor32(payload))
    b[0x1000:]=payload
    return bytes(b)

def run_obm(flash,fbf,fail_after=None,tim=None):
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    uc.mem_map(0x06000000,0x01200000)
    uc.mem_map(0x07800000,0x100000)
    uc.mem_map(0x07900000,0x10000)
    obm=(ROOT/'work/research/u15l-original-obm.bin').read_bytes()
    assert sha(obm)=='34a56247fa26e5c359930e43fef76ce30f5b95d2ce8ddd3f3fafcdab87f2e9f4'
    uc.mem_write(0x07800000,obm)
    header=bytearray(56);struct.pack_into('<I',header,0,0x30400);struct.pack_into('<I',header,0x2c,2)
    uc.mem_write(0x06000000,bytes(header))
    images=bytearray(192)
    struct.pack_into('<III',images,0,0x54494d48,0,0xffffffff)
    struct.pack_into('<III',images,96,0x46424630,0,0)
    uc.mem_write(0x06000400,bytes(images));uc.mem_write(0x06000800,struct.pack('<II',0x06000000,0x06000400))
    if tim is not None:uc.mem_write(0x06000000,tim)
    uc.mem_write(0x06001000,fbf)
    uc.reg_write(UC_ARM_REG_R0,0x06000800);uc.reg_write(UC_ARM_REG_SP,0x0790f000)
    uc.reg_write(UC_ARM_REG_LR,0x07900000)
    events=[]; outcome=[]
    def done(kind):outcome.append(kind);uc.emu_stop()
    def hook(u,addr,size,_):
        args=[u.reg_read(r) for r in REGS[:4]]
        ret=0
        if addr==0x078059fc:ret=0x078416b0
        elif addr==0x0780b1c8:
            assert args[1:3]==[0x06001000,0x46424630]
            u.mem_write(args[0],p32(0))
        elif addr in (0x0780a3bc,0x07805b30,0x0780a064,0x07806338,0x0780efd8,
                      0x07808850,0x078088ac,0x07805a18,0x07806648):pass
        elif addr==0x07805c44:
            assert args[:2]==[27,0]
            events.append(['flash_init_hardware_stub',27,0])
        elif addr in (0x07805bc0,0x07805bc4):raise AssertionError('Erase-all or BBT reset requested')
        elif addr==0x07806b0c:done(f'error_{args[0]:02x}');return
        elif addr==0x0780c1bc:done('complete');return
        elif addr==0x07805b60:
            start,length,device=args[:3]
            assert (start,length,device)==(WINDOW_START,WINDOW_END-WINDOW_START,0)
            events.append(['erase',hex(start),length]);flash[start:start+length]=b'\xff'*length
            if fail_after=='erase':done('simulated_power_loss_after_erase');return
        elif addr==0x07805ab0:
            start,ptr,length,device=args
            assert (start,length,device)==(WINDOW_START,WINDOW_END-WINDOW_START,0)
            payload=bytes(u.mem_read(ptr,length))
            assert all((a&b)==b for a,b in zip(flash[start:start+length],payload))
            if fail_after=='half_write':
                flash[start:start+length//2]=payload[:length//2]
                events.append(['partial_write',hex(start),length//2]);done('simulated_power_loss_during_write');return
            flash[start:start+length]=payload;events.append(['write',hex(start),length])
        elif addr==0x07805a68:
            start,ptr,length,device=args
            assert device==0 and start==WINDOW_START and length==8
            u.mem_write(ptr,bytes(flash[start:start+length]));events.append(['read',hex(start),length])
        else:raise AssertionError(hex(addr))
        u.reg_write(UC_ARM_REG_R0,ret);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
    boundaries=[0x078059fc,0x0780b1c8,0x0780a3bc,0x07805b30,0x0780a064,0x07806338,
                0x0780efd8,0x07805bc0,0x07805bc4,0x07806b0c,0x0780c1bc,0x07805b60,0x07805ab0,0x07805a68,
                0x07808850,0x078088ac,0x07805c44,0x07805a18,0x07806648]
    for address in boundaries:uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
    uc.emu_start(0x078086a4 if tim is not None else 0x07807f90,0x07900000,count=8000000)
    assert len(outcome)==1,f'No completion: PC={uc.reg_read(UC_ARM_REG_PC):x}'
    return {'outcome':outcome[0],'events':events,'flash_sha256':sha(flash)}

def main():
    original=(BACKUPS/'original-copy1.bin').read_bytes()
    assert sha(original)==EXPECTED
    plain=(ROOT/'work/research/u15l-decompressed-481000.bin').read_bytes()
    patched=(ROOT/'work/research/u15l-code-pl-patched.bin').read_bytes()
    assert len(plain)==PROFILE['plain_bytes'] and sha(plain)==PROFILE['plain_sha256']
    expected_patched=bytearray(plain)
    offset=PROFILE['patch_offset']
    assert plain[offset:offset+4].hex()==PROFILE['patch_original_hex']
    expected_patched[offset:offset+4]=bytes.fromhex(PROFILE['patch_replacement_hex'])
    assert patched==expected_patched
    result={'scope':'Offline emulation only. USB transport, real flash and boot are not tested.',
            'firmware_profile':PROFILE['id'],'firmware':PROFILE['firmware']}
    tim,noop=make_noop_package()
    flash=bytearray(original)
    result['obm_noop_full_metadata_parse']=run_obm(flash,noop,tim=tim)
    assert result['obm_noop_full_metadata_parse']['outcome']=='complete'
    assert result['obm_noop_full_metadata_parse']['events']==[['flash_init_hardware_stub',27,0]]
    assert flash==original
    result['patch_abi']=patch_abi(patched)
    result['task_original_reject']=task_case(plain,0,True)
    assert result['task_original_reject']['deny_flag']==1 and result['task_original_reject']['disconnect_calls']==1
    result['task_original_accept']=task_case(plain,1,True)
    result['task_patched_dedicated_url']=task_case(patched,None,True)
    accepted=['task_original_accept','task_patched_dedicated_url']
    if PROFILE['emulation']['variant']=='l01':
        result['task_patched_fallback_url']=task_case(patched,None,False)
        assert result['task_patched_dedicated_url']['callsites']==['0x690af00']
        assert result['task_patched_fallback_url']['callsites']==['0x690af0a']
        accepted.append('task_patched_fallback_url')
    else:
        assert result['task_original_reject']['configuration_calls']==[
            ['misc','sim_not_match','0'],['misc','sim_not_match','1'],
            ['wan','connect_disconnect','disabled']]
        for key,response,slot,ready in (
            ('task_original_missing_id_retry',[-1,1],1,None),
            ('task_original_missing_response_retry',[-2,1],1,None),
            ('task_original_wait_ready',1,1,[0,1]),
            ('task_patched_real_slot_helper',None,None,None)):
            result[key]=task_case(patched if response is None else plain,response,True,slot,ready)
            accepted.append(key)
        assert result['task_original_missing_id_retry']['delays']==[1000,1000,2000]
        assert result['task_original_missing_response_retry']['delays']==[1000,1000,6000]
        assert result['task_patched_dedicated_url']['callsites']==['0x690aeee']
        assert result['task_patched_real_slot_helper']['callsites']==['0x690aeee']
        result['task_missing_url']=task_case(plain,1,False,expect_complete=False)
        assert not result['task_missing_url']['callsites'] and result['task_missing_url']['disconnect_calls']==0
        for slot in (0,2,3):
            key=f'task_invalid_slot_{slot}'
            result[key]=task_case(plain,1,True,slot)
            assert not result[key]['callsites'] and result[key]['disconnect_calls']==0
    for key in accepted:
        assert result[key]['deny_flag']==0 and result[key]['disconnect_calls']==0
        assert result[key]['configuration_calls']==[['misc','sim_not_match','0']]
    old=original[WINDOW_START:WINDOW_END]
    candidate=(ROOT/'work/research/u15l-candidate-window-only-replaced-16MiB.bin').read_bytes()
    new=candidate[WINDOW_START:WINDOW_END]
    from u15l_candidate_package import make_candidate_package
    from u15l_recovery_package import make_restore_package
    actual_tim,actual_fbf=make_candidate_package(new,old)
    exact_flash=bytearray(original)
    result['exact_download_package_candidate']=run_obm(exact_flash,actual_fbf,tim=actual_tim)
    assert bytes(exact_flash)==candidate
    restore_tim,restore_packet=make_restore_package(old)
    result['exact_download_package_restore']=run_obm(exact_flash,restore_packet,tim=restore_tim)
    assert bytes(exact_flash)==original
    restore_fbf,patch_fbf=make_fbf(old),make_fbf(new)
    for name,data in [('restore',restore_fbf),('patch',patch_fbf)]:
        (ROOT/f'work/research/u15l-{name}-fbf-parser-fixture.bin').write_bytes(data)
    flash=bytearray(original)
    result['obm_patch']=run_obm(flash,patch_fbf)
    assert bytes(flash)==candidate and result['obm_patch']['outcome']=='complete'
    result['obm_restore']=run_obm(flash,restore_fbf)
    assert bytes(flash)==original and result['obm_restore']['outcome']=='complete'
    corrupted=bytearray(patch_fbf);corrupted[0x1000+123]^=1
    result['obm_corrupt_payload']=run_obm(flash,bytes(corrupted))
    assert result['obm_corrupt_payload']['outcome']=='error_71'
    assert result['obm_corrupt_payload']['events']==[] and flash==original
    for stage in ('erase','half_write'):
        flash=bytearray(original)
        failure=run_obm(flash,patch_fbf,stage)
        assert flash[:WINDOW_START]==original[:WINDOW_START] and flash[WINDOW_END:]==original[WINDOW_END:]
        recovery=run_obm(flash,restore_fbf)
        assert flash==original and recovery['outcome']=='complete'
        result[f'obm_simulated_interruption_{stage}']={'failure':failure,'recovery':recovery}
    (OUT/'离线仿真验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
