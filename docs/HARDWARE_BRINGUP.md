# docs/HARDWARE_BRINGUP.md — Joy-Con 2 实机验证运行手册

> **目的**：把当前标记为 `EXPERIMENTAL / 未验收` 的 Joy-Con 2 BLE 链路，在真机上跑通并验收。
> **读者**：拿到 Joy-Con 2 实机的人 + 接手的执行 Agent。
> **前置**：软件侧（Phase 0–8）已全部完成并通过 fallback 验收，见 [TESTING.md](./TESTING.md)。本手册是 GOAL.md §13 要求的「Joy-Con 2 硬件验证单独完成、独立验收」的那一步。
>
> 一句话现状：**软件全部就绪，只差把真机接上、对照社区逆向的协议表逐条核对、把 `[未真机验证]` 标记去掉。**

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
- `python -m adapter.src.service --source joycon2` —— 完整链路 + WebSocket（`ws://127.0.0.1:8765`）。
- `cd web && npm run dev` —— 浏览器端，provider 选 `Joy-Con 2 (adapter)`。

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
| 按键（右） | ✅ 8 位 + StickPress + **C=`0x40`(字节0x05 bit6)** 逐个确认；plus/home 未分辨 |
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

### 下一步计划（下次接着做）

两只 Joy-Con 2 的地址（macOS 随机 UUID，重启蓝牙后可能变，届时重新 `--scan`）：
- 右 `59F5F588-7FB0-D2F8-1D87-AFA2209F86AA`（广播名 `Joy-Con 2 (R)`）—— 已验证
- 左 `BD708F44-2792-E1F3-F6B0-48B9B7851FCF`（广播名空 → side unknown）—— **待测**

工具都在 `scratchpad/`（本次会话生成，非仓库文件）：`capture.py`（脚本化抓取，逐包落盘）、`analyze2.py` / `analyze3.py`（暴力定位偏移 + 解码）、`ws_gyro.py` / `mon_swing.py`（实时监控）、`pw_*.py`（Playwright 驱动浏览器）。

**A. 左 Joy-Con 复核（J9）— 优先**
1. 只按左 Joy-Con 的 Sync，`.venv/bin/python -m adapter.src.bluetooth.prototype --scan` 确认地址。
2. `.venv/bin/python scratchpad/capture.py <左地址> --seconds 240 --out scratchpad/cap_left.jsonl`，人按动作表（§2 Step C 那套：静置六朝向 + 转动 + **逐个按 D-Pad / L / ZL / − / stick / SL / SR**）。
3. `.venv/bin/python scratchpad/analyze2.py scratchpad/cap_left.jsonl` → 核对：
   - 左按键掩码（`BUTTON_MASKS_LEFT`，byte `0x04` big-endian，注意左是 `data[4:7]`）—— 现有表来自 [FR-PY] 未经真机，重点看 D-Pad 四向 + `−` + stick 按下。
   - 左摇杆在 `data[10:13]`（Step B 已初步见 `8a b7 84` ≈ 中心，确认推杆四向正负）。
   - accel/gyro 偏移应与右一致（`0x30` / `0x36`）。
4. 有出入就改 `constants.py` / `buttons.py`，`cd adapter && ../.venv/bin/python -m pytest -q` 不破坏 roundtrip。
5. 回填本文件 §J 的 J9、`JOYCON2_PROTOCOL.md` §E。

**B. 手势四方向 + game.html（Step E #4/#5）— 需要人盯屏**
1. 两个终端：`.venv/bin/python -m adapter.src.service --source joycon2 --side <l/r>` + `cd web && npm run dev`。
   注意 `service.py` 扫不到设备会**整个退出**（不重试）——先按住 Sync 出跑马灯再启动。
2. 浏览器开 `localhost:5173/playground.html`，`window.__engine` 已无临时探针；要实时看内部判定就临时加回 `window.__engine = engine`（`playground/main.js:11`）跑 `scratchpad/pw_instr2.py`，完事 `git checkout`。
3. 逐个做透 `SLASH_LEFT / UP / DOWN`（同 `SLASH_RIGHT` 套路，见 [MOTION_ENGINE.md](./MOTION_ENGINE.md) §3.1）：确认各轴符号、调 `enterSpeed`（现 1.5，回挥偏弱可试 1.3）。
4. 四方向都稳后开 `game.html`，验 #5：切水果加分、切炸弹扣分不结束。
5. 若某方向体感反了 → `gestures.js` `_classify()` 翻对应轴符号，更新 §3 表。

**C. 收尾项**
- Step F：快速断连 5 次，看 `service.py` 日志 backoff `1→2→4→…→60s` + 第 4 次提示等待（J10）。
- Step G：链路三点打时间戳统计 `t_draw - t_recv` p50/p95，目标 p95 < 50 ms（J11）。填 `JOYCON2_PROTOCOL.md` §D.3。
- 温度 / 磁力计 / analog trigger：抓取里恒 0 或 garbage，低优先，标 UNVERIFIED 即可。
- 全部完成后按本文件 §3 表更新 `TESTING.md` §3、`README.md`，一个总结 commit。
