# docs/JOYCON2_PROTOCOL.md — Joy-Con 2 协议摘要

> 对应 GOAL.md **Phase 1**。
> **状态：核心链路已在真机验证（2026-09-06，右 Joy-Con 2，macOS CoreBluetooth）。** 详见 [HARDWARE_BRINGUP.md](./HARDWARE_BRINGUP.md) §「实测记录」。
> 本文件汇总社区逆向成果并逐条标注来源；`[未真机验证]` 表示尚未复核，`[真机确认 2026-09-06]` 表示已用 `adapter/src/bluetooth/prototype.py` + 脚本化动作抓取核对。
> 仍待办：左 Joy-Con 单独复核（J9）、延迟分位数（J11）、高速旋转陀螺满量程（D.4）、温度/磁力计字段。
>
> 来源代号：
> - **[FR-PY]** = `TheFrano/joycon2py`（README 布局表 + `main.py` + `solo_logic.py`），布局原始提供者 `@german77`。
> - **[FR-CPP]** = `TheFrano/joycon2cpp` README 协议段。
> - **[MIS]** = `Misaka10571/joycon2-connector` README。
> - **[EIMU]** = `matiaspalmac/everything-imu`（采样率 / 硬件验证声明）。
> - **[DKMS]** = `XenuIsWatching/hid-nintendo2-dkms`（USB VID/PID）。

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
- macOS 特别说明 `[未真机验证]`：CoreBluetooth 用随机 UUID 而非 MAC 标识设备；`bleak` 已封装。设备名可能显示为 `Joy-Con (L)` / `Joy-Con (R)` 或厂商自定义名。

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
| Stick x/y | 12-bit unsigned packed | 见 §H | `(raw - 2048) / 2048` | 归一化 [-1,1] | 12-bit：0..4095，中心 2048 |
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
- `[未真机验证]` Joy-Con 2 是否在某 characteristic 暴露 SPI/出厂标定数据（第一代在 SPI flash `0x6020` / `0x6080`）。若真机发现，可替换为出厂标定，静置标定作兜底。
- 实现：`adapter/src/calibration/calibrator.py`。

---

## E. Left 与 Right 的 packet layout 是否不同？

**按键位布局不同；IMU / 电池 / 温度字段偏移相同。**
来源：[FR-PY] README（"Bit layouts differ slightly between left and right Joy-Cons"）+ `solo_logic.py`。

- 按键状态读取（[FR-PY] `solo_logic.handle_single_notification`）：
  - Left：`state = int.from_bytes(data[4:7], 'big')`（offset 4，3 字节，big-endian）
  - Right：`state = int.from_bytes(data[3:6], 'big')`（offset 3，3 字节，big-endian）
  - ⚠️ 注意与 README 布局表「Buttons 在 `0x04`，4 字节」有出入 —— README 给 4 字节窗口，解码实现取 3 字节且左右起点差 1。**以 `solo_logic.py` 实测实现为准**，真机上再校。
- 摇杆（[FR-PY] `solo_logic.py`）：
  - Left Joy-Con 读 `data[10:13]`（≈ `0x0A`），Right Joy-Con 读 `data[13:16]`（≈ `0x0D`）。
  - `[真机 2026-09-06 确认（右）]`：右摇杆在 **`data[13:16]`（0x0D–0x0F）**，12-bit 解包（§H.1）中心 ≈ 2047/2047，推杆时 x/y 摆到 ~900..3300。
    左摇杆槽位 `data[10:13]` 在右 Joy-Con 上是恒定占位 `ff f7 7f`（解出正好 2047/2047）。
    → **实现取的 `0x0A` / `0x0D` 正确**，README 布局表的 `0x08` / `0x0B` 是错的。左 Joy-Con 的 `data[10:13]` 待 J9 复核（Step B 里已见 `8a b7 84` → ~1930/2123，接近中心，初步 OK）。
- 按键位定义（[FR-PY] `solo_logic.MASKS`，`state` 为 big-endian 3 字节整数后的掩码）：

| 边 | 键 | mask |
| --- | --- | --- |
| RIGHT | A | `0x000400` |
| RIGHT | B | `0x000800` |
| RIGHT | X | `0x000100` |
| RIGHT | Y | `0x000200` |
| RIGHT | + (Plus) | `0x000002` |
| RIGHT | R | `0x004000` |
| RIGHT | ZR | `0x008000` |
| RIGHT | Stick press | `0x000004` |
| RIGHT | SL | `0x001000` |
| RIGHT | SR | `0x002000` |
| RIGHT | **C** | **`0x000040`** `[真机 2026-09-06]` —— 字节 `0x05` bit 6，"按 C 三下"精确对上三次 |
| LEFT | D-Up | `0x000002` |
| LEFT | D-Down | `0x000001` |
| LEFT | D-Left | `0x000008` |
| LEFT | D-Right | `0x000004` |
| LEFT | − (Minus) | `0x000100` |
| LEFT | L | `0x000040` |
| LEFT | ZL | `0x000080` |
| LEFT | Stick press | `0x000800` |
| LEFT | SL | `0x000020` |
| LEFT | SR | `0x000010` |

> `C` 按钮（Joy-Con 2 新增，位于右 Joy-Con）：**`[真机 2026-09-06 确认]` mask `0x000040`**（3 字节 big-endian state 里 = 字节 `0x05` 的 bit 6）。已写入 `adapter/src/decoder/buttons.py` 的 `BUTTON_MASKS_RIGHT["c"]`。
> 右侧 A/B/X/Y/R/ZR/SL/SR 掩码逐个按键实测，与 [FR-PY] 表**完全一致**；`stick`(按下) = `0x000004` 也确认。`plus` / `home` 未单独分辨（只抓到一次 `0x05` bit 4，可能是其一）。

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
- 重连后**必须重发** IMU 使能命令与 LED（[FR-PY] `handler_func` 在重连分支里会重新 `start_notify`）。

---

## H. Packet Structure（完整偏移表）

来源：[FR-PY] README 布局表（原始作者 `@german77`）+ `[真机 2026-09-06 右 Joy-Con]` 订正。IMU 已使能，**实测报文总长 = 63 字节（`0x3F`）**，非社区所说 62。

| Offset | Size | 字段 | 说明 / 换算 |
| --- | --- | --- | --- |
| `0x00` | 4 | Packet ID | uint32 LE —— **`[真机]` 实为毫秒时间戳**（~1006/s，单调） |
| `0x04` | 2 | Buttons hi | `[真机(右)]` A/B/X/Y/SL/SR/R/ZR 全在 `0x04`；`0x05` = plus/home/stick/**C** |
| `0x06` | 2 | Buttons lo / pad | `[真机]` 抓取中恒 0（3 字节 big-endian state，左 `data[4:7]` / 右 `data[3:6]`，见 §E） |
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

### H.1 Stick 12-bit 解包（来源 [FR-PY] `decode_joystick`）

```python
x = ((b1 & 0x0F) << 8) | b0
y = (b2 << 4) | ((b1 & 0xF0) >> 4)
x_norm = (x - 2048) / 2048.0     # -> [-1, 1)
y_norm = (y - 2048) / 2048.0
# deadzone 0.08; 参考实现再乘 1.7 增益并夹到 [-1,1]（游戏手感，非协议）
```

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
| J9 | Left vs Right | 🟡 | 右：按键 8 位 + C + stick + 摇杆槽全确认。**左：待单独抓一轮** |
| J10 | 重连冷却 | 🟡 | 已观察到：快速重连触发数分钟拒连（连过一次后再连 `TimeoutError`）。未跑满 5 次 backoff 序列 |
| J11 | 延迟 | ⬜ | 待做（Step G） |
| J12 | C 按钮 / 出厂标定块 | 🟡 | **C 键 mask `0x000040` 确认**（§E 已补）。出厂标定块未找（继续用静置标定） |

---

## K. 未决问题

已解决（2026-09-06 真机）：
- ~~Service UUID~~ = `ab7de9be-…-fd0`（§C.1）。
- ~~字节序~~ = int16 LE signed（§D.4 / §H）。
- ~~`C` 按钮掩码~~ = `0x000040`（§E）。
- ~~Stick 偏移~~：右 = `data[13:16]`，左槽位占位 `ff f7 7f`（§E）；代码取值正确。
- ~~每包 IMU 子采样~~：无，单组（§D.2）。
- ~~是否需要 standard full mode 前置命令~~：不需要，只发 `ENABLE_IMU_1/2` 即出 IMU（§F）。

仍待真机：
1. 左 Joy-Con 按键掩码 / 摇杆偏移单独复核（J9）。
2. 陀螺高速旋转（>245 dps）是否 wrap / 多档 FS（§D.4）。
3. Magnetometer：抓取中恒 0，是否需单独使能 + 单位/比例（§D.4）。
4. Temperature：`0x2E` 读负值 garbage，实际字段位置 / 比例（§H）。
5. Battery current、analog trigger 字段确认（idle 全 0）。
6. 出厂标定块位置（§D.5）——暂continue 用静置标定。
7. 延迟分位数 p50/p95（J11）。
8. 采样率是否平台相关：换 Linux/Windows/dongle 是否 > 33.5 Hz（§D.2）。
9. 重连 backoff 完整序列复核（J10）。
