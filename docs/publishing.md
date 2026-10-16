# 发布说明

只发布源码、测试、文档和 README 配图。运行库由使用者本地安装，固件从自己的备份生成；`runtime/`、`firmware/`、`local/` 不打包、不提交 Git。

```sh
python3 scripts/package_release.py
```

生成 `u15l-asr1803-toolkit-source-only.zip` 和校验文件。打包使用白名单，不上传文件。博客只维护 README 后半部分。

## 照片待作者打码

照片仅移除了 EXIF/XMP/IPTC 元数据，画面保持原样。作者已要求自行处理可见信息：

| 文件 | 需要检查的内容 |
| --- | --- |
| `01-board-sim-side.jpg` | 板上二维码与序列号 |
| `02-board-shield-side.jpg` | 屏蔽罩二维码 |
| `03-case-label.jpg` | Wi-Fi 密码、管理密码、序列号、IMEI、二维码及 SSID |
| `04-asr1803-board.jpg` | 拆下的屏蔽罩二维码 |
| `05-chip-closeup.jpg` | 背景与标识 |
| `06-success-blue-led.jpg` | 背景 |

打码后更新 `assets/photos/manifest.json` 中相应文件的 SHA-256、`redacted` 与 `pixels_unchanged`，再重新打包。不把未打码的原图附在公开发行里。

## 授权与依赖

原创代码使用 [MIT](../LICENSE)，照片权利归作者。项目不分发原厂固件或第三方二进制。

| 本地安装的组件 | 版本 | 来源与许可证 |
| --- | --- | --- |
| PyUSB | 1.3.1 | [上游](https://github.com/pyusb/pyusb)，BSD-3-Clause |
| libusb-package | 1.0.30.0 | [上游](https://github.com/pyocd/libusb-package)，Apache-2.0 |
| libusb | 1.0.30 | [源码与许可](https://github.com/libusb/libusb/releases/tag/v1.0.30)，LGPL-2.1-or-later |
| Capstone，可选分析 | 5.0.6 | [上游](https://github.com/capstone-engine/capstone)，BSD |
| Unicorn，可选仿真 | 2.1.4 | [上游](https://github.com/unicorn-engine/unicorn)，按其 GPL/LGPL 组件条款 |

安装脚本保留 Python 包自带的许可证和 libusb 来源说明。生成的运行目录与恢复包只供本机使用，不随源码发布。USB 协议参考资料见[技术记录](research.md)。
