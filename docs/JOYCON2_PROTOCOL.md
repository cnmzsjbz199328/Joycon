# docs/JOYCON2_PROTOCOL.md — Joy-Con 2 协议摘要

> 对应 GOAL.md **Phase 1**。
> **状态：`EXPERIMENTAL / 未在本环境真机验证`。** 本文件汇总社区逆向成果，并逐条标注来源。
> 凡标 `[未真机验证]` 的条目，需在有 Joy-Con 2 实机时用 `adapter/src/bluetooth/prototype.py` 复核。
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
- `[未真机验证]` 是否需要先在系统层完成一次 bond，还是可直接由 `bleak`/BlueZ/WinRT 扫描到并 `connect()`。[FR-PY] 的实现是**直接扫描 + connect，不经系统配对 UI**。

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

- 所属 Service UUID：`[未真机验证]`。[FR-PY] 直接按 characteristic UUID 读写，未显式记录 service UUID（`bleak` 允许按 char UUID 直接定位）。真机验证时用 `client.services` dump 完整 GATT 树补全本表。
- `[未真机验证]` 是否还有电池 Service（标准 `0x180F`）可用。报文内已含 battery voltage/current 字段（§I），无需额外 characteristic。

---

## D. 可读数据与规格

### D.1 可读内容
Buttons ✅、单摇杆（Left Joy-Con 用 Left Stick，Right Joy-Con 用 Right Stick）✅、Accelerometer (ax,ay,az) ✅、Gyroscope (gx,gy,gz) ✅、Magnetometer ✅、电池电压/电流 ✅、温度 ✅、模拟扳机 ✅、（右 Joy-Con）光学鼠标位移 ⚠️（字段已知，含义部分未定）。
来源：[FR-PY] README 布局表（`@german77`）、[FR-CPP]、[MIS]。

### D.2 Sampling Rate / Packet Rate
- **≈ 62 Hz**（IMU 使能后，每包 1 组 accel + 1 组 gyro 采样）。来源：**[EIMU]** —— "native 62 Hz BLE connectivity"，且该项目声明 Joy-Con 2 *hardware-validated*。
- 对照 [FR-PY]：`hidinput`/notification 与第一代一样「约 60 fps」量级。
- `[未真机验证]` 每包是否携带多组 IMU 子采样（第一代第 3 组 = 每包 3 组 @ ~200 Hdownsample 到包率）。Joy-Con 2 布局表中 IMU 区只有**单组** accel/gyro（`0x30–0x3B`），因此**按 62 Hz 单采样处理**，Motion Engine 不假设子采样。
- Packet ID 位于 `0x00`（4 字节，小端），"Sequence or timestamp"（[FR-PY]/[MIS]）。用于丢包检测与相对时序；**不是**绝对时间戳，真实时间由 Adapter 接收时刻 `time.monotonic()` 补充。

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

> **陀螺仪满量程注记**：换算系数 `48000 raw = 360°/s` 来自 [FR-PY]。据此 `1°/s = 133.333 raw`，int16 上限 `32767 raw ≈ 245.75 °/s` —— 这说明 raw 是**已按某档 FS 缩放后**的值，或高速旋转会 wrap；`[未真机验证]` 需在真机上快速旋转确认是否溢出 wrap，以及是否存在多档 FS。Motion Engine 侧对角速度做 `unwrap`/夹紧保护。

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
  - ⚠️ README 布局表写 Left Stick `0x08` / Right Stick `0x0B`。实现取 `0x0A` / `0x0D`。**两者差 2 字节，`[未真机验证]`**，Phase 2 真机时以能解出合理摇杆值的偏移为准，并更新本文件。
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

> `C` 按钮（Joy-Con 2 新增，位于右 Joy-Con）：`[未真机验证]`，社区掩码表未列出，Phase 2 真机时抓取。

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

> `[未真机验证]`：是否需要先发「standard full mode」再发 IMU 使能（第一代需要 `0x03 0x30` + `0x40 0x01`）。[FR-PY] 对 Joy-Con 2 **只发上面两条**即开始收到含 IMU 的报文，Phase 2 按此实现，真机不通再补。

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

来源：[FR-PY] README 布局表（原始作者 `@german77`），Left Joy-Con，IMU 已使能，报文总长约 **0x3E ≈ 62 字节**。

| Offset | Size | 字段 | 说明 / 换算 |
| --- | --- | --- | --- |
| `0x00` | 4 | Packet ID | uint32 LE，序号/时间戳 |
| `0x04` | 4 | Buttons | 位图（解码实现实际取 3 字节 big-endian，左 `data[4:7]` / 右 `data[3:6]`，见 §E） |
| `0x08` | 3 | Left Stick | 12-bit X/Y packed（见 §H.1）；解码实现实测取 `data[10:13]` `[未真机验证]` |
| `0x0B` | 3 | Right Stick | Left Joy-Con 上为垃圾数据；Right Joy-Con 有效，实测取 `data[13:16]` `[未真机验证]` |
| `0x0E` | 2 | Mouse X | 右 Joy-Con 光学传感器，含义部分未定 |
| `0x10` | 2 | Mouse Y | 同上 |
| `0x12` | 2 | Mouse Unk | 可能为额外运动数据 |
| `0x14` | 2 | Mouse Distance | 到表面的距离 |
| `0x16` | 2 | Magnetometer X | int16 LE |
| `0x18` | 2 | Magnetometer Y | int16 LE |
| `0x1A` | 2 | Magnetometer Z | int16 LE |
| `0x1C` | 2 | Battery Voltage | uint16 LE，mV（`1000 = 1V`） |
| `0x1E` | 2 | Battery Current | int16 LE，`100 = 1mA` |
| `0x20` | 14 | Reserved | 未文档化 |
| `0x2E` | 2 | Temperature | int16 LE，`25 + raw/127` °C |
| `0x30` | 2 | Accel X | int16 LE，`raw / 4096` g |
| `0x32` | 2 | Accel Y | 同上 |
| `0x34` | 2 | Accel Z | 同上 |
| `0x36` | 2 | Gyro X | int16 LE，`raw * 360/48000` °/s |
| `0x38` | 2 | Gyro Y | 同上 |
| `0x3A` | 2 | Gyro Z | 同上 |
| `0x3C` | 1 | Analog Trigger L | 0..255 |
| `0x3D` | 1 | Analog Trigger R | 0..255 |

> 实例（[FR-PY] README，Left Joy-Con 静置）：
> `08 67 00 00 | 00 00 00 00 | e0 ff 0f | ...`
> Packet ID `0x00006708`=26376；Buttons 全 0；Left Stick `e0 ff 0f` → X=`0x0FF0`=4080, Y=`0x0FE0`=4064（≈中心 + 少量偏置）。
> Accel `00 79 / 07 00 / 00 00` → axX=`0x7900`(LE)=`0x0079`? 见下注。

> **⚠️ Endianness 校验点**：README「Field Example」把 Accel X `00 79` 解释为 `0x7900 = 30976`（big-endian 读法），但 `solo_logic.decode_accel` 用 `byteorder='little'` → `0x7900` LE = `0x0079` = 121。两处不自洽。**以代码 (`little`, signed) 为准**，README 示例栏疑似笔误。真机静置时 Accel Z 应 ≈ ±4096（1 g），据此最终确认字节序。

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

| # | 验证项 | 方法 | 通过标准 |
| --- | --- | --- | --- |
| J1 | Sync 进入广播 | 按 Sync，运行 `prototype.py --scan` | 打印出 manuf id 1363 + 前缀 `01 00 03 7E` 的设备 |
| J2 | 连接 | `prototype.py --connect <addr>` | `is_connected == True`，dump 出 GATT 服务树 |
| J3 | 收原始 notification | 订阅 `ab7de9be-…` | 未使能 IMU 时也应有按键/摇杆报文 |
| J4 | IMU 使能 | 发 `ENABLE_IMU_1/2` | 报文长度增至 ~62B，`0x30+` 出现随姿态变化的值 |
| J5 | Accel 静置 | 放平 | 某一轴 ≈ ±4096 raw（1 g），其余 ≈ 0 |
| J6 | Gyro 静置 | 放平不动 | 三轴 raw ≈ 0（±噪声）；旋转时对应轴变化，方向自洽 |
| J7 | 字节序 | 结合 J5 | 确认 int16 LE signed（修正 §H 的 README 示例笔误） |
| J8 | 采样率 | 计时 1000 包 | ≈ 62 Hz（[EIMU]），记录实测值 |
| J9 | Left vs Right | 两只都测 | 按键掩码 / 摇杆偏移分别确认，更新 §E |
| J10 | 重连冷却 | 快速断连 5 次 | 复现「数分钟拒连」，验证 backoff 生效 |
| J11 | 延迟 | 时间戳链路 | p95 < 50 ms |
| J12 | C 按钮 / 出厂标定块 | 抓包 | 补全 §E 的 C 键掩码、§D.5 的标定来源 |

---

## K. 未决问题（须真机）

1. Service UUID 完整 GATT 树（§C.1）。
2. Stick / Buttons 的确切偏移（README 表 vs 代码实现不一致，§E/§H）。
3. 字节序最终确认（§H 校验点）。
4. 陀螺仪满量程 / 是否多档 FS / 高速是否 wrap（§D.4 注记）。
5. 是否需要「standard full mode」前置命令（§F）。
6. Magnetometer 单位/比例（§D.4）。
7. `C` 按钮掩码、出厂标定块位置（§E、§D.5）。
8. 每包是否含 IMU 子采样（§D.2）——当前按单采样处理。
9. 实测采样率 / 延迟分位数（§D.2/§D.3）。
