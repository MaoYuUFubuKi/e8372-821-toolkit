# Windows 使用指南

本工具链在 macOS / Apple Silicon 上实测。**Windows 上的硬件流程未经作者验证**，需要显式接受风险后才会放行刷写；所有哈希与完整性校验保持不变。使用前请完整阅读 [AGENTS.md](../AGENTS.md) 与 [操作指南](guide.md)。

## 适用对象

- 主板 `8BC010-U15L_V1.03`、主控 `ASR1803S` 的 E8372-821 随身 Wi-Fi。
- 原固件为 `U15L-MT02B01V15-L01` 或 `U15L-MT02B01V15-M02`，且代码指纹与本项目一致。
- **每台设备都必须用自己的两份备份生成修改版**（M02 只能 `--method local`）。本分发包不含任何设备的备份、修改版固件或恢复数据。

## 一、准备 Windows 环境

### 1. 安装 Python

需要 Python 3.9+（本项目在 3.14 上验证）。安装时勾选 **Add python.exe to PATH**。

Windows 商店的 `python3` 别名不可用，工具会自动回退到 `python`。若 `python` 仍指向商店别名，请卸载商店版或使用完整 Python 安装路径。

### 2. 解压工具包

把 `u15l-asr1803-toolkit-windows.zip` 解压到任意目录（路径避免中文和空格，例如 `D:\toolkit`）。得到：

```
u15l-asr1803-toolkit/
├── run.sh                # 唯一命令入口（Git Bash / WSL 可用）
├── src/  scripts/  tests/  docs/
├── runtime/              # 已安装好的 pyusb + libusb DLL（含 SHA256SUMS 校验）
├── AGENTS.md  README.md  LICENSE
└── docs/windows-setup.md # 本文件
```

`runtime/` 已预先装好并带完整性校验，目标电脑**不需要联网安装依赖**。

### 3. 安装 USB 驱动

设备有双身份 USB：下载模式 `VID:PID 2ecc:3001`（约 3 秒窗口），网卡模式 `1e0e:3487`（RNDIS）。需要用 Zadig 把下载模式设备绑定到 WinUSB/libusb 驱动：

1. 下载并打开 [Zadig](https://zadig.akeo.ie/)（需管理员）。
2. 菜单 Options → List All Devices。
3. 拔插设备，在下载模式出现的约 3 秒窗口内，从下拉框选 **WUKONG (VID_2ECC&PID_3001)**。
4. 目标驱动选 **WinUSB**，点击 **Install Driver / Replace Driver**。
5. 完成后，网卡模式（RNDIS）由系统自带驱动管理，用于管理页和联网；下载模式由 WinUSB 驱动，用于工具读写。

> 若驱动未绑定，下载模式会回退成网卡模式，工具会一直等不到设备。可先用设备管理器确认下载模式设备的驱动已替换。

## 二、核对设备与备份

### 4. 运行环境自检

```sh
./run.sh doctor
```

- 应显示 `bundled_runtime_verified: true`、`libusb_backend_loaded: true`。
- `hardware_tested_this_host: false`（Windows 未验证），`write_gate: enabled`（写入门禁开启）。

### 5. 备份（双遍 + 无擦写核对）

```sh
./run.sh backup my-device
```

- 提示“程序已就绪”后，**拔下设备，等 3 秒，插回同一接口**。备份需要两次拔插。
- 下载模式窗口很短（约 3 秒），可用自动监听器替代手动拔插：

```sh
python scripts/auto_backup.py --case my-device --timeout 0
```

监听器会一直等待下载模式出现并立即抓取，完成后自动写 `backup.json`。

- 备份结果保存在 `local/my-device/raw/<时间戳>/`，两份 16 MiB 备份必须逐字节一致。

## 三、生成修改版与恢复包

### 6. 准备（M02 必须 local）

```sh
./run.sh prepare my-device \
  --board 8BC010-U15L_V1.03 \
  --soc ASR1803S \
  --firmware U15L-MT02B01V15-M02 \
  --method local
```

- 会从**你自己的两份备份**生成修改版和独立恢复包，保存到 `local/my-device/prepared/`。
- 指纹不匹配、备份不一致或 `prepared/` 已存在时停止，不覆盖旧包。
- 生成的 `local/my-device/prepared/recovery.zip` 请**另存一份**到安全位置（含你的原版数据和独立恢复工具，不要上传）。

### 7. 离线检查

```sh
./run.sh check my-device
```

- 通过后会写 `checks.json`（`offline_checks_passed: true`），install 依赖它。
- Windows 上 `emulate` 不可用（依赖 macOS Rosetta + x86 Unicorn），不影响刷写。

## 四、刷入修改版（实际写设备）

### 8. 放行平台门禁

Windows 未在作者验证范围内，需要显式接受风险：

```sh
export U15L_ALLOW_UNVERIFIED_PLATFORM=1
```

每次新开终端都要设置，或写入 shell 配置文件。**确认你已理解**：此硬件流程仅在 macOS / Apple Silicon 实测，Windows 上自行承担风险；哈希与完整性校验不变。

### 9. 安装

```sh
./run.sh install my-device --write
```

按提示完成**五次拔插**：

1. 保存现状（两遍读当前闪存）
2. 写回原版（验证回滚）
3. 读回验证原版
4. 写入修改版
5. 读回验证修改版

每阶段看到“程序已就绪”后拔下设备，等 3 秒，插回同一接口；看到“请勿断电”时保持连接。**原版恢复核验失败会停止，不会进入修改版刷入**。

### 10. 验证

- 结束后**再拔插一次正常启动**，并保持自己的有效 SIM 在卡槽。
- 查看管理页 `http://192.168.0.1/`，核对 SIM 识别、运营商、PDP、`sim_not_match`。
- **最终测试**：用手机连接设备 Wi-Fi，**关闭手机蜂窝数据**，打开未缓存网页，确认能上网。

## 五、恢复原版

```sh
./run.sh restore my-device --write
```

或解压自己另存的 `recovery.zip`，双击其中的 `恢复原版.command`。恢复原版会把原卡商校验写回。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `doctor` 报缺 runtime | 分发包已带 runtime；确认解压完整，`runtime/SHA256SUMS` 存在。 |
| 等不到下载模式 | 驱动未绑定或窗口太短；用 Zadig 确认 WUKONG 已绑定 WinUSB，或改用 `auto_backup.py --timeout 0`。 |
| `python3` 不可用 | 商店别名问题；用 `python` 或设 `U15L_PYTHON` 指向完整路径。 |
| 写入门禁拦截 | 未设 `U15L_ALLOW_UNVERIFIED_PLATFORM=1`；明确接受风险后设置。 |
| 固件指纹不匹配 | 停止。不要改哈希或按“都是 U15L”强套；确认固件是 L01 或 M02 且代码匹配。 |
| 写入中断 | 程序会尝试转入原版恢复；也可用自己另存的 recovery.zip。保留记录。 |
| 恢复入口也不出现 | 软件救砖条件不满足，停止继续试写。 |

## 安全边界（必须遵守）

- **每台设备用自己的备份**。本工具包不含任何设备备份/修改版/恢复数据。
- **不要上传**完整备份、配置、日志原文、SIM 卡号或管理密码。
- **不要**把某台设备的 16 MiB 备份或修改版刷入另一台设备（会复制身份、配置和校准数据）。
- 恢复原版会恢复原卡商校验；后续固件更新若覆盖修改程序段，也会覆盖本次修改。
