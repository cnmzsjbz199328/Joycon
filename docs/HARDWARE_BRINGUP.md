# docs/HARDWARE_BRINGUP.md — Joy-Con 2 实机验证运行手册

> **目的**：把当前标记为 `EXPERIMENTAL / 未验收` 的 Joy-Con 2 BLE 链路，在真机上跑通并验收。
> **读者**：拿到 Joy-Con 2 实机的人 + 接手的执行 Agent。
> **前置**：软件侧（Phase 0–8）已全部完成并通过 fallback 验收，见 [TESTING.md](./TESTING.md)。本手册是 GOAL.md §13 要求的「Joy-Con 2 硬件验证单独完成、独立验收」的那一步。
>
> 一句话现状（2026-10-24）：BLE 链路、IMU、**全部按键与两侧摇杆、左右同时连接、断连清键与重连**均已真机验收（§5 第 1–5 轮）。仍未做：体感 UP/DOWN 调参（暂停）、`game.html` 实机验收、延迟分位数（Step G）、backoff 全序列（Step F）。

---

## 0. 你（人）需要准备什么

| 项 | 说明 |
| --- | --- |
| Joy-Con 2 实机 | 至少 1 只。左右都测最好（按键位布局和摇杆偏移左右不同）。 |
| 电量 | 先充一会儿，低电量广播可能不稳。 |
| 一台 PC | 自带或外接 **Bluetooth LE** 适配器。macOS / Windows / Linux 均可（`bleak` 分别走 CoreBluetooth / WinRT / BlueZ）。 |
| 不要连着 Switch 2 | Joy-Con 2 当前不要处于「已连主机」状态。如果刚从主机上拆下来，等它进入可发现状态。 |
| 一个安静的桌面 | 标定时要把手柄放平不动 2 秒。 |
| 已装好环境 | `python -m venv .venv && .venv/bin/pip install -r adapter/requirements.txt`；`cd web && npm install`。 |

**你在整个过程里要做的物理动作，只有这几种**：
1. 按住 Joy-Con 2 **侧面的圆形 Sync 按钮**让它进入配对广播（不是从系统蓝牙设置里点配对——社区反复确认那样连不上）。
2. 第一次运行时，**给终端/Python 授予蓝牙权限**（macOS 会弹窗；Windows 一般免；Linux 确保当前用户能用 BlueZ）。
3. 标定时把手柄**放平、静止 2 秒**。
4. Agent 让你做特定动作时照做：比如「把手柄 Z 轴朝上放」「绕某个轴慢慢转 90°」「快速向右挥一下」。
5. 如果 Agent 说进入了「控制器冷却」，**把手柄放下等 2–3 分钟**再继续（这是 Joy-Con 2 自带的防抖动机制，不是 bug）。

---

## 1. 给接手 Agent 的总体说明

你要做的事，本质是**验证与订正**，不是重写：

- 协议常量、解包算法、标定、WebSocket、Motion Engine、Playground、3D Sword、Fruit Slash **全部已实现并测过**。
- Joy-Con 2 的 BLE 细节来自社区逆向（`TheFrano/joycon2py` 等，`@german77` 提供布局），已逐条写进 [JOYCON2_PROTOCOL.md](./JOYCON2_PROTOCOL.md) 并**标注了哪些没在真机上验证过**（`[未真机验证]`）。
- 你的任务：拿真机数据，把这些 `[未真机验证]` 一条条确认或订正，然后按 §J（那份文件里的 J1–J12 清单）走完验收。
- **不允许**：没跑通就说跑通了；把 Joy-Con 1 协议直接套过来；把它当普通 HID 处理；用 Mock 数据冒充硬件验收（GOAL.md §14）。
- **允许并鼓励**：如果某个 OS 上 BLE 就是不稳，按 GOAL.md §13 切到 fallback provider 继续，把 Joy-Con 2 部分保持 `EXPERIMENTAL`，如实记录卡在哪一步。

关键工具（都已存在）：
- `python -m adapter.src.bluetooth.prototype` —— 扫描 / 连接 / dump 原始 notification + GATT 树。
- `python -m adapter.src.reader --source joycon2` —— 解码后在终端实时打印 ax/ay/az、gx/gy/gz、按键、摇杆。
- `python -m adapter.src.service --source joycon2` —— 完整链路 + WebSocket（`ws://127.0.0.1:8765`）；默认**同时找左右两只**（`--side left|right` 只连一侧），`--record FILE.jsonl` 全程录包（原始报文 + 连接状态 + 页面发来的动作标注），`--source replay --file FILE.jsonl [--speed 10]` 回放。
- `cd web && npm run dev` —— 浏览器端：`input.html` 看全部按键/摇杆/事件（带引导式验收流程），Playground/Fruit Slash 的 provider 选 `Joy-Con 2 (adapter)`。

---

## 2. 执行步骤（按顺序）

### Step A — 扫描（对应 J1、J2）

Agent：
```bash
.venv/bin/python -m adapter.src.bluetooth.prototype --scan --scan-timeout 15
```
人：按住 Joy-Con 2 的 Sync 键。

**期望**：打印出一条设备，`manufacturer id 1363` + data 前缀 `01 00 03 7E`，`side=left/right/unknown`。
**记下**：设备地址（macOS 是一串 UUID，Windows/Linux 是 MAC）。

**若失败**：
- 完全没有设备 → 换 Sync 方式（长按到灯跑马），确认没连着主机，确认蓝牙权限。
- 有一堆别的蓝牙设备但没 Joy-Con → 正常，过滤器只认 Nintendo 厂商号。
- macOS `prototype.py` 卡住不动 → 多半是终端没有蓝牙权限：去「系统设置 → 隐私与安全性 → 蓝牙」把终端 / iTerm / 运行 Python 的程序勾上，或用 `tccutil` 重置后重跑。代码里已有超时保护，不会真的永久卡死。

### Step B — 连接 + dump（对应 J2、J3）

```bash
.venv/bin/python -m adapter.src.bluetooth.prototype --connect <地址> --no-imu --seconds 10
```
**期望**：`connected=True`；打印出完整 GATT 服务树；**未使能 IMU 时也应有按键/摇杆报文**在滚动。

**记下 / 订正**：
- **Service UUID**（当前 `constants.py` 里是 `[未验证]`）→ 从 GATT dump 里找到包含 `ab7de9be-…`（notify）和 `649d4ac9-…`（write）的那个 service，把它的 UUID 补进 [JOYCON2_PROTOCOL.md](./JOYCON2_PROTOCOL.md) §C.1。
- 未使能 IMU 时报文长度是多少（预期比 62 短）。

**若失败**：
- 连上就秒断 / 报 `temporary refusal` → 进入控制器冷却，等 2–3 分钟。`ReconnectPolicy` 会自己退避，但手动等更快。
- 连上但 `start_notify` 没数据 → 确认订阅的是 `INPUT_REPORT_UUID`；有的栈需要先 pair/bond，试试系统蓝牙里先配一次再跑。

### Step C — 使能 IMU + 核对偏移（对应 J4、J5、J6、J7 —— **最关键的一步**）

```bash
.venv/bin/python -m adapter.src.bluetooth.prototype --connect <地址> --seconds 20
```
（这次会发 `ENABLE_IMU_1/2` 两条命令）

**期望**：报文长度涨到 **~62 字节**；`0x30` 往后出现随姿态变化的值。

人：按 Agent 要求做这几个静置/转动动作，Agent 逐个核对：

| 动作 | 核对什么 | 通过标准 |
| --- | --- | --- |
| 手柄放平、Z 轴朝上、不动 | `0x30/0x32/0x34`（accel）三个 int16 LE | 有且仅有一个轴 ≈ ±4096（即 1 g），其余 ≈ 0。→ 确认 **int16 little-endian signed**（订正 §H 里 README「Field Example」那个 big-endian 笔误） |
| 静置不动 | `0x36/0x38/0x3A`（gyro） | 三轴 raw ≈ 0（只有噪声） |
| 绕某一轴慢慢转约 90° | 对应 gyro 轴积分出来的角度 | 方向自洽、量级合理（`raw * 360/48000` = °/s） |
| 快速旋转 | gyro raw 是否溢出 wrap | 记录是否有跳变（§D.4 注记里的未决问题） |
| 拨摇杆四个方向 + 回中 | `STICK_SLICE_LEFT/RIGHT`（现在是 `slice(10,13)` / `slice(13,16)`） | 回中时 x/y ≈ 0，四方向对应正负。**如果解出来是垃圾值**，改用布局表的 `0x08` / `0x0B`（即 `slice(8,11)` / `slice(11,14)`），哪个对用哪个，然后更新 `constants.py` 和 §E/§H |
| 按每个按键 | `BUTTON_STATE_SLICE_LEFT/RIGHT` + `decoder/buttons.py` 的掩码 | 每个键点亮唯一的 bool。**顺便抓 `C` 键**（右 Joy-Con 2 新增键，掩码当前未知），补进 `BUTTON_MASKS_RIGHT` 和 §E |
| 数 1000 包计时 | 采样率 | ≈ 62 Hz（`everything-imu` 的数据点），记录实测值到 §D.2 |

**订正落点**：所有需要改的常量都在 `adapter/src/protocol/constants.py`（偏移、slice、scale）和 `adapter/src/decoder/buttons.py`（按键掩码）。改完跑 `cd adapter && ../.venv/bin/python -m pytest -q` 确认没破坏解码 roundtrip。

**若使能 IMU 后报文长度没变**：可能 Joy-Con 2 也需要「standard full mode」前置命令（Joy-Con 1 是 `0x03 0x30`）。在 `bluetooth/connection.py` 的 `_initialise()` 里，`enable_imu` 之前加一条试试，记录结果到 §F。

### Step D — 终端解码 reader（对应 J5、J6、J9）

```bash
.venv/bin/python -m adapter.src.reader --source joycon2 --side left
```
人：先按提示放平静止 2 秒完成标定，然后随意动。

**期望**：标定后静置时 `A[g] ≈ 0 0 1`、`G[dps] ≈ 0 0 0`；转动时对应轴动、方向直觉一致；按键/摇杆实时反映。左右各测一遍。

### Step E — 完整链路 + 浏览器（对应 §17 第 1、2、3、4 项）

两个终端：
```bash
# 终端 1
.venv/bin/python -m adapter.src.service --source joycon2 --side left
# 终端 2
cd web && npm run dev
```
浏览器打开 `http://localhost:5173/playground.html` → provider 选 **Joy-Con 2 (adapter)** → Connect → 按提示标定。

**验收**（对照 GOAL.md §17）：
1. Adapter 里 `in ≈ out ≈ 60 Hz`，`out/in == 1.00`（不降采样）。
2. Playground 实时显示 accel / gyro（数字 + 示波器），Connection = Connected，Controller = LEFT/RIGHT。
3. 现实中转动手柄 → 网页里 3D 剑同步旋转。
4. 快速挥动 → 正确识别 `SLASH_LEFT/RIGHT/UP/DOWN`。
   - **如果方向反了**（比如向右挥出的是 `SLASH_LEFT`）：这取决于 Joy-Con 姿态和左右手，在 `web/src/motion/gestures.js` 顶部 / `GestureRecognizer` 构造参数里翻转对应轴符号即可，**不动引擎其它部分**。把最终符号约定记进 [MOTION_ENGINE.md](./MOTION_ENGINE.md) §3。
5. 打开 `game.html` → 挥手柄 → 水果被切开 → Score 增加；切炸弹扣分且游戏不结束。

### Step F — 重连冷却（对应 J10、GOAL.md §7.1）

人：故意快速断开重连 5 次（关掉 adapter 再开，或让手柄睡眠再唤醒）。
**期望**：复现「数分钟内拒连」；`service.py` 日志显示退避从 1s → 2s → 4s …→ 60s，第 4 次失败后提示「等待 2–3 分钟」。确认 `ReconnectPolicy` 行为符合预期。

### Step G — 延迟（对应 J11、GOAL.md §9）

在链路上打三个时间戳（adapter 收到 `t_recv`、浏览器收到 `t_ws`、页面渲染 `t_draw`），统计 `t_draw - t_recv` 的 p50 / p95。
**目标**：p95 < 50 ms。把实测值填进 §D.3。可以在 `joycon2-provider.js` 收到 frame 时和 rAF 里各记一个数，控制台打印分位数。

---

## 3. 验收完成后要更新的文件

| 文件 | 改什么 |
| --- | --- |
| `docs/JOYCON2_PROTOCOL.md` | 删掉已确认项的 `[未真机验证]` 标记；填入 Service UUID、实测采样率、延迟分位数、C 键掩码、字节序结论、陀螺满量程结论；§J 的 J1–J12 打勾 |
| `adapter/src/protocol/constants.py` | 若偏移 / slice / scale 与社区表不同，按真机订正 |
| `adapter/src/decoder/buttons.py` | 补 `C` 键掩码；订正任何对不上的键 |
| `web/src/motion/gestures.js` 或 `MOTION_ENGINE.md` §3 | 记录真机确认的手势轴符号约定 |
| `docs/TESTING.md` §3 | 把 §17 第 1、3、4 项里依赖硬件的部分从 `EXPERIMENTAL / 未验收` 改为 `已验收`，附实测数据 |
| `README.md` | 顶部的 "Joy-Con 2 BLE is EXPERIMENTAL" 说明相应下调 |
| 提交 | 一个 commit：`Hardware bring-up: Joy-Con 2 BLE verified on <OS>`，附带上述改动和实测数据 |

---

## 4. 如果 BLE 在这台机器 / 这个 OS 上就是不行

按 GOAL.md §13，**不要停**：
- 浏览器 provider 切 `Joy-Con 1 (WebHID)`（若手边有一代）/ `Keyboard` / `Gamepad` / `Mock IMU`，Motion Engine 和游戏照常验收。
- Joy-Con 2 部分保持 `EXPERIMENTAL`，在 `docs/TESTING.md` §3 如实写清楚**卡在 Step 几、什么现象、试过什么**。
- 常见「换台机器就好」的情况：某些蓝牙芯片（尤其老的 Intel、部分 Linux BlueZ 版本）对 Joy-Con 2 的私有 GATT 支持差；换 OS 或换一个 USB BLE dongle 往往能解决。

---

## 5. 实测记录

### 第 1 轮 — 2026-09-06，Mac mini（macOS 15，CoreBluetooth），右 Joy-Con 2

**环境**：`.venv` + `bleak 3.0.2`；两只 Joy-Con 2（地址 macOS 随机 UUID）：
- 右 `59F5F588-7FB0-D2F8-1D87-AFA2209F86AA`（广播名 `Joy-Con 2 (R)`）
- 左 `BD708F44-2792-E1F3-F6B0-48B9B7851FCF`（广播名空 → side unknown）

**做法**：`prototype.py` 跑 Step A/B/C；再用脚本化 90 s 动作抓取（`scratchpad/capture.py`，240 s 窗口逐包落盘）+ 离线分析（`scratchpad/analyze*.py`，按重力模长 / 陀螺能量暴力定位偏移）。

**结果**（详见 [JOYCON2_PROTOCOL.md](./JOYCON2_PROTOCOL.md) §J 清单）：

| 项 | 结论 |
| --- | --- |
| Step A 扫描 | ✅ 两只都识别（manuf 1363 + 前缀 `01 00 03 7e`） |
| Step B 连接 + GATT | ✅ Service UUID = `ab7de9be-89fe-49ad-828f-118f09df7fd0`；未使能 IMU 报文 63 B / 28 Hz |
| Step C IMU + 偏移 | ✅ 只发 `ENABLE_IMU_1/2` 即出 IMU（无需 full-mode 前置）。**报文 63 B（非 62）**。accel `0x30` / gyro `0x36` / 右 stick `0x0D`——**与代码一致**，只订正 battery `0x1C→0x1F`、补 C 键 `0x000040` |
| accel | ✅ 六朝向重力单轴 ≈ 1.00 g；int16 LE signed 确认 |
| gyro | 🟡 静置 <2 dps、转动定轴自洽；峰值仅 ~95 dps 无 wrap；未做精确角度标定 |
| 采样率 | 🟡 **33.5 Hz**（疑 macOS 连接间隔限制）；`0x00` = 毫秒时间戳 |
| 按键（右） | 🟡 8 位 + StickPress + **C=`0x40`(字节0x05 bit6)** 各点亮唯一一位；plus/home 未分辨。**更正（2026-10-24）**：当时只确认了“每键一位”，没核对名字——A↔B、X↔Y、SL↔SR 实际是对调的，第 5 轮订正 |
| 重连冷却 | 🟡 观察到：连过一次后短时间再连 `TimeoutError`（即社区说的控制器级冷却）；未跑满 backoff 序列 |

**代码改动**：`adapter/src/protocol/constants.py`（Service UUID、battery 偏移、注释）、`adapter/src/decoder/buttons.py`（C 键）。19 项 pytest 仍全过；真机包端到端 `decode_packet` 验证通过。

### 第 2 轮 — 同日，Step E 完整链路 + 浏览器（右 Joy-Con）

`service.py --source joycon2 --side right` → `web` (vite) → 无头 Chromium（Playwright）连 Playground。

| 验收项（GOAL §17） | 结果 |
| --- | --- |
| 1 Adapter `out/in == 1.00` 不降采样 | ✅ `in=33.5 Hz out=33.5 Hz out/in=1.00 short=0` |
| 2 Playground 显示 accel/gyro + Connected + LEFT/RIGHT | ✅ Connected / **RIGHT** / Calibrated；示波器 + 数字实时；3D 剑渲染正常（截图存档） |
| 3 转动手柄 → 3D 剑同步 | ✅ 朝向跟踪实时（yaw 随转动 0°→113°，pitch/roll 跟手） |
| 4 快挥 → `SLASH_LEFT/RIGHT/UP/DOWN` | 🟡→ **`SLASH_RIGHT` 已做透**：水平前挥稳定判 `SLASH_RIGHT`（强度 0.6–0.8，`gyro.z+` 主导，方向 `[-0.44,-0.15,+0.87]`），`THRUST` 抢占已修（window-peak）。`LEFT/UP/DOWN` 待逐个调力度一致性 |
| 5 `game.html` 切水果加分 | ⬜ 未测（等 4 个方向都稳） |

**关键发现**：`GestureRecognizer` 阈值是按 Mock IMU（合成 900 dps ≈ 15.7 rad/s）调的；真机 Joy-Con 2 挥击峰值只有 **~1.8–2.7 rad/s**（轻晃 0.9），`enterSpeed 6.0` 够不到。
已把 `gestures.js` 默认值降到 `enterSpeed 1.5 / exitSpeed 0.6 / fullSpeed 2.6`，17 项 web 测试全过（`gentle` 用例的 `peak` 3→1.0）。
另修 `THRUST` 抢占（改看窗口内转速峰值，见 [MOTION_ENGINE.md](./MOTION_ENGINE.md) §3.1）。

陀螺满量程复核：拼命转 raw 峰值 ~20000/32767，**未饱和** → [FR-PY] 的 `360/48000`（FS ±245 dps）对真机合理，D.4 的 wrap 担忧基本排除（常速下）。

**代码改动（第 2 轮）**：`web/src/motion/gestures.js`（阈值 retune + `THRUST` window-peak）、`web/test/gestures.test.js`（gentle 用例）。

### 第 3 轮 — 2026-09-28，左 Joy-Con 2 复核（J9）

两只 Joy-Con 2 的地址（macOS 随机 UUID，重启蓝牙后可能变，届时重新 `--scan`）：
- 右 `59F5F588-7FB0-D2F8-1D87-AFA2209F86AA`（广播名 `Joy-Con 2 (R)`）—— 已验证
- 左 `BD708F44-2792-E1F3-F6B0-48B9B7851FCF`（广播名 `Joy-Con 2 (L)`）—— **本轮验证完成**

工具重新写在 `scratchpad/`（本次会话生成，非仓库文件，环境重启后已丢失，照旧重建）：`capture.py`（连接 + 使能 IMU + 逐包落盘 JSONL + 实时打印按键/accel/gyro/stick 变化，用于边做动作边核对）。

流程：只按左 Joy-Con 的 Sync → `--scan` 确认地址（**注意广播窗口只有几十秒，过期要重新按 Sync 才能连上**，本轮踩了一次坑）→ `capture.py <左地址> --side left --seconds 300` → 人按 §2 Step C 那套动作（静置 → 慢转 90° → 快速转 → 摇杆四向 → 逐个按 D-Pad/−/L/ZL/stick/SL/SR）。

| 验证项 | 结果 |
| --- | --- |
| 连接 + IMU 使能 | ✅ 与右一致，`ENABLE_IMU_1/2` 后 63 字节报文含活值 |
| Accel 静置 | ✅ 单轴 ≈0.98–1.0 g，其余 ≈0（int16 LE 假设成立） |
| Gyro 静置/转动/快转 | ✅ 静置 <0.2 dps；慢转、快转（峰值约 -46.5 dps）方向自洽，**未见溢出/wrap** |
| 摇杆 `data[10:13]` | ✅ 回中 ≈0，四向推杆方向正确、连贯（非垃圾值）；幅度约 ±0.5–0.6，未测到贴满 ±1.0（当时判断为推杆力度问题——**更正（2026-10-24）**：是归一化除以 2048 而实际行程只有 ±1150–1300，第 5 轮修复） |
| 十个按键掩码（D-Up/Down/Left/Right/−/L/ZL/Stick/SL/SR） | ✅ **全部与 `BUTTON_MASKS_LEFT` 现有假设完全一致，无需改动任何常量** |
| 采样率 | 33.2 Hz（与右一致，确认是 macOS BLE 连接间隔限制，非单只手柄问题） |

**结论：J9 完成，`constants.py` / `buttons.py` 左侧假设全部通过真机验证，本轮零代码改动**（只更新了文档/常量注释里的 HW-VERIFIED 标注）。已回填 `JOYCON2_PROTOCOL.md` §E、§J（J9）、§K。

**B. 手势四方向 + game.html（Step E #4/#5）— 需要人盯屏。**

### 第 4 轮 — 2026-09-28（同日），左 Joy-Con 2 手势调参

不用 Playwright 探针读 `window.__engine`（那套一次性脚本已随会话丢失），改用 headless Playwright 常驻监看 `#gesture` DOM 文本 + 临时 `console.log` 读 `GestureRecognizer` 内部状态（`accelMag`/`windowPeakSpeed`/`holdCount`），工具在 `scratchpad/watch_gesture.py`（本会话生成，非仓库文件）。两个终端起 `adapter.src.service --side left` + `npm run dev` 不变。

用户自然挥动（不是刻意孤立的单次全力挥砍）后发现左手柄挥动几乎全被判成 `THRUST`，查明是两层问题（详见 [MOTION_ENGINE.md](./MOTION_ENGINE.md) §3.2）：
1. `THRUST` 判定时机太早（线加速度比转速先冲高）→ 加了 `thrustHoldFrames`（需连续 N 帧低转速+高加速度才下结论，默认 4）。
2. **真正根因**：自然/连贯动作的挥砍转速峰值（1.2–1.5 rad/s）本来就低于 9-06 单次全力挥砍标定出的 `enterSpeed=1.5` → 降到 `1.1`。
3. 用户提出人的连贯反向动作（挥上接挥下、挥左接挥右）不会经过 `exitSpeed`，原峰值追踪只记单个最大值会丢一半手势 → 加了同轴反号即分段的逻辑。

修完左手柄自然连贯挥动 `SLASH_LEFT/RIGHT/DOWN`（`UP` 也出现过）11/12 次判对，1 次残留 `THRUST` 误判（已知限制，见 §3.2，判断不值得继续调）。`web/test/gestures.test.js` 全过（17/17），`mock-imu-provider.js` 的合成 THRUST 峰值从 3.2 提到 6.0 g 配合新的连续帧要求。

**代码改动**：`web/src/motion/gestures.js`（`enterSpeed 1.5→1.1`、新增 `thrustHoldFrames`、新增峰值同轴反号分段）、`web/src/input/mock-imu-provider.js`（THRUST 合成峰值 3.2→6.0）。

**仍未做**：`game.html` 切水果验收（#5）——手势基本稳定后应该顺理成章，但还没实测过。

### 第 5 轮 — 2026-10-24，全按键与摇杆专项（左右同时连接）

**目标**：让其他项目不懂 BLE/IMU 也能通过 WebSocket 稳定读到左右手柄全部按键与摇杆。体感调参暂停，不在本轮。
**工具**（均已入库）：`service.py --source joycon2 --record adapter/captures/<文件>.jsonl`（一次连左右两只）、`web/input.html`（全部按键/摇杆/事件 + 引导流程）、`adapter/tests/fixtures/hw_2026-10-24_input.jsonl`（本轮抓包裁剪，供回放与回归测试）。分析用的一次性脚本在会话 scratchpad（逐步骤原始位统计、摇杆扇区统计），未入库。
**抓包**：`adapter/captures/2026-10-24-input.jsonl`（A 段）、`…-round2.jsonl`（B–D 段），本地保留（`.gitignore`）；入库的是裁剪后的 fixture（3 个时间窗，原始字节未改，只丢掉无变化的包）。

| 段 | 用户动作 | 结果 |
| --- | --- | --- |
| A | 按 Sync 连两只；在页面上自由按全部键、拨摇杆 | 两只同时连上（各 33.2 Hz）；**左右判定来自广播 Product ID**（`0x2067`/`0x2066`），GATT 复核一致；**两只的摇杆出厂标定 `0x130A8` 读取成功**；用户反馈 **ABXY 对应不对** → 原始位与 [ND]/Joy2Win 映射一致、与本项目旧表（[FR-PY]）A↔B、X↔Y、SL↔SR 对调 |
| — | 修复：右手掩码改按 [ND]；摇杆改用出厂标定（中心 + 四向行程，格式由 A 段数据确定：中心/＋行程/－行程） | 单元测试 80 项通过后重启 adapter |
| B | 按页面按键网格顺序逐个按左 11 键、右 12 键 | 每键唯一一位；**用户确认右手 A/B/X/Y/SL/SR 与印字一致**；左手在 IMU 标定完成（17:42:18）之前按下的 ↑…Capture 全部正常送达 → **按键不依赖 IMU 标定** |
| C | 两摇杆：静置、四向推到底、绕圈 | 静置预死区偏移最大 0.038（死区 0.08），输出精确 0；四向峰值 0.98–1.00；八扇区（含对角）全部 ≥0.99 |
| D | 两摇杆同时推到底；右 A+B+R 同按；按住 A 时短按 Sync；长按 Sync 到跑马灯后按 A | 两摇杆同时 ≥0.95 共 2.4 s；A+B+R 同按 7 s 无串键，A 连续 18 s；断开前最后一包 A=按下，`disconnected` 约 0.7 s 后到达（客户端据此释放 A，e2e 用这份真机抓包回放验证）；长按 Sync 后自动重连，A 正常 |

**重连诊断**：第一次断开后 adapter 按地址重试约 2 分钟都没找到手柄；另起独立扫描并请用户再按 Sync（这次灯在跑马）→ 17:52:31 扫描看到配对广播（地址未变）、17:52:32 adapter 已自动重连。结论：**断开后手柄不会自己再向本机广播，必须长按 Sync 到指示灯跑马**；adapter 无需重启。已把状态 `hint` 改成“长按 Sync 直到灯跑马”。
**Sync**：两份抓包共 78 064 包，按键域内无任何未映射位，`0x07` 恒为 `0xE0` → Sync 不作为输入上报。
**测试节奏的教训**：页面的英文“引导式验收流程”实际没被使用（两次都直接点按网格），所以动作标注（mark）为 0；改为聊天里给中文动作清单 + 从原始抓包自动判定后顺利完成。以后实机测试直接给中文步骤清单，不依赖页面上的英文引导面板。

**代码改动**：`decoder/buttons.py`（右手 A/B/X/Y/SL/SR 订正，新增 Home、Capture）、`calibration/stick.py`（出厂标定 + 分方向行程 + 圆形限幅 + 径向死区）、`bluetooth/connection.py`（读出厂标定、GATT 侧别、扫不到不计冷却、重连提示）、`sources.py`/`service.py`（左右同时、状态与帧同队列、按键不等 IMU）、协议 v2（`shared/protocol/`）、`web/input.html`、`examples/`。新增真机回归 `adapter/tests/test_hw_capture.py`。

### 体感 UP/DOWN 轴单独调参（计划，**暂停**，未执行）— 左 Joy-Con 2

**触发**：用户反馈实际体验是"上下反应慢、左右反应快"。已排除的假设：这**不是** Nintendo Switch Sports 那种"对屏幕按键"朝向（yaw）校准缺失导致的——那个校准解决的是水平朝向漂移，和 pitch（上下）轴的响应速度是两个正交的问题；代码里也确认过 `motion-engine.js` 对 x/y/z 三轴用的是同一套去偏置/死区/低通（`gyroF = this.gyroLP.update(...)`），没有针对某个轴的额外滤波延迟。完整推理见与用户的讨论（本文件对应会话）。

**工作假设（待验证，不要预设结论）**：pitch 轴（`gx`，对应 SLASH_UP/DOWN）的自然挥动峰值转速，可能比 yaw 轴（`gz`，对应 SLASH_LEFT/RIGHT）更低——类似第 4 轮发现的"自然连贯动作峰值低于孤立全力挥砍标定值"，但可能在 pitch 轴上更严重（人体工学：手腕上下屈伸的角速度范围通常小于左右尺偏/桡偏，`docs/MOTION_ENGINE.md` §3.1 已记录"左向比右向弱"的同类现象）。当前 `enterSpeed`/`exitSpeed` 是套在 `speed = hypot(gx,gy,gz)` 整体幅值上的**单一标量**，不分轴——如果 pitch 轴天然峰值系统性偏低，单一标量阈值可能无法同时兼顾两个轴，可能需要引入**分轴阈值**（这是比第 4 轮更大的架构改动，动手前应该先跟用户确认要不要做，不要直接实现）。

**执行前必读**：`docs/MOTION_ENGINE.md` §3.2（第 4 轮的完整问题分析）、`web/src/motion/gestures.js`（现状代码）。

**测试节奏（重要，参考本项目记忆 `joycon2-hardware-collab-style`）**：
- 开始前先跟用户说清楚打算测几轮、什么条件下算完成（例如"先收集一轮数据，改一次，验证一次；多数判对就停"），不要开放式"再挥几次"循环。
- 优先一轮拿到足够信息（用临时 debug log 直接读内部数值），而不是"猜一个阈值→再测一轮→猜下一个"来回试探。

**步骤**：
1. 环境：确认 `.venv/bin/python --version` 能跑；若报 "no such file or directory"，先 `brew link python@3.14`（本机已知会反复失效）。
2. 左 Joy-Con 按 Sync（广播窗口只有几十秒，别扫描完拖久了再连）→
   `.venv/bin/python -m adapter.src.bluetooth.prototype --scan --scan-timeout 12` 确认地址 →
   立刻 `.venv/bin/python -m adapter.src.service --source joycon2 --side left`（后台）。
3. `cd web && npm run dev`（后台）。
4. 重建 `scratchpad/watch_gesture.py`（本会话原文见下，非仓库文件，需要时直接照抄）：

   ```python
   """Headless Playwright watcher for the Motion Playground's live #gesture readout."""
   from playwright.sync_api import sync_playwright
   import time

   URL = "http://localhost:5173/playground.html"

   with sync_playwright() as p:
       browser = p.chromium.launch(headless=True)
       page = browser.new_page()
       page.add_init_script("window.__DEBUG_THRUST = true;")
       page.on("console", lambda msg: print(f"[console] {msg.text}", flush=True) if "[DBG]" in msg.text else None)
       page.goto(URL)
       page.wait_for_load_state("networkidle")
       page.click(".cp-connect")
       page.wait_for_function("document.querySelector('.cp-conn')?.textContent === 'Connected'", timeout=15000)
       print(f"connected, controller={page.locator('.cp-ctrl').text_content()}", flush=True)
       page.wait_for_function("document.querySelector('.cp-cal')?.textContent === 'Calibrated'", timeout=15000)
       print("calibrated, watching #gesture ...", flush=True)
       last = None
       t0 = time.monotonic()
       while True:
           text = page.locator("#gesture").text_content()
           if text != last and text and "waiting for motion" not in text:
               last = text
               print(f"[{time.monotonic() - t0:7.2f}s] GESTURE: {text}", flush=True)
           elif text != last:
               last = text
           time.sleep(0.1)
   ```

5. 在 `web/src/motion/gestures.js` 的 `update()` 里、算完 `windowPeakSpeed` 之后，临时加一行（第 4 轮用过同样的手法，测完要删掉，不要提交）：
   ```js
   if (globalThis.__DEBUG_THRUST) {
     console.log(`[DBG] t=${t.toFixed(3)} gx=${gyro[0].toFixed(2)} gy=${gyro[1].toFixed(2)} gz=${gyro[2].toFixed(2)} speed=${speed.toFixed(2)} windowPeakSpeed=${windowPeakSpeed.toFixed(2)}`);
   }
   ```
6. 后台跑 `watch_gesture.py`（输出重定向到文件，例如 `> watch.log 2>&1`，用 `run_in_background`）；确认 adapter 日志 `clients=1`（不是 0——0 说明网页没连上，见第 4 轮踩过的坑）。
7. 让用户**自然地、连贯地**只做上/下方向挥动（不要求刻意用力，就是平时会做的动作），一次性做一轮（比如 8-10 次），不要来回反复确认。
8. 读 `watch.log`：
   - 统计 `SLASH_UP` / `SLASH_DOWN` 命中率。
   - 对每次挥动，看 `[DBG]` 行里 `gx`（pitch 分量）的峰值，和已知的 yaw 轴基线（左右挥动峰值 1.2–1.5 rad/s，现 `enterSpeed=1.1` 能覆盖）对比：明显更低就证实了工作假设。
9. 决策：
   - 若 pitch 峰值和 yaw 峰值量级相近（也是 1.1+ 能覆盖的范围）→ 说明不是分轴阈值问题，可能是别的原因（比如这次样本恰好挥得轻），如实汇报，不要强行调参凑数据。
   - 若 pitch 峰值系统性更低（比如普遍 <1.0）→ 向用户说明"pitch 轴需要专门更低的阈值"这个判断，**问用户要不要做分轴阈值**（架构改动）还是先简单地把 `enterSpeed` 整体再降一点（简单但会牺牲左右方向的抗噪性，这个 trade-off 要讲清楚，不要替用户决定）。
10. 改完照第 4 轮的模式验证：跑 `web/test/gestures.test.js`（`cd web && npm test`），再拿真机验证一轮，达到和第 4 轮相当的命中率（比如 8/10+）就停，更新本文件 + `docs/MOTION_ENGINE.md` §3（新增 §3.3 或并入 §3.2）+ 项目记忆。
11. UP/DOWN 稳定后才进入 `game.html` 验收（Step E #5）——不要在手势还不稳的时候去测游戏局面。

**C. 收尾项**
- Step F：快速断连 5 次，看 `service.py` 日志 backoff `1→2→4→…→60s` + 第 4 次提示等待（J10）。
- Step G：链路三点打时间戳统计 `t_draw - t_recv` p50/p95，目标 p95 < 50 ms（J11）。填 `JOYCON2_PROTOCOL.md` §D.3。
- 温度 / 磁力计 / analog trigger：抓取里恒 0 或 garbage，低优先，标 UNVERIFIED 即可。
- 全部完成后按本文件 §3 表更新 `TESTING.md` §3、`README.md`，一个总结 commit。
