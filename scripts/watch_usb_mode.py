#!/usr/bin/env python
"""Watch for the E8372 download mode and auto-run ./run.sh backup <case>.

The download-mode USB identity (VID 0x2ecc / PID 0x3001, product WUKONG)
appears only for a short window when the device is re-plugged. As soon as it
appears, this script launches the backup command automatically so the window
is never wasted waiting for a manual notification.
"""
import argparse
import os
import subprocess
import sys
import time

try:
    import usb.core
except ImportError:
    usb.core = None

try:
    import libusb_package
except ImportError:
    libusb_package = None

DOWNLOAD_VID, DOWNLOAD_PID = 0x2ECC, 0x3001
RNDIS_VID, RNDIS_PID = 0x1E0E, 0x3487
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _libusb_backend():
    if libusb_package is None:
        return None
    return libusb_package.get_libusb1_backend()


def mode_via_libusb():
    """Return set of modes currently visible via libusb (faster than PnP)."""
    modes = set()
    backend = _libusb_backend()
    if backend is None:
        return modes
    try:
        if list(usb.core.find(find_all=True, backend=backend, idVendor=DOWNLOAD_VID, idProduct=DOWNLOAD_PID)):
            modes.add('download')
        if list(usb.core.find(find_all=True, backend=backend, idVendor=RNDIS_VID, idProduct=RNDIS_PID)):
            modes.add('rndis')
    except Exception:
        pass
    return modes


def pnp_contains(needle):
    ps = r"""Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_2ECC' -or $_.InstanceId -match 'VID_1E0E' } | Select-Object -ExpandProperty InstanceId"""
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True)
    return any(needle in line for line in r.stdout.splitlines())


def current_modes():
    """Prefer fast libusb enumeration; fall back to PnP if libusb is unavailable."""
    modes = mode_via_libusb()
    if modes:
        return modes
    # libusb may not see the device if the WinUSB driver is not bound yet;
    # fall back to PnP presence.
    if pnp_contains('VID_2ECC&PID_3001'):
        modes.add('download')
    if pnp_contains('VID_1E0E&PID_3487'):
        modes.add('rndis')
    return modes


def run_backup(case):
    print('\n*** 检测到下载模式，自动执行 backup ***', flush=True)
    print('case = %s' % case, flush=True)
    env = dict(os.environ)
    env['U15L_ALLOW_UNVERIFIED_PLATFORM'] = '1'
    env['PYTHONPATH'] = os.pathsep.join([os.path.join(ROOT, 'runtime', 'python'), os.path.join(ROOT, 'src')])
    # Use run.sh so the launcher resolves the Python interpreter and env the same
    # way the project documents; fall back to direct -m invocation.
    run_sh = os.path.join(ROOT, 'run.sh')
    if os.path.exists(run_sh) and os.access(run_sh, os.X_OK):
        cmd = [run_sh, 'backup', case]
    else:
        cmd = [sys.executable, '-m', 'u15l', 'backup', case]
    print('运行: %s' % ' '.join(cmd), flush=True)
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env)
        print('backup 退出码: %d' % r.returncode, flush=True)
        return r.returncode
    except Exception as e:
        print('backup 启动失败: %s' % e, flush=True)
        return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', default='e8372', help='backup case name (default: e8372)')
    ap.add_argument('--interval', type=float, default=0.2)
    ap.add_argument('--once', action='store_true', help='Exit after first trigger instead of re-arming')
    args = ap.parse_args()
    print('监听设备模式切换（每 %.2f 秒轮询）。按 Ctrl+C 退出。' % args.interval, flush=True)
    last = set()
    while True:
        try:
            modes = current_modes()
        except Exception as e:
            print('轮询失败: %s' % e, flush=True)
            time.sleep(args.interval)
            continue
        if 'download' in modes and 'download' not in last:
            print('\n*** 检测到下载模式 (WUKONG 2ECC:3001) ***', flush=True)
            rc = run_backup(args.case)
            if args.once:
                return rc
        if modes != last:
            print('当前模式: %s' % (', '.join(sorted(modes)) if modes else '（无）'), flush=True)
        last = modes
        time.sleep(args.interval)


if __name__ == '__main__':
    sys.exit(main())
