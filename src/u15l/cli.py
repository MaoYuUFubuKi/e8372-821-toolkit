import argparse,json,os,platform,subprocess,sys
from .common import ROOT,case_path,verify_runtime,save_json,now

def run_case(name,script):
    prepared=case_path(name)/'prepared'
    if not (prepared/'manifest.json').exists():raise RuntimeError('尚未完成 prepare。')
    env=dict(os.environ,PYTHONPATH=str(prepared/'runtime'),PYTHONDONTWRITEBYTECODE='1')
    return subprocess.call([sys.executable,str(prepared/'work/device'/script)],cwd=prepared,env=env)

def main():
    p=argparse.ArgumentParser(description='U15L / ASR1803S：自己的备份、固定指纹修改、先验证回滚。')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    b=sub.add_parser('backup');b.add_argument('case');b.add_argument('--mirror',action='store_true')
    b=sub.add_parser('prepare');b.add_argument('case')
    b.add_argument('--method',choices=('auto','fixed','local'),default='auto',help='默认优先固定程序组件；无组件时从本机备份生成')
    for key in ('board','soc','firmware'):b.add_argument('--'+key,required=True)
    for name in ('check','install','restore','emulate'):
        b=sub.add_parser(name);b.add_argument('case')
        if name in ('install','restore'):b.add_argument('--write',action='store_true',help='明确执行实际闪存写入')
    b=sub.add_parser('status');b.add_argument('--host',default='192.168.0.1')
    args=p.parse_args()
    if args.command in ('backup','install','restore') and (platform.system()!='Darwin' or platform.machine()!='arm64'):
        raise RuntimeError('当前硬件流程仅在 macOS ARM64 验证；此平台只允许离线研究。')
    if args.command=='doctor':
        verify_runtime();import libusb_package
        backend=libusb_package.get_libusb1_backend()
        print(json.dumps({'python':sys.version.split()[0],'os':platform.system(),'architecture':platform.machine(),
                          'bundled_runtime_verified':True,'libusb_backend_loaded':backend is not None,
                          'hardware_tested_platform':'macOS / Apple Silicon','device_opened':False},indent=2))
        return 0 if backend else 1
    if args.command=='status':
        from .status import read_status
        print(json.dumps(read_status(args.host),ensure_ascii=False,indent=2));return 0
    if args.command=='prepare':
        from .prepare import prepare
        prepare(args.case,args.board,args.soc,args.firmware,args.method);return 0
    if args.command=='backup':
        from .collect import collect
        collect(args.case,args.mirror);return 0
    if args.command=='check':
        checks=['check_noop_flow_offline.py','check_restore_flow_offline.py','check_candidate_flow_offline.py','check_install_offline.py']
        for f in checks:
            if run_case(args.case,f):raise RuntimeError('离线检查失败：'+f)
        save_json(case_path(args.case)/'checks.json',{'offline_checks_passed':True,'checked_at':now(),'scripts':checks})
        return 0
    if args.command=='emulate':
        return subprocess.call([str(ROOT/'scripts/emulate_case.sh'),args.case])
    if args.command in ('install','restore'):
        if not args.write:raise RuntimeError('写入命令需要 --write；查看 README 后再执行。')
        if args.command=='install':
            checks=case_path(args.case)/'checks.json'
            if not checks.exists() or not json.loads(checks.read_text()).get('offline_checks_passed'):
                raise RuntimeError('先运行 check；之后仍会在实际刷写前重新核验全部数据。')
        return run_case(args.case,'install_u15l_candidate.py' if args.command=='install' else 'restore_u15l_original.py')

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:print('停止：'+str(e),file=sys.stderr);sys.exit(1)
