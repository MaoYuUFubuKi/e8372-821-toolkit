# 技术记录

供维护者复核协议、补丁与测试边界。常规操作看 [README](../README.md)。

## USB 读取与恢复协议

本文件记录本次原机实测和原机 OBM 分析，不是通用 ASR 协议适配声明。

### 传输接口

启动 USB：VID/PID `2ecc:3001`、产品名 `WUKONG`。配置 1、接口 0，Bulk OUT `0x02`、Bulk IN `0x81`，最大包 512。需先启用 USB 配置再 claim 接口；打开前发生接口切换可以重新捕获，已经发命令后出错不复用旧会话。

Preamble 为 `00 d3 02 2b`。普通请求头为 `<BBBBI`：命令、序号、CID、标志、数据长度。典型回应含 6 字节头，随后才是数据。读取有效数据最多 `8192-6=8186` 字节；下载每包有效数据最多 `8192-8=8184` 字节。不要混淆。

### 读取会话

```text
Preamble → GetProtocolVersion(34) → GetParameters(35)
         → UploadDataHeader(32) → UploadData(33)... → Done(30)
```

读取前不发 `GetVersion(20)`。每个 1 MiB 区域重新握手，16 MiB 两遍共 32 个区域。参数头使用 `<BBBBIIBBBB>`，本次类型 0、子类型 27（QSPI）、分区 0、固定范围。32 MiB 两遍的回绕检查使用 64 个区域。

协议返回 `01 01 00 00`，参数缓冲区 8192。首 4 KiB 的公共固件指纹也必须匹配。两次逐段及完整哈希不同、头被拒绝或数据长度不符都停止。保留 `.partial`，不补零。

`0x64` 是参考源码定义的 UnsupportedFlashError；`0x05` 是 NotSupportedError。它们不自动代表读保护。错误原因必须结合这次命令、参数和启动程序，而不是只看“读取失败”。

### 下载会话

每个镜像分别：

```text
Preamble → 消息队列 → GetVersion(20) → SelectImage(26)
         → VerifyImage(27) → DataHeader(2a)/Data(22)... → Done(30)
```

设备按顺序请求 TIMH、FBF0。身份固定为 `3311 / 06012014 / NZA3`，按线上的字节是 `313133331420010633415a4e`。数据序号按 8 位回绕。空消息队列的特殊回应 `2b0000010000` 在本机属正常情况；其他 NACK 不忽略。

元数据空操作只有 1 KiB TIM 和 4 KiB FBF，FBF 写入项数量为 0，无程序代码。等待解析完成通知，不把数据 ACK 当作 Ready。类型 4 通知在本机报告 `0x01000000` 字节容量；类型 1 是错误。

### 固定窗口恢复与候选

TIM 3.4.0，QSPI 27，仅 TIMH/FBF0 描述；FBF 11，一个设备、一项范围写入。设备字段 EraseAll、ResetBBT、生产/熔丝相关标志为 0。唯一范围为：

```text
起点 0x480000，长度 0x140000，末地址 0x5c0000（不含）
```

数据先完整传输到原机启动程序指定的临时内存，校验后再写入。该项校验为 payload 的 little-endian uint32 XOR。恢复包与候选包的元数据、地址一致，只差数据和对应校验。

原机启动程序的内部写后检查只覆盖很小一段，不能替代主机完整读回。每次恢复/刷入后都需新上电、16 MiB 两次读取。保护范围为 `[0,0x480000)`、`[0x5c0000,0x980000)`、`[0xb20000,0x1000000)`。中间历史上会变化的运行/配置区域单独保存记录，不用旧配置覆盖。此次最终实际比较显示，写入窗口外整片都没有变化。

### 固件指纹

| 区域 | SHA-256 |
| --- | --- |
| 原版首 4 KiB | `a03e30e27c254666ea35881a25096723c38f3087eb8b40d230d6ea892f93b78f` |
| 原机 OBM：闪存 `0x6000` 起，长度 `0x165ac` | `34a56247fa26e5c359930e43fef76ce30f5b95d2ce8ddd3f3fafcdab87f2e9f4` |
| 解压后 CODE_PL | `e42836f86fdcef5c1ab13061efa0429c9f9ee4c7e4f4daf2ec7b47a85d7c2daf` |

整片 SHA 包含自己的配置和运行记录，不作为跨设备的适配值。准备程序给每个使用者的恢复/候选数据重新计算并固定哈希。

参考：[公开工具的读取实现](https://github.com/wirenboard/flash-simcom-a76xx/blob/b813581c095c3f4e83d636f3b8999072eb803e7f/WtptpDownloader.c)、[错误码定义](https://github.com/wirenboard/flash-simcom-a76xx/blob/b813581c095c3f4e83d636f3b8999072eb803e7f/ErrorCode.h)。原机二进制不随项目分发。

## 原固件校验与修改

### 校验调用链

匹配固件的 CODE_PL 解压加载基址 `0x06882000`，解压长度 `0x294fb4`。函数 `0x0690acfa` 读取 ICCID，调用卡商 HTTP/JSON 校验并解析 `bindFlag`。已定位的两个调用点是 `0x0690af00` 和 `0x0690af0a`，在任务 `0x0690ae52` 内。

返回 0 会设置内部拒绝状态 `0x06b72d1c`，并修改管理配置、调用断开数据连接流程。返回 1 走接受路径。配置层单独改 `sim_not_match` 的试验未恢复网络，之后复原了试验配置。

补丁在函数入口将 `2de9f043` 改为 `01207047`，即 `movs r0,#1; bx lr`。公开准备程序只在全部原始指纹匹配、入口原字节匹配时应用。代码不会替换身份、校准和其他人的配置。

### 压缩

闪存压缩范围 `0x481000..0x5b7000`，长度 `0x136000`。LZMA-alone：lc=3、lp=0、pb=2、1 MiB 字典，原头 `5d00001000b44f290000000000`。压缩后恢复已知长度头，重解压必须逐字节等于只有 4 字节改变的目标。

本次原流 1,267,838 字节，修改流 1,268,216 字节，预留区剩余 1,544 字节。不同运行库若产生不同压缩结果，必须重新校验大小和完整解压；不能用本次结果替它背书。

### 原机启动程序与仿真

原机 OBM 从自己的备份提取，ARM 加载地址 `0x07800000`。执行原机 TIM/FBF 解析和校验代码，在 USB、底层 flash 函数等硬件边界做仿真替代，验证指定窗口写入、恢复、损坏校验失败以及模拟中断恢复。

此外测试了 32 组寄存器状态和原任务两条调用分支。任务仿真使用预设的外部系统函数和初始全局状态，不是完整基带启动仿真。仿真通过不能代替实际硬件读回和联网。

实机最终又完成原版真实写回、修改版写入、两遍主闪存读回、正常启动、管理 API 状态和手机 Wi-Fi 上网确认。重构为公开项目后只做离线复现，没有为打包再刷一遍机器。

### 如何自己查看

准备自己的 case 后，其 `prepared/work/research/` 中包含从自己备份提取的 OBM、原 CODE_PL、修改 CODE_PL 和完整候选。它们都在 `local/`，不能发布。

```sh
## 需先准备分析依赖；反汇编只读取文件。
local/analysis-env/bin/python scripts/disassemble.py \
  local/my-device/prepared/outputs/backup/original-copy1.bin
./run.sh emulate my-device
```

仿真环境注意事项见 本文件的运行与分析环境一节。可复核来源：[有格 ASR Cat4 工具资料](https://docs.yuge-info.com/doku.php?id=asr:cat4:update_w)、[Wiren Board 协议源码](https://github.com/wirenboard/flash-simcom-a76xx/tree/b813581c095c3f4e83d636f3b8999072eb803e7f)。其他型号的参考启动文件只用于理解差异，没有用于本机刷写，也不随本项目分发。

## 运行与分析环境

### 备份和刷写

实测平台是 macOS / Apple Silicon。Python 3.9+ 自带 hashlib、struct、lzma、json；运行 `python3 scripts/setup_runtime.py` 安装：

- PyUSB 1.3.1；
- libusb-package 1.0.30.0 及 ARM64 的 libusb 动态库；
- 使用 Python 标准库 importlib.resources 的小适配模块。

依赖生成到项目自己的 `runtime/`，不改全局 Python。`./run.sh` 使用这些固定依赖，`doctor` 校验 runtime 清单并加载后端，不打开设备。没有复制带个人路径的 `.venv`。生成的私有恢复包也包含这些依赖，因此在已有 Python 的同类 Mac 上可离线恢复。

如使用自己安装的环境，可按上面的固定版本研究；正式流程使用安装脚本生成的运行目录及清单，其中包含标准库资源适配模块。其他系统的 Python 库可安装，不代表此项目已验证其 USB 驱动、捕获和刷写流程。当前命令对非 macOS ARM64 的硬件操作停止。

### 反汇编和仿真

这部分是可选研究环境，不影响常规刷写。

- Capstone 5.0.6：静态反汇编。
- Unicorn 2.1.4：离线运行原机 ARM/Thumb 指令。
- 本次 Mac 上，Unicorn 原生 ARM64 wheel 在初始化 CPU 特性时崩溃；x86_64 wheel 配合 Rosetta 和兼容的 `/usr/bin/python3` 实测可用。这个结论只描述本次主机，不能泛化为所有 ARM64 Mac 都有同样问题。

```sh
./scripts/setup_analysis.sh
./run.sh emulate my-device
```

setup 脚本联网下载固定版本，Unicorn x86_64 wheel SHA-256 必须为：

```text
2a6f738fab5fabffa56af1e7bbf16ea1e91466c342f8dc64f125bd70f36c6b80
```

Rosetta 和能以 x86_64 运行的 Python 要单独具备；脚本不会替用户修改系统安装。`/usr/bin/arch -x86_64 /usr/bin/python3 -V` 可检查。未来 Mac 如果没有该解释器，可配置等价的 x86_64 Python 后调整研究脚本，不能因此修改实际 USB 写入流程。

网络下载的分析依赖保存到 `local/`。厂商 Windows/Linux 下载工具、不同主板固件、完整虚拟环境和历史失败脚本没有捆绑；本次有效参数及分析证据已写入协议文档。

### 测试层级

- `python3 -m unittest discover -s tests -v`：不需要原机整片备份的公开测试；自行提供固定组件时会额外检查，未提供时跳过该项。
- `./run.sh check <case>`：使用自己的备份测试分包、失败路径及恢复门槛，不打开 USB。
- `./run.sh emulate <case>`：执行自己的匹配启动程序与补丁指令；硬件边界是仿真。
- 实际 install：真实恢复、修改写入、两遍读回。
- 实际网页访问：手机 Wi-Fi 访问，关闭手机蜂窝数据。

不能把上一层测试替代下一层结论。

## 实测与整理后的验证

本次实机结果和整理后的离线检查记录合并在 [validation.json](validation.json)。公共测试可在无 USB 依赖的环境运行：

```sh
python3 -m unittest discover -s tests -v
```

`src/u15l/device/` 中带哈希占位符的代码由准备程序绑定到本机数据，再写入私人工作目录。`tests/flows/` 的四组检查同时复制到该目录运行。不要直接运行未绑定数据的写入模块。
