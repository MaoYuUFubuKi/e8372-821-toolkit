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

原机启动程序的内部写后检查只覆盖很小一段，不能替代主机完整读回。每次恢复/刷入后都需新上电、16 MiB 两次读取。保护范围为 `[0,0x480000)`、`[0x5c0000,0x980000)`、`[0xb20000,0x1000000)`。中间历史上会变化的运行/配置区域单独保存记录，不用旧配置覆盖。L01 最终实际比较显示，写入窗口外整片都没有变化。

### 固件指纹

| 区域 | SHA-256 |
| --- | --- |
| 原版首 4 KiB | `a03e30e27c254666ea35881a25096723c38f3087eb8b40d230d6ea892f93b78f` |
| 原机 OBM：闪存 `0x6000` 起，长度 `0x165ac` | `34a56247fa26e5c359930e43fef76ce30f5b95d2ce8ddd3f3fafcdab87f2e9f4` |
| L01 解压后 CODE_PL | `e42836f86fdcef5c1ab13061efa0429c9f9ee4c7e4f4daf2ec7b47a85d7c2daf` |
| M02 解压后 CODE_PL | `ef0506f5e4669e9501370e459f5987c12cc6fe2019d7e02158ba869cbc5054e4` |

本次 M02 备份的首 4 KiB 与原机 OBM 均匹配上述共享指纹，因此保持既有传输协议、解析仿真和写入范围。应用 CODE_PL 必须分版本验证。整片 SHA 包含自己的配置和运行记录，不作为跨设备的适配值。准备程序给每个使用者的恢复/候选数据重新计算并固定哈希。

`src/u15l/profiles.py` 注册精确固件配置，`prepare` 将所选配置写入私人目录的 `firmware_profile.py` 和清单，实际刷写前再次检查原版程序与候选差异。未渲染模板不能执行候选准备或刷写。旧采集器曾把备份记录的 `profile` 固定写为 L01；该字段仅作为历史提示保留，不能替代原版指纹。新采集记录不提前声称应用固件版本。

参考：[公开工具的读取实现](https://github.com/wirenboard/flash-simcom-a76xx/blob/b813581c095c3f4e83d636f3b8999072eb803e7f/WtptpDownloader.c)、[错误码定义](https://github.com/wirenboard/flash-simcom-a76xx/blob/b813581c095c3f4e83d636f3b8999072eb803e7f/ErrorCode.h)。原机二进制不随项目分发。

## 原固件校验与修改

### L01 校验调用链

L01 的 CODE_PL 解压加载基址 `0x06882000`，解压长度 `0x294fb4`。函数 `0x0690acfa` 读取 ICCID，调用卡商 HTTP/JSON 校验并解析 `bindFlag`。已定位的两个调用点是 `0x0690af00` 和 `0x0690af0a`，在任务 `0x0690ae52` 内。

返回 0 会设置内部拒绝状态 `0x06b72d1c`，并修改管理配置、调用断开数据连接流程。返回 1 走接受路径。配置层单独改 `sim_not_match` 的试验未恢复网络，之后复原了试验配置。

补丁在函数入口将 `2de9f043` 改为 `01207047`，即 `movs r0,#1; bx lr`。公开准备程序只在全部原始指纹匹配、入口原字节匹配时应用。代码不会替换身份、校准和其他人的配置。

### M02 独立适配

使用 M02 设备两份一致的 16 MiB 备份，独立反汇编并执行原函数，确认以下版本差异：

| 项目 | L01 | M02 |
| --- | --- | --- |
| 完整固件名 | `U15L-MT02B01V15-L01` | `U15L-MT02B01V15-M02` |
| CODE_PL 解压长度 | `0x294fb4` / 2,707,380 字节 | `0x294e60` / 2,707,040 字节 |
| 校验函数入口 | `0x0690acfa` | `0x0690acee` |
| 解压代码补丁偏移 | `0x88cfa` | `0x88cee` |
| 调用任务入口 | `0x0690ae52` | `0x0690ae54` |
| 校验函数直接调用点 | `0x0690af00`、`0x0690af0a` | `0x0690aeee` |
| 实际 JSON 校验键 | `bindFlag` | `checkFlag` |

M02 与 L01 使用相同的加载基址和四字节替换指令。M02 查询 `checkFlag`，但缺失键日志仍写着 `no bindFlag`。执行原始查找、类型判断和返回分支确认：JSON 布尔真返回 1；假、数字或字符串等非真布尔类型返回 0；缺响应、解析失败或缺键返回 -2；空 SN 或 ICCID 返回 -1。HTTP、标识读取和 JSON 对象构造使用确定的离线 fixture，没有访问卡商接口。

M02 原任务只接受 slot 1，原始 slot helper `0x069a4cb8` 本身也固定返回 1。返回 0 的拒绝路径设置 `0x06b72d1c=1`、`sim_not_match=1`、`wan/connect_disconnect=disabled` 并调用断网；返回 1 结束校验循环。-1 和 -2 分别走延迟重试。专门仿真覆盖了这些路径、等待 readiness、缺 URL 和无效 slot。

补丁在校验函数入口返回匹配，不执行 HTTP/JSON，也不会清除已有的内部拒绝标志。任务仿真假设冷启动全局状态为零，因此实际刷写后必须重新上电，再检查拨号状态与真实联网。

### 压缩

两版闪存压缩范围均为 `0x481000..0x5b7000`，长度 `0x136000`。LZMA-alone：lc=3、lp=0、pb=2、1 MiB 字典。L01 原头为 `5d00001000b44f290000000000`，M02 为 `5d00001000604e290000000000`。压缩后恢复对应版本的已知长度头，重解压必须逐字节等于只有 4 字节改变的目标。

L01 原流 1,267,838 字节，修改流 1,268,216 字节，预留区剩余 1,544 字节。M02 从本机原版独立重压缩并校验，禁止使用 L01 固定组件。不同运行库若产生不同压缩结果，必须重新校验大小和完整解压；不能用前次结果替它背书。

### 原机启动程序与仿真

原机 OBM 从自己的备份提取，ARM 加载地址 `0x07800000`。执行原机 TIM/FBF 解析和校验代码，在 USB、底层 flash 函数等硬件边界做仿真替代，验证指定窗口写入、恢复、损坏校验失败以及模拟中断恢复。

L01 测试了 32 组寄存器状态和原任务两条调用分支；此次通用化后的 L01 回归也通过，候选与旧源码算法输出完全一致，M02 配置会拒绝 L01 原版。M02 除同样的补丁寄存器检查外，还独立执行了原始校验函数与调用任务，包括原始 slot helper。两版任务仿真均使用预设的外部系统函数和初始全局状态，不是完整基带启动仿真。仿真通过不能代替实际硬件读回和联网。

### 如何自己查看

准备自己的 case 后，其 `prepared/work/research/` 中包含从自己备份提取的 OBM、原 CODE_PL、修改 CODE_PL 和完整候选。它们都在 `local/`，不能发布。

```sh
# 先准备分析依赖；此处以 M02 为例，L01 应使用其完整版本。
local/analysis-env/bin/python scripts/disassemble.py \
  local/my-device/prepared/outputs/backup/original-copy1.bin \
  --firmware U15L-MT02B01V15-M02
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

[validation.json](validation.json) 分别保存 L01 和 M02 的实测摘要。原始备份、日志和仿真材料留在私人目录，不随源码分发。

L01 已完成原版写回、修改版双份读回、正常启动与手机 Wi-Fi 上网确认；公开项目整理后的验证为离线复现。

M02 于 2026-10-20 完成五阶段安装，各读取阶段均为两份一致的 16 MiB 数据。原版和修改版窗口分别匹配本机备份与候选，整个写入窗口外数据未变化。独立恢复包完整性已校验；实际原版恢复通过安装流程执行，未另行执行独立恢复入口。

M02 重新上电后固件版本保持不变，`sim_not_match` 从 1 变为 0、PDP 从 0 变为 1，并取得 IPv4 地址。机主确认手机连接设备 Wi-Fi、关闭蜂窝数据后能打开新网页。结论限于本台设备与自有移动 SIM，其他卡、型号和 Reset 恢复出厂未验证。

`src/u15l/device/` 中带哈希占位符的代码由准备程序绑定到本机数据，再写入私人工作目录。`tests/flows/` 的四组检查同时复制到该目录运行。不要直接运行未绑定数据的写入模块。
