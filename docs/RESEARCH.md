# docs/RESEARCH.md — Joy-Con 2 开源生态调研报告

> 对应 GOAL.md **Phase 0**。
> 调研日期：2026-09-06。信息源优先级：GitHub 源码 > 官方技术资料 > issue / PR > 抓包数据 > 二手文章（**不作为唯一依据**）。
> 本报告所有协议细节的一手来源汇总在 [JOYCON2_PROTOCOL.md](./JOYCON2_PROTOCOL.md)。

---

## 0. 执行摘要（结论先行）

| 问题 | 结论 |
| --- | --- |
| Joy-Con 2 需要从零逆向吗？ | **不需要。** 社区已完成关键逆向：BLE 自定义 GATT service、input-report characteristic、write-command characteristic、IMU 使能命令、完整 62 字节 notification 布局（含 accel/gyro/mag/battery/temp）均已公开。 |
| IMU 是否已有公开代码可启用？ | **是。** `TheFrano/joycon2py`、`TheFrano/joycon2cpp`、`Misaka10571/joycon2-connector`、`matiaspalmac/everything-imu` 均已实现「连接 → 写 IMU 使能命令 → 收到含 accel/gyro 的 notification」。其中 `everything-imu` 明确标注 Joy-Con 2 为 *hardware-validated*，BLE 采样约 **62 Hz**。 |
| 浏览器能否直接读 Joy-Con 2 IMU？ | **不能可靠做到。** Joy-Con 2 **不是** Bluetooth HID，而是自定义 BLE GATT；WebHID 完全不适用（WebHID 只对第一代 Joy-Con 的 HID 生效）。Web Bluetooth 理论可连 GATT，但需要浏览器实验 flag、受 characteristic 黑名单/权限限制，社区无成功先例。→ **采用 GOAL.md 方案 B：Native BLE Adapter → WebSocket → Browser。** |
| 复用策略 | 以 `joycon2py` 为**协议 + 解码参考实现**（`REFERENCE`，MIT，可直接改写），`everything-imu` 为**滤波/采样率/姿态解算参考**（`REFERENCE`）。不整体 fork 任何项目，因为它们都绑定 Windows 专有虚拟手柄（vgamepad / ViGEmBus），与本项目「BLE → WebSocket」目标正交。 |

---

## 1. 候选项目逐项评估

> 字段：Star / 最近更新 / 设备 / OS / Bluetooth / Buttons / Stick / IMU / Rumble / Mouse Sensor / 语言 / License / 代码质量 / 成熟度 / **结论**。
> Star 数为 2026-09-06 抓取值，可能有 ±小幅波动。

### 1.1 `TheFrano/joycon2py` — https://github.com/TheFrano/joycon2py

| 字段 | 值 |
| --- | --- |
| Star | ~29 |
| 最近更新 | 已停止维护（README 明确 "THIS SPECIFIC PROJECT IS NO LONGER IN DEVELOPMENT"，指向 C++ 版） |
| 设备 | Joy-Con 2 (L/R)、Pro Controller 2、NSO GameCube Controller 2 |
| OS | Windows only（因 `vgamepad`） |
| Bluetooth | ✅ 通过 `bleak`（跨平台 BLE 库） |
| Buttons | ✅ |
| Stick | ✅ 12-bit packed 解码 |
| IMU | ⚠️ **数据可解**（`solo_logic.py` 内含 `decode_gyro` / `decode_accel`），但该 Python 版不向 vgamepad 输出 gyro |
| Rumble | ✅ 命令已实现（`COMMAND_VIBRATION=0x0A`, `play_vibration_preset`） |
| Mouse Sensor | ⚠️ 数据字段已在布局中标注，未使用 |
| 语言 | Python 3.10+（`bleak` + `vgamepad`） |
| License | **MIT** |
| 代码质量 | 中等：单目录、逻辑按控制器类型分文件（`solo_logic.py` / `duo_logic.py` / `pro_logic.py` / `gc_logic.py`）、无测试、异常处理粗糙（`except: pass`）。可读性尚可。 |
| 成熟度 | 原型级，但**协议部分可信**：README 内含 `@german77`（知名 Switch 逆向者）提供的完整 notification 布局表。 |

**可复用要点（一手）**：
- BLE characteristics：`INPUT_REPORT_UUID = ab7de9be-89fe-49ad-828f-118f09df7fd2`（notify）、`WRITE_COMMAND_UUID = 649d4ac9-8eb7-4e6c-af44-1ea54fe5f005`（write）。
- 广播过滤：manufacturer id `1363` (0x0553)，manufacturer data 前缀 `01 00 03 7E`。
- IMU 使能：连续写两条命令
  `0c 91 01 02 00 04 00 00 2f 00 00 00`，`0c 91 01 04 00 04 00 00 2f 00 00 00`（间隔 ~0.5s）。
- Accel：signed 16-bit LE，`4096 = 1G`，offset `0x30/0x32/0x34`。
- Gyro：signed 16-bit LE，`48000 = 360°/s`，offset `0x36/0x38/0x3A`。
- Stick：3 字节 12-bit packed，`x = ((b1 & 0x0F) << 8) | b0`，`y = (b2 << 4) | ((b1 & 0xF0) >> 4)`，中心 `2048`。
- 重连 quirk：**短时间反复连接会触发控制器级冷却，数分钟内拒绝连接** → 必须实现 reconnect backoff。
- Left / Right **位布局不同**，必须按边配对。

**结论：`REFERENCE`**（作为协议与解码算法的主参考；License 允许直接改写为本项目 `adapter/` 的 Python 实现。不整体复用，因为绑定 Windows 虚拟手柄。）

---

### 1.2 `Misaka10571/joycon2-connector` — https://github.com/Misaka10571/joycon2-connector

| 字段 | 值 |
| --- | --- |
| Star | ~65（fork 数 ~5） |
| 最近更新 | 活跃维护中（`joycon2cpp` 的 fork，重做 GUI + 光学鼠标 + 多手柄） |
| 设备 | Joy-Con 2 单/双、Pro Controller 2、NSO GC Controller 2 |
| OS | Windows only（ViGEmBus） |
| Bluetooth | ✅ |
| Buttons | ✅ |
| Stick | ✅ |
| IMU | ✅ accel + gyro（可输出到 DS4 raw / DSU UDP） |
| Rumble | 未明确 |
| Mouse Sensor | ✅ 右 Joy-Con 2 光学鼠标 |
| 语言 | C++（Visual Studio 2022） |
| License | 存在（仓库有 LICENSE，抓取内容未展开具体类型，需以仓库为准） |
| 代码质量 | 中上：有 GUI（ImGui）、协议注释、多控制器支持。 |
| 成熟度 | 较成熟的 Windows 终端用户工具。 |

**一手要点**：确认 `Accel/Gyro 为 signed 16-bit`；温度公式 `25 + raw/127`；packet ID 在 `0x00`（4 字节，序号或时间戳）；同样记录了「反复连接触发数分钟冷却」。

**结论：`REFERENCE`**（与 `joycon2cpp` 同源，佐证协议；C++ + ViGEmBus 技术栈不复用。）

---

### 1.3 `TheFrano/joycon2cpp` — https://github.com/TheFrano/joycon2cpp（1.1 的官方后继，Phase 0 关键词命中，纳入评估）

| 字段 | 值 |
| --- | --- |
| Star | 较 py 版高（社区推荐的「更新版」） |
| 最近更新 | 活跃 |
| 设备 | Joy-Con 2 (L/R)、Pro Controller 2、NSO GC |
| OS | Windows only（ViGEmBus） |
| Bluetooth | ✅ |
| IMU | ✅ gyro + accel，多输出目标（DS4 Raw / DS4 Switch Emu / DSU UDP） |
| Rumble | ✅（NSO GC 除外；Pro 2 未测） |
| Mouse Sensor | ✅ 三种指针模式 |
| 语言 | C++ + ImGui + CMake |
| License | 见仓库 |
| 代码质量 | 中上，有协议文档段落。 |

**一手要点（与 py 版一致，互相印证）**：Left Joy-Con IMU-enabled notification：Packet ID `0x00`(4)、Buttons `0x04`(4)、Left Stick `0x08`(3, 12-bit packed)、Right Stick `0x0B`(3)、Accel `0x30–0x35`(signed16, 4096=1G)、Gyro `0x36–0x3B`(48000=360°/s)、Analog Trigger `0x3C–0x3D`(1 each)。

**结论：`REFERENCE`**（协议交叉验证来源；技术栈不复用。）

---

### 1.4 `XenuIsWatching/hid-nintendo2-dkms` — https://github.com/XenuIsWatching/hid-nintendo2-dkms

| 字段 | 值 |
| --- | --- |
| Star | ~0（新项目，v0.1.0，~28 commits） |
| 最近更新 | 早期活跃 |
| 设备 | Switch 2 Pro (057e:2069)、Joy-Con 2 Left (057e:2067)、Joy-Con 2 Right (057e:2066)、NSO GC (057e:2073) |
| OS | **Linux**（DKMS 内核模块，先于 mainline） |
| Bluetooth | ❌ **仅 USB**（README 明确 Bluetooth ✘） |
| Buttons | ✅ |
| Stick | ✅（Joy-Con 2 单摇杆） |
| IMU | ⚠️ **仅加速度计**；**陀螺仪未解码**（"the report slots carry only noise over USB at the current config; recovering it needs more reverse-engineering"） |
| Rumble | ✅ |
| Mouse | ❌ |
| 语言 | C（内核） |
| License | **GPL-2.0-or-later** |
| 代码质量 | 早期但规范（有 `docs/PROTOCOL.md`）。 |
| 成熟度 | v0.1.0，USB 通路可用。 |

**评估**：走 **USB HID** 而非 BLE，且陀螺仪在 USB 配置下拿不到 —— 与本项目「BLE + 完整 IMU」目标冲突；GPL 传染性也不利于与 MIT 上层混用。其 USB VID/PID 表（`057e:2066/2067`）对识别设备有参考价值。

**结论：`DO NOT USE`**（通路与许可证均不匹配；仅记录其 USB PID 作背景资料。）

---

### 1.5 `matiaspalmac/everything-imu` — https://github.com/matiaspalmac/everything-imu

| 字段 | 值 |
| --- | --- |
| Star | ~6（v1.0.7，~250 commits，活跃） |
| 最近更新 | 近期活跃 |
| 设备 | 13+ 手柄族：Joy-Con (L/R)、Switch Pro、**Joy-Con 2 / Pro 2**、DualSense、DualShock 4/3、PS Move、Wii Remote、3DS、PS Vita、Steam Deck…… |
| OS | Windows、Linux（.deb / AppImage） |
| Bluetooth | ✅（Joy-Con 2 *native BLE*） |
| Buttons / Stick | ✅ |
| IMU | ✅ **Joy-Con 2 hardware-validated**，BLE **~62 Hz**，含磁力计 + 磁力计校准向导 |
| Rumble | ✅（haptics 反馈） |
| Mouse Sensor | 未明确 |
| 语言 | Rust（后端）+ React/TypeScript（Tauri UI） |
| License | **MIT** |
| 用途 | 把手柄 IMU 通过 **UDP 转发给 SlimeVR-Server**（全身追踪） |
| 姿态解算 | **VQF / Madgwick / BasicVQF**，可按设备切换，默认 **VQF** |
| 代码质量 | 高：稳定版、崩溃上报、跨设备硬件验证。 |

**可复用要点**：
- **一手确认 Joy-Con 2 BLE 采样率 ≈ 62 Hz**（对应 GOAL.md §9「参考 60–100 Hz」，取 62 Hz 为设计基准）。
- 姿态解算选型证据：成熟项目默认 **VQF**，备选 Madgwick —— 支撑本项目在 [MOTION_ENGINE.md](./MOTION_ENGINE.md) 选 **Complementary + 可选 Madgwick**（VQF 实现复杂，游戏场景 Complementary/Madgwick 已足够，低延迟优先）。
- 架构证据：一个成熟项目同样采用「Native 读 IMU → 网络协议转发（UDP）→ 消费端」的解耦形态，印证本项目「Native → WebSocket」方向。

**结论：`REFERENCE`**（采样率、滤波选型、解耦架构三方面参考；不复用 Rust/Tauri/SlimeVR 代码 —— 目标输出不同。）

---

### 1.6 第一代参考 `tomayac/joy-con-webhid` — https://github.com/tomayac/joy-con-webhid

| 字段 | 值 |
| --- | --- |
| Star | ~187（~135 commits） |
| 设备 | **第一代** Joy-Con (L/R)、HVC-Controller、Ring-Con |
| OS | 跨平台（WebHID；Linux 需额外步骤） |
| Bluetooth | 经 **WebHID**（USB + 蓝牙皆可） |
| Buttons / Stick | ✅ |
| IMU | ✅ `enableIMUMode()` 开启 accel + gyro |
| Rumble | ✅ `rumble(d1, d2, intensity)` |
| Mouse | N/A |
| 语言 | TypeScript / JavaScript |
| License | **Apache-2.0** |
| API | `connectJoyCon()` → `open()` → `enableStandardFullMode()` → `enableIMUMode()`；事件 `hidinput` ≈ 60 fps，`joyCon.addEventListener('hidinput', ({detail}) => …)` |

**关键差异（重要，写入禁止事项校验）**：
- 第一代 Joy-Con 是 **Bluetooth HID**，所以 WebHID 直接可用。
- **Joy-Con 2 不是 HID**，是自定义 BLE GATT → **WebHID 对 Joy-Con 2 无效**，第一代的连接/使能流程**不能直接照搬**（GOAL.md §14.2 / §14.3 禁止把一代协议直接套用、禁止当普通 HID）。
- 可参考的是**上层形态**：`hidinput` 事件驱动、`detail` 里带 `accelerometers` / `gyroscopes` / `actualAccelerometer` / `actualOrientation` 的**事件对象设计** —— 本项目 `web/src/input/` 的 `InputProvider` 事件接口借鉴此形态。

**结论：`REFERENCE`**（上层 API 形态 + `JoyCon1Provider` fallback 的实现依据；协议层不可复用于 Joy-Con 2。）

---

### 1.7 玩法参考

| 项目 | URL | 用途 | 结论 |
| --- | --- | --- | --- |
| `open-video-game-library/MinimumTennis` | https://github.com/open-video-game-library/MinimumTennis | Joy-Con「按住按键 + 甩动」触发不同挥拍 —— 手势 = 阈值 + 方向 + 按键修饰的组合。启发 Gesture Engine 的「motionSpeed 阈值 + 主轴方向」判定。 | `REFERENCE` |
| Motion-Controlled Fruit Ninja (three.js + TensorFlow.js，dev.to 文章) | https://dev.to/devdevcharlie/motion-controlled-fruit-ninja-game-using-three-js-tensorflow-js-18de | three.js 场景组织、水果抛物线、切割 trail、命中检测。用输入源替换（手 → Joy-Con IMU）即为本项目 Phase 7。 | `REFERENCE` |
| `SilverTuxedo/JoyConBridge` | https://github.com/SilverTuxedo/JoyConBridge | 「Bridge」式暴露 Joy-Con state（buttons/stick/accel/gyro）。印证 Bridge 架构命名与职责。 | `REFERENCE` |

---

## 2. 关键词检索结论（GOAL.md Phase 0 要求的关键词）

| 关键词 | 结论 |
| --- | --- |
| `Joy-Con 2 BLE` / `Bluetooth protocol` / `GATT` | 自定义 GATT service，非 HID-over-GATT。核心 UUID 已公开（见 §1.1）。 |
| `Joy-Con 2 reverse engineering` | 主要成果集中在 `@german77` 提供、`TheFrano/joycon2py`+`joycon2cpp` 落地的 notification 布局；`joycon2-connector` 交叉印证。 |
| `Joy-Con 2 IMU` / `accelerometer` / `gyroscope` | 已解出：accel `4096=1G`、gyro `48000=360°/s`，signed 16-bit LE。offset 见协议文档。 |
| `Joy-Con 2 PC` / `Windows` | 终端用户方案均为 Windows + ViGEmBus 虚拟手柄（`joycon2cpp` / `joycon2-connector`）。 |
| `Joy-Con 2 Linux` | `hid-nintendo2-dkms`（USB only，无 gyro）；`bleak` 在 Linux 走 BlueZ 可用。 |
| `Joy-Con 2 Python` | `TheFrano/joycon2py`（`bleak`）—— 本项目 adapter 主参考。 |
| `Joy-Con 2 Rust` | `everything-imu`（Rust + Tauri），采样率与滤波参考。 |
| `Joy-Con 2 WebSocket` | **无直接命中**。没有现成「Joy-Con 2 → WebSocket」桥。→ 本项目 Phase 3 属**首次实现**，无可复用桥，自研。 |
| `Joy-Con 2 Web Bluetooth / WebHID` | WebHID 仅一代可用；Joy-Con 2 无浏览器直连先例。 |

---

## 3. 复用策略总表（GOAL.md §12.1 要求的明确结论）

| 项目 | 结论 | 复用内容 |
| --- | --- | --- |
| `TheFrano/joycon2py` | **REFERENCE** | 协议常量、IMU 使能命令、accel/gyro/stick 解码算法 → 改写进 `adapter/src/`（MIT 允许） |
| `TheFrano/joycon2cpp` | **REFERENCE** | 协议交叉验证、mouse/rumble 字段线索 |
| `Misaka10571/joycon2-connector` | **REFERENCE** | 协议交叉验证、温度公式、多控制器差异 |
| `XenuIsWatching/hid-nintendo2-dkms` | **DO NOT USE** | 仅记录 USB VID/PID（`057e:2066` Right / `057e:2067` Left / `057e:2069` Pro2 / `057e:2073` GC）；BLE 场景不涉及 |
| `matiaspalmac/everything-imu` | **REFERENCE** | BLE 采样率 ≈ 62 Hz、姿态解算选型（VQF/Madgwick）、解耦架构佐证 |
| `tomayac/joy-con-webhid` | **REFERENCE** | 上层事件 API 形态、`JoyCon1Provider` fallback 实现依据 |
| `MinimumTennis` / Fruit-Ninja three.js / `JoyConBridge` | **REFERENCE** | 玩法与 3D 场景、手势判定、Bridge 命名 |

> **不对任何项目给出 `REUSE`（整体复用/直接依赖）结论**：所有 Joy-Con 2 现有工程都绑定「Windows 虚拟手柄」或「SlimeVR/USB」等与本项目正交的输出目标。本项目复用的是**协议知识与算法**（`REFERENCE` 级），据 MIT/Apache 许可改写进自有分层代码。

---

## 4. 对后续阶段的直接影响

1. **技术方案锁定 B**（Native BLE Adapter → WebSocket → Browser）。理由完整版见 [ARCHITECTURE.md](./ARCHITECTURE.md)。
2. **Adapter 语言选 Python**（GOAL.md §7.1 优先级 Python→Rust→Node）：`bleak` 跨平台成熟、`joycon2py` 提供可直接改写的 MIT 参考实现、调试快。
3. **IMU 无需逆向**，直接用已知 UUID + 使能命令 + 布局；仍须真机验证（本环境无硬件 → 标 `EXPERIMENTAL`）。
4. **采样率基准 62 Hz**，WebSocket 不得降采样（GOAL.md §9）。
5. **必做 reconnect backoff**：社区一致报告「反复连接触发数分钟控制器级冷却」。
6. **姿态解算**：Complementary 为主，Madgwick 备选（见 MOTION_ENGINE.md）。
7. **校准专题**：官方「放平」系统级校准 vs. 游戏内「面向屏幕」朝向锚点 vs. Joy-Con 2 出厂 SPI 校准的可用性，另见 [CALIBRATION_RESEARCH.md](./CALIBRATION_RESEARCH.md)。

---

## 5. 来源清单

- TheFrano/joycon2py — https://github.com/TheFrano/joycon2py （README 协议表、`main.py`、`solo_logic.py`）
- TheFrano/joycon2cpp — https://github.com/TheFrano/joycon2cpp
- Misaka10571/joycon2-connector — https://github.com/Misaka10571/joycon2-connector
- XenuIsWatching/hid-nintendo2-dkms — https://github.com/XenuIsWatching/hid-nintendo2-dkms
- matiaspalmac/everything-imu — https://github.com/matiaspalmac/everything-imu
- tomayac/joy-con-webhid — https://github.com/tomayac/joy-con-webhid ；发布博客 https://blog.tomayac.com/2020/12/21/releasing-joy-con-webhid/
- open-video-game-library/MinimumTennis — https://github.com/open-video-game-library/MinimumTennis
- Motion-Controlled Fruit Ninja (three.js) — https://dev.to/devdevcharlie/motion-controlled-fruit-ninja-game-using-three-js-tensorflow-js-18de
- SilverTuxedo/JoyConBridge — https://github.com/SilverTuxedo/JoyConBridge
- `@german77`（GitHub）— joycon2py README 中 notification 布局的原始提供者
- bleak BLE 库 — https://github.com/hbldh/bleak

---

## 补充：2026-10-24 全按键与摇杆专项查阅的社区资料

只为回答具体问题而读相关文件，**未移植任何代码**（只取偏移、UUID、flash 地址等事实）。

| 仓库 @ commit | 读了什么 | 用于 | 与谁同源 |
| --- | --- | --- | --- |
| [ndeadly/switch2_controller_research](https://github.com/ndeadly/switch2_controller_research) @ `a3306b47` | `hid_reports.md`、`bluetooth_interface.md`、`commands.md`、`memory_layout.md`、`descriptors.md` | 按键域 0x04–0x07 全表（Home/Capture/右 ABXY/SL/SR，无 Sync 位）；广播 Product ID 判左右；左右专属 GATT char；命令应答 char；读 flash 命令与摇杆标定地址 `0x130A8` | **一手研究**（USB/BLE 抓包、flash dump） |
| [Logan-Gaillard/Joy2Win](https://github.com/Logan-Gaillard/Joy2Win) @ `932d6d7d` | `controllers/JoyconR.py`、`JoyconL.py`、`controller_command.py` | 右手掩码佐证、命令应答 UUID 佐证；固定摇杆边界 780..3260 **未采用** | README 致谢 ndeadly → 与上行**非独立** |
| [TheFrano/joycon2cpp](https://github.com/TheFrano/joycon2cpp) @ `2e410b7e` | `testapp/src/JoyConDecoder.cpp` | Home/Capture 掩码佐证；摇杆 ×1.7 增益 + 0.08 死区印证了 ±0.6 的根因，**增益未采用**；其 B/X 映射与 [ND] 不同，**未采用** | 与 `joycon2py` 同作者、同源（@german77 布局） |
| [OZORDI/JoyCon2Mac](https://github.com/OZORDI/JoyCon2Mac) @ `f5947df0` | `JoyCon2Mac/JoyConDecoder.cpp` | 查看 macOS 端摇杆处理：自动找中心但仍 ÷2048 → 同样到不了 1.0，**未采用** | 注释写明掩码照搬 joycon2cpp → 非独立 |

结论：社区只有两条来源线（ndeadly 一手研究 vs. @german77 布局），二者在右手 ABXY/SL/SR 上冲突，由本项目 2026-10-24 真机抓包裁决为 ndeadly 正确；摇杆出厂标定的 9 字节格式（中心 / +行程 / −行程）社区未写明，由本项目两只手柄的实测数据确定。详见 [JOYCON2_PROTOCOL.md](./JOYCON2_PROTOCOL.md) §E、§D.5、§H.1。
