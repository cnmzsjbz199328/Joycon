# docs/JOYCON2_PROTOCOL.md — Joy-Con 2 协议摘要

> 对应 GOAL.md **Phase 1**。
> **状态：核心链路已在真机验证（2026-09-06 右 / 2026-09-28 左 / 2026-10-24 左右同时连接，macOS CoreBluetooth）。** 详见 [HARDWARE_BRINGUP.md](./HARDWARE_BRINGUP.md) §5「实测记录」。
> **全部按键与摇杆（2026-10-24 专项）**：左 11 键 + 右 12 键逐个真机确认（右 A/B/X/Y/SL/SR 订正）、Home/Capture 补齐、Sync 不上报；摇杆改用手柄出厂标定，四向/八扇区满行程 ≥0.95、静置精确为 0；左右同时输入、断连清键、长按 Sync 重连均真机通过。对外接口见 [shared/protocol/README.md](../shared/protocol/README.md)（协议 v2）。
> 本文件汇总社区逆向成果并逐条标注来源；`[未真机验证]` 表示尚未复核，`[真机确认 <日期>]` 表示已用真机抓包核对。
> 仍待办：延迟分位数（J11）、高速旋转陀螺满量程（D.4）、温度/磁力计字段。
>
> 来源代号：
> - **[FR-PY]** = `TheFrano/joycon2py`（README 布局表 + `main.py` + `solo_logic.py`），布局原始提供者 `@german77`。
> - **[FR-CPP]** = `TheFrano/joycon2cpp` README 协议段。
> - **[MIS]** = `Misaka10571/joycon2-connector` README。
> - **[EIMU]** = `matiaspalmac/everything-imu`（采样率 / 硬件验证声明）。
> - **[DKMS]** = `XenuIsWatching/hid-nintendo2-dkms`（USB VID/PID）。
> - **[ND]** = [`ndeadly/switch2_controller_research`](https://github.com/ndeadly/switch2_controller_research) @ `a3306b473acff0d6844fb1e288883a3940df0baf`（2026-09-08）：`hid_reports.md`、`bluetooth_interface.md`、`commands.md`、`memory_layout.md`、`descriptors.md`。**一手研究**（USB 描述符、BLE 抓包、flash dump），与 [FR-PY] 不同源。
> - **[J2W]** = [`Logan-Gaillard/Joy2Win`](https://github.com/Logan-Gaillard/Joy2Win) @ `932d6d7d`（2026-05-19）`controllers/JoyconR.py` / `JoyconL.py` / `controller_command.py`。README 致谢 ndeadly → 按键表**与 [ND] 非独立**。
> - **[FR-CPP]**（续）[`TheFrano/joycon2cpp`](https://github.com/TheFrano/joycon2cpp) @ `2e410b7e`（2026-09-10）`testapp/src/JoyConDecoder.cpp`；与 [FR-PY] 同作者、同源（@german77 布局）。
> - **[JC2M]** = [`OZORDI/JoyCon2Mac`](https://github.com/OZORDI/JoyCon2Mac) @ `f5947df0`（2026-09-06）`JoyCon2Mac/JoyConDecoder.cpp`；按键位注释写明照搬 joycon2cpp → **非独立**。
>
> 2026-10-24 专项只从上述仓库取**事实**（偏移、UUID、flash 地址），没有移植任何代码，因此无需引入其 MIT 许可文本。社区内部实际只有两条来源线：① [ND]（及引用它的 [J2W]）；② @german77 布局（[FR-PY]/[FR-CPP]/[JC2M]）。两线冲突处（右手 ABXY/SL/SR）由本项目真机抓包裁决，见 §E。

---

## A. Joy-Con 2 如何进入配对模式？

按住 Joy-Con 2 侧面的 **Sync 按钮**（第一代同位置），进入 BLE 可发现的广播状态。
- 来源：[FR-PY] README "please use the Sync button as directed by the program"。
- **不要**用系统蓝牙设置里的「配对码/按键配对」流程 —— [FR-PY] 明确 "Pairing through a button press - this never works"。
- `[真机 2026-09-06 确认（macOS）]` **无需系统层 bond**：`bleak` `BleakScanner` 扫到后直接 `BleakClient(addr).connect()` 即成功。每次连接都要求控制器处于广播态（按 Sync 跑马灯）——本项目不做 OS 级配对，掉线后需再按 Sync 才能重连。

---

## B. PC 能否稳定发现并连接？

能，通过通用跨平台 BLE 库 `bleak`（Windows WinRT / macOS CoreBluetooth / Linux BlueZ）。
- 来源：[FR-PY] `main.py` 使用 `bleak.BleakScanner` + `bleak.BleakClient`。
- **广播识别**（来源 [FR-PY] `main.py`）：
  - Manufacturer ID：`1363`（十进制）= `0x0553`。
  - Manufacturer data 前缀：`01 00 03 7E`（`JOYCON_MANUFACTURER_PREFIX = bytes([0x01, 0x00, 0x03, 0x7E])`）。
  - 扫描回调里：`adv.manufacturer_data.get(1363)` 且 `data.startswith(b"\x01\x00\x03\x7E")` → 判定为 Switch 2 系列控制器。
- **稳定性 quirk**（来源 [FR-PY] README + [MIS]，两个独立项目一致）：
  > 短时间内反复连接/配对，控制器会「数分钟内完全拒绝连接」。这是**控制器级冷却**，非 OS/BLE 栈问题。
  → 见 §G，必须实现 reconnect backoff。
- macOS：CoreBluetooth 用每台主机固定的 UUID 而非 MAC 标识设备（两只手柄的 UUID 自 2026-09-06 至 10-24 未变）；广播名 `Joy-Con 2 (L)` / `Joy-Con 2 (R)`，**但首次发现时可能为空**（2026-09-06 左手柄即如此）。
- **左右判定** `[真机确认 2026-10-24]`：manufacturer data（bleak 去掉公司号后）第 5–6 字节 = Product ID（LE）：`0x2067` = 左，`0x2066` = 右（[ND] `bluetooth_interface.md` + `descriptors.md`）。两只实测 `…7e 05 67 20…` / `…7e 05 66 20…`，与广播名一致。连接后再用 GATT 表复核：只有左手柄有 `cc1bbbb5-…`，只有右手柄有 `d5a9e01e-…`（[ND]），实测与 PID 判定一致。实现：`bluetooth/scanner.py`、`connection.side_from_services`。

---

## C. 使用哪种协议？

**自定义 BLE GATT（proprietary GATT service + 自定义 characteristics），不是 HID-over-GATT，也不是 Bluetooth Classic HID。**

| 判据 | 证据 |
| --- | --- |
| 不是 Bluetooth Classic HID | 第一代 Joy-Con 是 Classic HID（`tomayac/joy-con-webhid` 靠 WebHID 工作）；Joy-Con 2 的社区代码全部用 **BLE GATT `bleak`**，且 WebHID 社区无 Joy-Con 2 成功案例。 |
| 不是标准 HID-over-GATT (HOGP) | 未使用标准 `0x1812` HID Service / `0x2A4D` Report characteristic；而是下面的私有 128-bit UUID。 |
| 是私有 GATT | 见 §C.1 的 128-bit vendor UUID。 |

> 结论直接决定架构：浏览器 **WebHID 不可用**；Web Bluetooth 连私有 GATT characteristic 需实验 flag 且受权限/黑名单限制、无社区先例 → 采用 **方案 B：Native BLE Adapter → WebSocket**。详见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

### C.1 BLE Services / Characteristic UUID

来源：[FR-PY] `main.py`

| 名称 | UUID | 属性 | 用途 |
| --- | --- | --- | --- |
| Input Report characteristic | `ab7de9be-89fe-49ad-828f-118f09df7fd2` | Notify | 订阅后持续收到输入报文（buttons/stick/IMU/…） |
| Write Command characteristic | `649d4ac9-8eb7-4e6c-af44-1ea54fe5f005` | Write | 下发命令（使能 IMU、设置 LED、震动预设） |

- 所属 Service UUID：**`ab7de9be-89fe-49ad-828f-118f09df7fd0`** `[真机确认 2026-09-06]`。上面两个 characteristic 都在这个私有 primary service 下。
  完整 GATT 树里另有一个配置 service `00c5af5d-1964-4e30-8f51-1956f96bd280`（read/write/read 三个 char），用途未定；以及多个 notify-only char（`cc1bbbb5-…` / `c765a961-…` / `63a3810f-…` / `d3bd69d2-…` 等），本项目只订阅 `…fd2`。
  左右两只的 char 列表略有差异（各自多出一两个 vendor char），但 `…fd2`(notify) / `649d4ac9`(write) 一致。
- 常量：`adapter/src/protocol/constants.py` 的 `INPUT_SERVICE_UUID`。
- `[未真机验证]` 是否还有电池 Service（标准 `0x180F`）可用。报文内已含 battery voltage/current 字段（§I），无需额外 characteristic。
- 命令应答 characteristic `c765a961-d9d8-4d36-a20a-5315b111836a`（Notify，[ND]/[J2W]）`[真机确认 2026-10-24]`：读 flash（§D.5）的应答从这里回来。

---

## D. 可读数据与规格

### D.1 可读内容
Buttons ✅、单摇杆（Left Joy-Con 用 Left Stick，Right Joy-Con 用 Right Stick）✅、Accelerometer (ax,ay,az) ✅、Gyroscope (gx,gy,gz) ✅、Magnetometer ✅、电池电压/电流 ✅、温度 ✅、模拟扳机 ✅、（右 Joy-Con）光学鼠标位移 ⚠️（字段已知，含义部分未定）。
来源：[FR-PY] README 布局表（`@german77`）、[FR-CPP]、[MIS]。

### D.2 Sampling Rate / Packet Rate
- [EIMU] 声称 **≈ 62 Hz** native。**`[真机 2026-09-06]` 本环境实测：33.5 Hz notification（IMU 使能后）/ 28 Hz（使能前）**，右 Joy-Con，macOS CoreBluetooth。
  - 几乎肯定是 **macOS BLE 连接间隔限制**（CoreBluetooth 常锁 ~30 ms），不是控制器上限；换 Linux/Windows 或 dongle 可能拿到更高。属平台 caveat，非解码 bug。
  - 每包**单组** accel + 单组 gyro（IMU 区就是 12 字节 `0x30–0x3B`），**无子采样**。Motion Engine 不假设子采样，且实测确认无需。
- **Packet ID `0x00`（uint32 LE）实测是毫秒时间戳**：240 s 抓取里从 2036 涨到 243656，≈ 1006 units/s。单调递增，可作相对时序 / 丢包间隙判断；绝对时间仍由 Adapter 接收时刻 `time.monotonic()` 补充。

### D.3 Latency
- `[未真机验证]`。设计目标（GOAL.md §9）：Motion latency < 50 ms。
- 预算拆解（估算）：BLE 连接间隔 ~15 ms + 解包 <1 ms + WebSocket 本机回环 <2 ms + 浏览器事件 <5 ms + 渲染半帧 ~8 ms ≈ **30–40 ms**，留余量。
- 真机验证方法：Adapter 打时间戳 `t_recv`，浏览器收到打 `t_ws`，页面渲染打 `t_draw`，统计 `t_draw - t_recv` 分位数（p50/p95）。工具见 [TESTING.md](./TESTING.md)。

### D.4 数据单位 / 范围 / Endianness

来源：[FR-PY] `solo_logic.py`（`decode_gyro` / `decode_accel`）+ README 布局表。

| 量 | 原始类型 | Endian | 换算 | 物理单位 | 满量程估算 |
| --- | --- | --- | --- | --- | --- |
| Accelerometer x/y/z | int16 signed | little | `raw / 4096` | g（重力加速度） | ±8 g（`32768/4096`） |
| Gyroscope x/y/z | int16 signed | little | `raw * 360 / 48000` = `raw / 133.333…` | °/s | ±2000 °/s 量级（`32768 * 360/48000 ≈ ±245`… 实际满量程取决于 FS 设定，见下） |
| Stick x/y | 12-bit unsigned packed | 见 §H | 出厂标定中心 + 分方向行程（§H.1） | 归一化 [-1,1] | 12-bit：0..4095；实际中心偏离 2048 最多 ~150，行程仅 ±1150–1300 |
| Battery voltage | uint16 | little | `raw`（mV），`1000 = 1V` | V | — |
| Battery current | int16 | little | `raw / 100`（mA），`100 = 1mA` | mA | — |
| Temperature | int16 | little | `25 + raw / 127` | °C | 例：raw 3679 → ~54°C |
| Magnetometer x/y/z | int16 | little | `[未真机验证]` 比例 | µT（待定） | — |

> **陀螺仪满量程注记**：换算系数 `48000 raw = 360°/s` 来自 [FR-PY]。据此 `1°/s = 133.333 raw`，int16 上限 `32767 raw ≈ 245.75 °/s`。
> `[真机 2026-09-06 部分]`：普通挥动/甩腕下峰值仅 ~82–95 °/s（raw ≤ 12711），**远未触及 int16 上限，无 wrap/饱和迹象**；静置三轴 < 2 °/s。
> **高速旋转（> 245 °/s）仍未测**，是否 wrap、是否多档 FS 待补。Motion Engine 侧保留 `unwrap`/夹紧保护。
>
> **字节序 `[真机 2026-09-06 确认]`**：accel 按 int16 **little-endian signed** 解，六个朝向重力模长均 ≈ 1.00 g（0.97–1.04）；big-endian 解得不到 1 g。§H「Field Example」的 big-endian 读法确为笔误。

### D.5 Calibration 方法
- **社区参考实现未做出厂标定块解析**（[FR-PY] 直接用线性系数），因此本项目采用**用户静置标定**（GOAL.md §15 步骤 5「将 Joy-Con 放平保持 2 秒」）：
  1. 采集静置 ~2 s（≈124 包）accel/gyro。
  2. **陀螺仪零偏** `gyro_bias = mean(gyro_raw)`，之后每包减去。
  3. **加速度计**：静置时 `|accel|` 应 ≈ 1 g；求得每轴 offset 使重力矢量模长归一，记录重力方向作为初始 orientation 参考。
  4. 死区：标定后 `|gyro| < deadzone` 视为 0（抗漂移）。
- **摇杆出厂标定 `[真机确认 2026-10-24]`**：用 [ND] 的读 flash 命令 `02 91 01 04 00 08 00 00 | len 7E 00 00 | addr(u32 LE)`（写到 `649d4ac9-…`，应答在 `c765a961-…`，数据从应答第 16 字节起）读 `0x130A8` 的 9 字节（[ND] 只给出地址 “Primary analog stick calibration”）。两只手柄均读成功，格式由本项目真机数据确定为三组 12-bit (x,y)：**中心、+x/+y 行程、−x/−y 行程**：
  | 手柄 | 原始 9 字节 | 中心 | +行程 | −行程 | 同次实测静置中位数 | 实测满推行程 |
  | --- | --- | --- | --- | --- | --- | --- |
  | 左 | `73 77 86 ee e4 47 88 04 4e` | (1907, 2151) | (1262, 1150) | (1160, 1248) | (1895, 2161) | +x 1276 +y 1154 −x 1167 −y 1295 |
  | 右 | `4c 88 7c b3 a4 4d c3 54 48` | (2124, 1992) | (1203, 1242) | (1219, 1157) | (2109, 1987) | +x 1174 +y 1290 −x 1242 −y 1154 |
  中心与实测静置点相差 ≤15，行程与实测逐方向相差约 ±5%（实测略大处由自学习扩展覆盖）。用户标定区 `0x1FC040` 两只均为全 `FF`（未做过用户标定）。实现：`connection._read_stick_calibration` + `calibration/stick.py`。
- IMU 出厂标定仍未找（[ND] 列出 `0x1FC000` 用户 motion 标定，本机未读），IMU 继续用静置标定。
- 实现：`adapter/src/calibration/calibrator.py`（IMU）、`adapter/src/calibration/stick.py`（摇杆）。

---

## E. Left 与 Right 的 packet layout 是否不同？

**按键位布局不同；IMU / 电池 / 温度字段偏移相同。**
来源：[FR-PY] README（"Bit layouts differ slightly between left and right Joy-Cons"）+ `solo_logic.py`。

- 按键状态读取（[FR-PY] `solo_logic.handle_single_notification`）：
  - Left：`state = int.from_bytes(data[4:7], 'big')`（offset 4，3 字节，big-endian）
  - Right：`state = int.from_bytes(data[3:6], 'big')`（offset 3，3 字节，big-endian）
  - 对应 [ND] 的 4 字节按键域 `0x04–0x07`：`0x04` = 右手键，`0x05` = 共用（−/+/摇杆按下/Home/Capture/C），`0x06` = 左手键，`0x07` 实测两只恒为 `0xE0`（[ND] 记为 Pro 手柄 GL/GR/耳机位，Joy-Con 不用）。右 slice 的高字节 `data[3]` 是计数器字节，掩码不用它（测试覆盖）。
- 摇杆：
  - Left Joy-Con 读 `data[10:13]`（`0x0A`），Right Joy-Con 读 `data[13:16]`（`0x0D`），与 [ND] 一致。另一侧槽位恒为占位 `ff f7 7f`（= 2047/2047）。
  - 方向 `[真机确认 2026-10-24]`：原始 x 向右增大、y 向上增大（推上 → y 原始 ~3300），即 +x 右、+y 上，左右两只相同。
  - ~~右摇杆中心 ≈2047/2047~~（2026-09-06 记录有误，那是空槽占位值）：右实际静置 ≈(2109, 1987)，左 ≈(1895, 2161)。
  - 旧版 `±0.5–0.6 未贴满` 的原因已查明：行程只有 ±1150–1300 计数却除以 2048（不是推杆力度问题）；改用出厂标定后两只四向峰值 0.98–1.00、八扇区全部 ≥0.99，见 §H.1。
- 按键位定义（`state` 为 big-endian 3 字节整数后的掩码；括号内为 [ND] 字节/位）：

| 边 | 键 | mask | [ND] 位置 | 状态 |
| --- | --- | --- | --- | --- |
| RIGHT | A | `0x000800` | `0x04` bit 3 | **`[真机确认 2026-10-24]`**（订正：原 [FR-PY] 表为 `0x000400`） |
| RIGHT | B | `0x000400` | `0x04` bit 2 | **`[真机确认 2026-10-24]`**（原 `0x000800`） |
| RIGHT | X | `0x000200` | `0x04` bit 1 | **`[真机确认 2026-10-24]`**（原 `0x000100`） |
| RIGHT | Y | `0x000100` | `0x04` bit 0 | **`[真机确认 2026-10-24]`**（原 `0x000200`） |
| RIGHT | SR | `0x001000` | `0x04` bit 4 | **`[真机确认 2026-10-24]`**（原 `0x002000`） |
| RIGHT | SL | `0x002000` | `0x04` bit 5 | **`[真机确认 2026-10-24]`**（原 `0x001000`） |
| RIGHT | R | `0x004000` | `0x04` bit 6 | `[真机确认 2026-09-06 / 10-24]` |
| RIGHT | ZR | `0x008000` | `0x04` bit 7 | `[真机确认 2026-09-06 / 10-24]` |
| RIGHT | + (Plus) | `0x000002` | `0x05` bit 1 | `[真机确认 2026-10-24]` |
| RIGHT | Stick press | `0x000004` | `0x05` bit 2 | `[真机确认 2026-09-06 / 10-24]` |
| RIGHT | **Home** | **`0x000010`** | `0x05` bit 4 | **新增** `[真机确认 2026-10-24]` |
| RIGHT | **C** | **`0x000040`** | `0x05` bit 6 | `[真机确认 2026-09-06 / 10-24]` |
| LEFT | D-Up | `0x000002` | `0x06` bit 1 | `[真机确认 2026-09-28 / 10-24]` |
| LEFT | D-Down | `0x000001` | `0x06` bit 0 | 同上 |
| LEFT | D-Left | `0x000008` | `0x06` bit 3 | 同上 |
| LEFT | D-Right | `0x000004` | `0x06` bit 2 | 同上 |
| LEFT | L | `0x000040` | `0x06` bit 6 | 同上 |
| LEFT | ZL | `0x000080` | `0x06` bit 7 | 同上 |
| LEFT | SL | `0x000020` | `0x06` bit 5 | 同上 |
| LEFT | SR | `0x000010` | `0x06` bit 4 | 同上 |
| LEFT | − (Minus) | `0x000100` | `0x05` bit 0 | 同上 |
| LEFT | Stick press | `0x000800` | `0x05` bit 3 | 同上 |
| LEFT | **Capture** | **`0x002000`** | `0x05` bit 5 | **新增** `[真机确认 2026-10-24]` |
| — | **Sync** | — | 无 | **不上报** `[真机确认 2026-10-24]` |

> **右手 ABXY/SL/SR 订正的来龙去脉**：本项目最初照 [FR-PY] `solo_logic.MASKS` 写的右手表把 A↔B、X↔Y、SL↔SR 两两对调；2026-09-06 第 1 轮记为“逐个确认”，实际只确认了“每键点亮唯一一位”，没有核对标签。[ND] 与 [J2W] 给出相反映射（[FR-CPP] 又与两者都不同：B/X 对调）。2026-10-24 真机：用户按 A/B/X/Y 时页面亮错名字；改用 [ND] 映射后用户逐键确认“按 A 亮 a … 按 SL 亮 sl”全部一致。真机抓包固化为回归测试 `adapter/tests/test_hw_capture.py`（用旧表解同一份抓包会得到 `b, a, y, x, …, sr, sl`）。
> **Home / Capture**：[ND]、[J2W]、[FR-CPP] 三处一致（`0x05` bit 4 / bit 5）；2026-10-24 真机各点亮唯一一位且名字一致。
> **Sync**：[ND] 的完整按键域里没有 Sync 位；2026-10-24 整场抓包（含多次按 Sync）中按键域内没有任何未映射位翻转。Sync 只用于配对：**连接中短按 → 手柄主动断开**（最后一包到断开回调约 0.7 s）；**长按到指示灯跑马 → 进入配对广播**，adapter 自动重连（见 §G）。
> **组合与长按**：多键同时按下各自独立置位（A+B+R 同按 7 s、R+SR、R+stick 实测），长按期间每包持续置位（A 连续 18 s、R 3.4 s），松开其中一键不影响其它键。

---

## F. 是否已有公开代码能启用 IMU？

**有。** 来源：[FR-PY] `main.py` `enable_imu()`。

向 Write Command characteristic (`649d4ac9-…`) **连续写两条 12 字节命令**，间隔 ~0.5 s：

```
ENABLE_IMU_1 = 0c 91 01 02 00 04 00 00 2f 00 00 00
ENABLE_IMU_2 = 0c 91 01 04 00 04 00 00 2f 00 00 00
```

命令结构推断（对照 [FR-PY] `write_command()` 通用格式
`cmd_id | 0x91 0x01 | subcmd_id | 0x00 | len | 0x00 0x00 | payload`）：
- `0x0C` = command id（IMU/config 域）
- `0x91 0x01` = 固定包头
- `0x02` / `0x04` = subcommand（两条分别配置两个寄存器/两个轴组）
- `0x04 0x00` = payload 长度 4
- `0x2F 0x00 0x00 0x00` = payload（`0x2F` 为使能位掩码，`[未真机验证]` 具体位含义）

相关命令（来源 [FR-PY]）：
- 设置 Player LED：`write_command(client, 0x09, 0x07, <pattern byte>)`，pattern：P1=`0x01` P2=`0x03` P3=`0x07` P4=`0x0F` …
- 震动预设：`write_command(client, 0x0A, 0x02, <preset id>)`（GOAL.md 非目标，仅记录）。

> `[真机 2026-09-06 确认]`：**不需要**「standard full mode」前置命令。只写 `ENABLE_IMU_1` + `ENABLE_IMU_2`（间隔 0.5 s），~1 s 后 `0x30–0x3B` 即开始输出随姿态变化的 IMU 值。也不需要系统级 bond/pair——`bleak` 直接扫描 + `connect()` 即可（macOS CoreBluetooth）。

---

## G. 断开后的重连机制 / reconnect backoff

- 观测（[FR-PY] README + [MIS]，两独立来源）：**短时间反复连接 → 控制器数分钟内拒绝连接**（控制器级冷却）。
- [FR-PY] 参考实现的重连（`maintain_connection_loop`）过于简单（固定 `sleep(5)`），本项目**强化**为指数退避 + 抖动：

```
初次断开: 等待 1s 重连
失败: 2s -> 4s -> 8s -> 16s -> 32s -> 60s(上限)
每次加 ±20% 随机抖动
连续失败 >= 4 次: 判定进入控制器冷却, 提示用户"等待 2-3 分钟", 退避固定在 60s
成功连接后: 退避计数清零
```

- 实现：`adapter/src/bluetooth/reconnect.py`（`ReconnectPolicy`）。
- 断开检测：`BleakClient` 的 disconnected callback + `is_connected` 轮询（1s）。
- 重连后**必须重发** IMU 使能命令与 LED（[FR-PY] `handler_func` 在重连分支里会重新 `start_notify`）。本项目 `JoyConConnection._initialise` 每次（重）连都重做：GATT 侧别复核 → LED → feature mask `0x2F`（按键+摇杆+IMU+…）→ 订阅输入；重连后保留该手柄的 IMU 标定与摇杆标定，按键/摇杆立即可用。
- **真机行为 `[真机确认 2026-10-24]`**：手柄断开后（如连接中短按 Sync）**不会自己再向本机广播**——adapter 按地址持续重试约 2 分钟都扫不到；**长按 Sync 到指示灯跑马**后约 1 s 内自动重连（17:52:31 出现广播 → 17:52:32 connected），无需重启 adapter。扫不到设备（`BleakDeviceNotFoundError`）不计入冷却退避，每次间隔 1 s 继续找；状态里的 `hint` 会提示“长按 Sync 直到灯跑马”。
- 断连到状态上报：最后一包输入到 `disconnected` 约 0.7 s（BLE 监督超时）；客户端另有 1 s 无帧即视为 stale 的兜底（`shared/protocol/input-client.mjs`）。

---

## H. Packet Structure（完整偏移表）

来源：[FR-PY] README 布局表（原始作者 `@german77`）+ `[真机 2026-09-06 右 Joy-Con]` 订正。IMU 已使能，**实测报文总长 = 63 字节（`0x3F`）**，非社区所说 62。

| Offset | Size | 字段 | 说明 / 换算 |
| --- | --- | --- | --- |
| `0x00` | 4 | Packet ID | uint32 LE —— **`[真机]` 实为毫秒时间戳**（~1006/s，单调） |
| `0x04` | 1 | Buttons（右手） | Y/X/B/A/SR/SL/R/ZR = bit 0..7 `[真机确认 2026-10-24]`（§E） |
| `0x05` | 1 | Buttons（共用） | −/+/右摇杆按下/左摇杆按下/Home/Capture/C = bit 0..6 `[真机确认 2026-10-24]` |
| `0x06` | 1 | Buttons（左手） | ↓/↑/→/←/SR/SL/L/ZL = bit 0..7 `[真机确认]` |
| `0x07` | 1 | Buttons（Pro 专用） | Joy-Con 实测恒 `0xE0` |
| `0x08` | 3 | Left Stick | 12-bit packed；解码取 `data[10:13]`。`[真机(右)]` 此槽位恒为占位 `ff f7 7f` |
| `0x0B`.. | 3 | Right Stick | 解码取 **`data[13:16]`（0x0D–0x0F）** `[真机(右)确认]` 中心 ≈2047 |
| `0x0E` | 2 | Mouse X | 右 Joy-Con 光学传感器，含义部分未定；`[真机]` 抓取中恒 0 |
| `0x10` | 2 | Mouse Y | 同上；恒 0 |
| `0x12` | 2 | Mouse Unk | 恒 0 |
| `0x14` | 2 | Mouse Distance | 恒 0 |
| `0x16` | 2 | Magnetometer X | int16 LE；`[真机]` 恒 0（未使能？）UNVERIFIED |
| `0x18` | 2 | Magnetometer Y | 同上 |
| `0x1A` | 2 | Magnetometer Z | 同上 |
| `0x1F` | 2 | Battery Voltage | uint16 LE，mV。**`[真机]` 在 `0x1F` 读到 ~3690 mV**；社区表的 `0x1C` 读 0。constants 已改 `OFF_BATTERY_VOLTAGE=0x1F` |
| `0x1E` | 2 | Battery Current | int16 LE，`100 = 1mA`；`[真机]` idle 读 0，UNVERIFIED |
| `0x21` | ~13 | Reserved | 多数恒 0；`0x22` 偶有非零（用途未定） |
| `0x2E` | 2 | Temperature | int16 LE，`25 + raw/127` °C —— **`[真机]` 读到负值 garbage，比例/位置存疑，UNVERIFIED** |
| `0x30` | 2 | Accel X | int16 LE，`raw / 4096` g —— **`[真机确认]`** |
| `0x32` | 2 | Accel Y | 同上 |
| `0x34` | 2 | Accel Z | 同上 |
| `0x36` | 2 | Gyro X | int16 LE，`raw * 360/48000` °/s |
| `0x38` | 2 | Gyro Y | 同上 |
| `0x3A` | 2 | Gyro Z | 同上 |
| `0x3C` | 1 | Analog Trigger L | 0..255；`[真机(右)]` 恒 0（ZR 在此模式为数字量），UNVERIFIED |
| `0x3D` | 1 | Analog Trigger R | 同上，UNVERIFIED |
| `0x3E` | 1 | ？ | 63 字节报文的末字节；`[真机]` 恒 0 |

> 实例（[FR-PY] README，Left Joy-Con 静置）：
> `08 67 00 00 | 00 00 00 00 | e0 ff 0f | ...`
> Packet ID `0x00006708`=26376；Buttons 全 0；Left Stick `e0 ff 0f` → X=`0x0FF0`=4080, Y=`0x0FE0`=4064（≈中心 + 少量偏置）。
> Accel `00 79 / 07 00 / 00 00` → axX=`0x7900`(LE)=`0x0079`? 见下注。

> **⚠️ Endianness 校验点**：README「Field Example」把 Accel X `00 79` 解释为 `0x7900 = 30976`（big-endian 读法），但 `solo_logic.decode_accel` 用 `byteorder='little'`。两处不自洽。
>
> **一致性检查结论（非真机，但可信度高）**：用本项目 `decoder/packet.py` 按 **int16 little-endian signed** 解码 README 给出的完整样例包
> `08 67 00 00 | 00 00 | 00 00 | e0 ff 0f | ... | 5f 0e | 00 79 07 00 00 00 | 00 00 01 ce 7b 52 | ...`
> 得到 **accel ≈ (-0.016, +0.107, +0.996) g，模长 ≈ 1.002 g**；gyro ≈ (0, 0, 0) °/s；stick ≈ 中心；temp ≈ 25 °C。
> 静置时重力矢量模长 ≈ 1 g、陀螺 ≈ 0 —— 与物理预期完全吻合。
> → **采用 int16 little-endian signed**（`decode_accel`/`decode_gyro` 实现如此）。README「Field Example」列的 big-endian 读法为笔误。
> 真机静置仍需按 J5/J7 复核，但字节序问题视为已解决。

### H.1 Stick 12-bit 解包与归一化

解包（来源 [FR-PY] `decode_joystick`，[ND] 同）：

```python
x = ((b1 & 0x0F) << 8) | b0
y = (b2 << 4) | ((b1 & 0xF0) >> 4)
```

归一化（本项目，`adapter/src/calibration/stick.py`，每只手柄一份状态）：
1. **中心**：手柄出厂标定（§D.5）；读不到时退回“连上后第一次静止在 2048±300 内的均值”，再之前用 2048。
2. **行程**：四个方向各一个；初值取出厂标定（读不到时 1100），只会随实际推到的最大值增长（上限 1900）。
3. 每轴 `(raw - 中心) / 该方向行程`，再**限制在单位圆内**（对角线 ≈ (0.71, 0.71)），再做**径向死区 0.08** 并从死区边缘重新拉伸到 0..1。
4. 坐标：+x 右、+y 上。原始值另以 `stickRaw` 下发，供诊断或自定义标定。

为什么不是社区做法：[FR-PY]/[FR-CPP] 用 `(raw-2048)/2048` 再乘 **1.7 增益**（就是在补 ±0.6 的行程不足），[JC2M] 只做自动找中心仍除以 2048（同样到不了 1.0），[J2W] 写死 780..3260 的边界；三者都不按单只手柄标定，增益系数也不照搬。

真机结果 `[2026-10-24]`（同一场、出厂标定）：静置时预死区偏移最大 0.038（死区 0.08，余量 2 倍），输出精确为 0；四向峰值 左 0.998–1.000 / 右 0.978–1.000；八个扇区（含对角线）全部 ≥0.99；两摇杆同时满推 2.4 s 互不影响；按下摇杆与推杆同时进行正常。

---

## I. 归一化输出（Adapter → 下游）

Adapter 解包 + 标定后，产出 GOAL.md §8.1 契约（见 [shared/protocol/](../shared/protocol/README.md)）：

```json
{
  "timestamp": 0.0,
  "seq": 26376,
  "controller": "left",
  "buttons": { "a": false, "... ": false },
  "stick": { "x": 0.0, "y": 0.0 },
  "accelerometer": { "x": 0.0, "y": 0.0, "z": 1.0 },
  "gyroscope": { "x": 0.0, "y": 0.0, "z": 0.0 },
  "battery": { "voltage": 3.9, "current": 0.0 },
  "temperature": 30.0
}
```

- `timestamp`：Adapter 侧 `time.monotonic()`（秒，float），接收该 BLE notification 的时刻。**不做降采样**（GOAL.md §9）。
- `accelerometer`：单位 g，标定后（去 offset）。
- `gyroscope`：单位 **rad/s**（Adapter 把 °/s 转成 rad/s 再输出，便于 Motion Engine 积分）；已减零偏。
- `controller`：`"left"` | `"right"`。

---

## J. 真机验证清单（有 Joy-Con 2 时执行）

状态：`[✅]` 通过 / `[🟡]` 部分 / `[ ]` 待办。首轮 2026-09-06，右 Joy-Con，macOS CoreBluetooth。

| # | 验证项 | 状态 | 结果 |
| --- | --- | --- | --- |
| J1 | Sync 进入广播 | ✅ | 两只都扫到：manuf 1363 + 前缀 `01 00 03 7e`；右广播名 `Joy-Con 2 (R)` |
| J2 | 连接 | ✅ | `is_connected=True`；Service UUID = `ab7de9be-…-fd0`（补进 §C.1） |
| J3 | 收原始 notification | ✅ | 未使能 IMU 也有报文（63 B，28 Hz），`0x30+` 全 0 |
| J4 | IMU 使能 | ✅ | 发 `ENABLE_IMU_1/2` 后 `0x30+` 出现活值；报文仍 63 B（长度不变，IMU 区从 0 变活） |
| J5 | Accel 静置 | ✅ | 六朝向各测到重力单轴 ≈ 1.00 g（0.97–1.04），其余 ≈ 0 |
| J6 | Gyro 静置 / 转动 | 🟡 | 静置三轴 < 2 dps；转动对应轴响应、方向自洽。积分幅度偏小（动作不标准），未做精确标定 |
| J7 | 字节序 | ✅ | int16 **little-endian signed** 确认（LE 才得 1 g） |
| J8 | 采样率 | 🟡 | 实测 **33.5 Hz**（macOS BLE 连接间隔限制？）≠ [EIMU] 的 62 Hz。`0x00` 是毫秒时间戳 |
| J9 | Left vs Right | ✅ | 右：按键 8 位 + C + stick + 摇杆槽全确认。左（2026-09-28）：十键掩码 + 摇杆槽 `data[10:13]` + accel/gyro 偏移全确认，与 [FR-PY] 假设一致，**无需改动常量** |
| J10 | 重连冷却 | 🟡 | 已观察到：快速重连触发数分钟拒连（连过一次后再连 `TimeoutError`）。未跑满 5 次 backoff 序列 |
| J11 | 延迟 | ⬜ | 待做（Step G） |
| J12 | C 按钮 / 出厂标定块 | ✅ | C 键 `0x000040` 确认；**摇杆出厂标定 `0x130A8` 两只均读到并用于归一化**（§D.5）。IMU 出厂标定未找（继续静置标定） |
| J13 | 全部按键（左 11 + 右 12）+ Sync | ✅ | 2026-10-24 逐键真机：右 A/B/X/Y/SL/SR 订正，Home/Capture 新增，Sync 不上报（§E） |
| J14 | 摇杆中心 / 满行程 / 对角 / 方向 | ✅ | 出厂标定 + 分方向行程：静置 0，四向沿轴峰值 0.978–1.000，八扇区（含对角）r ≥0.99，+x 右 +y 上（§H.1） |
| J15 | 左右同时连接与输入 | ✅ | 一个 adapter 同时连左右，各 ~33 Hz；按键/摇杆/组合互不串扰（§E、[HARDWARE_BRINGUP](./HARDWARE_BRINGUP.md) §5 第 5 轮） |
| J16 | 断连清键 / 重连 | ✅ | 按住 A 时短按 Sync 断开 → `disconnected` 约 0.7 s 后到达，客户端释放 A；长按 Sync 到跑马灯 → ~1 s 自动重连，按键立即可用（§G） |

---

## K. 未决问题

已解决（2026-09-06 真机）：
- ~~Service UUID~~ = `ab7de9be-…-fd0`（§C.1）。
- ~~字节序~~ = int16 LE signed（§D.4 / §H）。
- ~~`C` 按钮掩码~~ = `0x000040`（§E）。
- ~~Stick 偏移~~：右 = `data[13:16]`，左槽位占位 `ff f7 7f`（§E）；代码取值正确。
- ~~每包 IMU 子采样~~：无，单组（§D.2）。
- ~~是否需要 standard full mode 前置命令~~：不需要，只发 `ENABLE_IMU_1/2` 即出 IMU（§F）。
- ~~左 Joy-Con 按键掩码 / 摇杆偏移~~（2026-09-28 真机）：十键掩码 + `data[10:13]` 摇杆槽 + accel/gyro 偏移全部与 [FR-PY] 假设一致（§E、J9）。
- ~~右手 ABXY/SL/SR、Home、Capture、Sync~~（2026-10-24 真机，§E）。
- ~~摇杆幅度只有 ±0.6~~：归一化除错了数（行程 ±1150–1300），改用出厂标定（§D.5、§H.1）。
- ~~出厂标定块位置~~：摇杆在 `0x130A8`，格式见 §D.5；IMU 部分仍未知。
- ~~左右判定~~：广播 Product ID + GATT 复核（§B）。

仍待真机：
1. 陀螺高速旋转（>245 dps）是否 wrap / 多档 FS（§D.4）。
2. Magnetometer：抓取中恒 0，是否需单独使能 + 单位/比例（§D.4）。
3. Temperature：`0x2E` 读负值 garbage，实际字段位置 / 比例（§H）。
4. Battery current、analog trigger 字段确认（idle 全 0）。
5. IMU 出厂/用户标定（[ND] `0x1FC000`）是否可用——IMU 暂继续用静置标定。
7. 延迟分位数 p50/p95（J11）。
8. 采样率是否平台相关：换 Linux/Windows/dongle 是否 > 33.5 Hz（§D.2）。
9. 重连 backoff 完整序列复核（J10）。
