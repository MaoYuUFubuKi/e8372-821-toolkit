#!/usr/bin/env python
"""Grab the download-mode window and run the project backup in the same process.

The device enters download mode (VID 0x2ecc / PID 0x3001, WUKONG) for a short
window when re-plugged, then jumps back to RNDIS within a few seconds. The
project's session() expects the device to appear AFTER it starts (it waits for
an unplug), so launching it while the device is already in download mode makes
session() wait for a disappearance that never happens. This script instead
claims the interface itself the moment download mode appears (which holds the
device in download mode) and hands the held device to the project collect flow
via held_dev, so no subprocess launch time or re-claim race is needed.

It keeps listening forever (re-creating the libusb backend after each wait
cycle) so a short download-mode window is never missed, even hours later.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'runtime', 'python'), os.path.join(ROOT, 'src'),
                os.path.join(ROOT, 'src', 'u15l', 'device')]

import libusb_package
import usb.core
import usb.util

DOWNLOAD_VID, DOWNLOAD_PID = 0x2ECC, 0x3001


def find_download(backend):
    return list(usb.core.find(find_all=True, backend=backend,
                              idVendor=DOWNLOAD_VID, idProduct=DOWNLOAD_PID))


def claim_device(dev):
    """Verify interface layout and claim; returns the device once held."""
    if dev.product != 'WUKONG':
        raise RuntimeError('USB 设备名不符。')
    try:
        cfg = dev.get_active_configuration()
    except usb.core.USBError as exc:
        if 'Configuration not set' not in str(exc):
            raise
        dev.set_configuration(1)
        cfg = dev.get_active_configuration()
    itf = cfg[(0, 0)]
    eps = sorted((e.bEndpointAddress, e.bmAttributes & 3, e.wMaxPacketSize) for e in itf)
    if cfg.bConfigurationValue != 1 or eps != [(2, 2, 512), (129, 2, 512)]:
        raise RuntimeError('USB 接口布局不符。')
    usb.util.claim_interface(dev, 0)
    return dev


def run_collect(args, dev):
    """Hand the held device to the project collect flow; session() reuses it."""
    from u15l import collect as collect_mod
    try:
        collect_mod.collect(args.case, already_present=True,
                            resume=args.resume, held_dev=dev)
        print('备份完成。', flush=True)
        return 0
    except Exception as exc:
        print('备份失败：%s' % exc, file=sys.stderr)
        return 1
    finally:
        try:
            usb.util.release_interface(dev, 0)
        except Exception:
            pass
        usb.util.dispose_resources(dev)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', default='e8372')
    ap.add_argument('--interval', type=float, default=0.1)
    ap.add_argument('--timeout', type=float, default=120,
                    help='单个等待周期秒数（0=不重置后端，一直等）')
    ap.add_argument('--resume', action='store_true',
                    help='跳过已完成的双遍 16 MiB 读取，只补核对阶段')
    ap.add_argument('--once', action='store_true',
                    help='成功抓取并完成一轮后退出')
    args = ap.parse_args()

    os.environ['U15L_ALLOW_UNVERIFIED_PLATFORM'] = '1'
    print('持续监听下载模式（WUKONG 2ECC:3001），每 %.2f 秒轮询。' % args.interval, flush=True)
    print('请拔下设备，等 3 秒，再插回。检测到后会立即抓取并备份。', flush=True)
    print('按 Ctrl+C 退出。', flush=True)

    cycle = 0
    while True:
        backend = libusb_package.get_libusb1_backend()
        if backend is None:
            print('无法加载 libusb 后端，1 秒后重试', file=sys.stderr)
            time.sleep(1)
            continue
        cycle += 1
        deadline = time.monotonic() + (args.timeout if args.timeout > 0 else 1e9)
        last_heartbeat = time.monotonic()
        dev = None
        grabbed = False
        while time.monotonic() < deadline:
            ds = find_download(backend)
            if ds:
                print('*** 检测到下载模式，立即抓取 ***', flush=True)
                try:
                    dev = claim_device(ds[0])
                    print('接口已 claim，设备已固定。', flush=True)
                    grabbed = True
                    break
                except usb.core.USBError as exc:
                    print('claim 失败：%r，重试...' % exc, flush=True)
                    try:
                        usb.util.dispose_resources(ds[0])
                    except Exception:
                        pass
                    time.sleep(args.interval)
                    continue
                except Exception as exc:
                    print('抓取失败：%s' % exc, file=sys.stderr)
                    time.sleep(args.interval)
                    break
            if time.monotonic() - last_heartbeat >= 60:
                print('仍在监听下载模式（已等待 %.0f 秒，周期 %d）...' %
                      (time.monotonic() - (deadline - (args.timeout if args.timeout > 0 else 1e9)), cycle),
                      flush=True)
                last_heartbeat = time.monotonic()
            time.sleep(args.interval)

        if grabbed:
            rc = run_collect(args, dev)
            if args.once:
                return rc
            print('本轮完成，继续监听下一次下载模式。', flush=True)
        else:
            print('等待周期结束，重新建立 USB 枚举；设备可随时插入。', flush=True)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n已停止监听。', file=sys.stderr)
        sys.exit(130)
