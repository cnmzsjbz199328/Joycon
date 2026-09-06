# Joy-Con 2 Motion Web Game Platform — 项目任务书

> **文档用途**：本文件是项目的唯一权威任务说明，用作 `/goal` 的输入。
> 执行 Agent 必须严格按本文件的目标、阶段顺序、交付物与验收标准推进，不得擅自跳过阶段或改变方向。
>
> | 项目 | 内容 |
> | --- | --- |
> | 项目名称 | Joy-Con 2 Motion Web Game Platform / Joy-Con 2 体感网页游戏平台 |
> | 文档版本 | v1.0 |
> | 创建日期 | 2026-09-06 |
> | 阅读对象 | 执行 Agent、后续协作者 |
> | 当前阶段 | 第一阶段（Phase 0 – Phase 8） |

---

## 1. 项目背景与定位

在 PC 上把 Nintendo Switch 2 的 **Joy-Con 2** 作为体感控制器使用。

本项目的产出**不是**一个单独的小游戏，而是一个**可持续扩展的体感游戏平台基础**：底层协议只研究一次，上层玩法可以不断叠加。

- 底层（研究一次）：`Joy-Con 2 → Bluetooth LE → Adapter → Motion Engine → 统一 Motion API`
- 上层（持续扩展）：Fruit Slash、Tennis、Table Tennis、Boxing、Racing、Bowling、Fishing、Rhythm Games……

第一个完整体感 Demo 为「**挥剑 / 切水果**（Motion Fruit Slash）」。只要底层链路稳定，后续每个小游戏本质上只是替换上层玩法。

---

## 2. 项目目标（Goals）

1. **G1 — 生态调研**：完成 Joy-Con 2 开源生态调研，明确哪些代码可复用，避免从零逆向协议。
2. **G2 — 协议与硬件验证**：在真机上验证 Joy-Con 2 的连接方式、协议类型、可读数据（按键 / 摇杆 / IMU）及其采样率、延迟、单位、标定方法。
3. **G3 — 解耦的输入层**：建立 `Adapter → Motion Engine → Browser SDK` 三层解耦架构，任意一层可独立替换。
4. **G4 — 统一 Motion API**：对游戏层暴露标准化的运动状态与手势事件，游戏不直接接触原始 IMU。
5. **G5 — Motion Playground**：提供实时 IMU 可视化与手势调试页面。
6. **G6 — 3D Sword Demo**：验证 `IMU → orientation → motion → gesture` 完整 pipeline。
7. **G7 — Motion Fruit Slash**：交付第一个完整、可玩、有爽感的体感 Demo。
8. **G8 — 可维护工程**：完整文档 + 清晰目录结构 + 分阶段提交历史。

---

## 3. 非目标（Non-Goals）

以下内容在第一阶段**明确不做**，防止范围蔓延：

- 从零逆向 Joy-Con 2 全部协议（应优先复用社区成果）。
- 一次性实现网球、乒乓球、拳击等多款游戏（架构需支持扩展，但本阶段只做 Fruit Slash）。
- 追求 3D 画面质量或美术资源（Demo 以验证 pipeline 为目的）。
- 依赖 Nintendo Switch 2 主机（整个流程必须脱离主机运行）。
- Rumble / 震动、鼠标传感器等非核心能力（可记录调研结论，不作为交付项）。
- Game Over / 关卡 / 复杂数值系统（Fruit Slash 是爽感型，不设失败结局）。

---

## 4. 核心原则（Guiding Principles）

1. **不从零逆向**：先深度调研现有开源社区成果，尽可能复用成熟代码。
2. **真机为准**：任何「Joy-Con 2 支持某功能」的结论，必须有真机验证；禁止用 Joy-Con 1 协议直接套用，禁止把 Joy-Con 2 当普通 Bluetooth HID。
3. **来源可追溯**：所有协议细节必须注明来源（GitHub / 抓包 / issue / 官方资料），不引用二手博客作为唯一依据。
4. **分层解耦**：BLE、Motion、Game 三者不得写死在一起。
5. **先验证后开发**：第一阶段问题（见 Phase 1）未回答前，不进入游戏开发。
6. **渐进交付**：每阶段先测试再 commit，不允许写完全部代码才测试。
7. **Fallback 不阻塞**：Joy-Con 2 BLE 在某 OS 受阻时，用 Provider 接口切换到 Joy-Con 1 / 手机 IMU / Mock IMU 继续开发上层；Joy-Con 2 硬件验证单独标记 `EXPERIMENTAL`，独立完成与验收。

---

## 5. 总体架构（Target Architecture）

```
Joy-Con 2
   │  Bluetooth LE
   ▼
JoyCon2 Adapter        （BLE 扫描 / 连接 / 初始化 / 使能 IMU / 解包 / 标定 / 归一化）
   │  normalized data
   ▼
Motion Engine          （滤波 / 死区 / 漂移处理 / 坐标归一化 / 运动幅度 / 手势识别）
   │  WebSocket
   ▼
Browser SDK            （Input Provider 接口 / 连接管理 / 事件分发）
   │
   ▼
Game                   （Motion Playground → 3D Sword → Fruit Slash → …）
```

**约束**：Adapter 与 Game 必须解耦；游戏层通过 Input Provider 接口消费数据，不感知具体硬件。

---

## 6. 里程碑与阶段划分（Milestones）

> 执行顺序**不可调整**。每阶段完成后：先测试 → 再 commit。

### Phase 0 — 生态调研（Research）

**目标**：摸清 Joy-Con 2 开源现状，决定复用策略。

**必须调查并验证以下项目**（含其最新 fork / issue / PR）：

| # | 项目 |
| --- | --- |
| 1 | https://github.com/TheFrano/joycon2py |
| 2 | https://github.com/Misaka10571/joycon2-connector |
| 3 | https://github.com/XenuIsWatching/hid-nintendo2-dkms |
| 4 | https://github.com/matiaspalmac/everything-imu |
| 5 | 第一代参考：https://github.com/tomayac/joy-con-webhid |
| 6 | 玩法参考：MinimumTennis、gyro-fruit-ninja / Blade Ninja |

**必须检索的关键词**：
`Joy-Con 2 BLE` / `Joy-Con 2 reverse engineering` / `Joy-Con 2 IMU` / `Joy-Con 2 accelerometer` / `Joy-Con 2 gyroscope` / `Joy-Con 2 GATT` / `Joy-Con 2 Bluetooth protocol` / `Joy-Con 2 PC` / `Joy-Con 2 Linux` / `Joy-Con 2 Windows` / `Joy-Con 2 Python` / `Joy-Con 2 Rust` / `Joy-Con 2 WebSocket`

**信息源优先级**：GitHub > 官方技术资料 > issue / PR > 实际抓包数据 > 真机测试记录。**不接受**仅有博客或二手文章支撑的结论。

**交付物**：`docs/RESEARCH.md`（内容清单见 §13.1）。

**验收标准**：
- 每个候选项目给出明确结论：`REUSE` / `REFERENCE` / `DO NOT USE`。
- 明确「IMU 是否已有公开代码可启用」。

---

### Phase 1 — 协议与硬件能力验证（Protocol Validation）

**目标**：在进入游戏开发前，回答下列全部问题。

| 编号 | 必须回答的问题 |
| --- | --- |
| A | Joy-Con 2 如何进入配对模式？ |
| B | PC 能否稳定发现并连接 Joy-Con 2？ |
| C | 使用哪种协议：BLE / proprietary GATT / HID over GATT / 其他？ |
| D | 能否读取 Left Stick、Right Stick、Buttons，以及 **Accelerometer (ax, ay, az)**、**Gyroscope (gx, gy, gz)**？若能，确认实际 Sampling Rate、Packet Rate、Latency、数据单位、数据范围、calibration 方法。 |
| E | Joy-Con 2 Left 与 Right 的 packet layout 是否不同？ |
| F | 是否已有公开代码能启用 IMU？ |
| G | 断开后的重连机制是什么？（社区出现过 rapid reconnect / temporary refusal，**必须加入 reconnect backoff**） |

**技术决策**（调研后至少比较三种方案）：

| 方案 | 链路 | 采用条件 |
| --- | --- | --- |
| A | Browser → Web Bluetooth / WebHID → Joy-Con 2 | **仅当**确认浏览器可直接、可靠读取 Joy-Con 2 IMU 时才允许采用 |
| **B** | Joy-Con 2 → Native BLE Adapter → WebSocket → Browser | **当前优先方案** |
| C | Joy-Con 2 → Virtual Gamepad / HID → Browser Gamepad API | Gamepad API 通常只能拿到 buttons / sticks，**不能假设能拿到 IMU**；IMU 游戏不得仅依赖此方案 |

**交付物**：
- `docs/JOYCON2_PROTOCOL.md`（内容清单见 §13.2）。
- `docs/ARCHITECTURE.md`（三方案对比 + 最终选型理由）。
- PC BLE connection prototype（能连上真机并打印原始 notification）。

**验收标准**：A–G 全部有基于真机的书面答案；协议文档每条细节均注明来源。

---

### Phase 2 — BLE Raw Reader + IMU Decoder

**目标**：稳定接收 Joy-Con 2 的 BLE 通知并解出结构化数据。

**任务**：BLE Scan → Device Detection → Pair / Connect → Initialization → Enable IMU → Receive Notifications → Decode packets（buttons / stick / accel / gyro）→ Calibration → Normalize。

**交付物**：
- `adapter/` 下 `bluetooth/`、`protocol/`、`decoder/`、`calibration/` 模块。
- IMU raw data reader：可在终端实时打印 ax/ay/az、gx/gy/gz 与按键 / 摇杆。

**验收标准**：Left 与 Right 均能解包；标定流程可复现；数据单位 / 范围与协议文档一致。

---

### Phase 3 — WebSocket Bridge + 数据契约

**目标**：Adapter 通过 WebSocket 输出标准化数据，且不降低 IMU 频率。

**交付物**：
- `adapter/src/websocket/` 输出模块。
- `shared/protocol/` 定义统一数据格式（见 §9）。

**验收标准**：浏览器端能以设备原始更新率接收数据；WebSocket 不做降采样；带真实 `timestamp`。

---

### Phase 4 — Motion Playground + 实时可视化

**目标**：提供 IMU 调试页面（**不要**直接做切水果）。

**页面必须显示**：
- Joy-Con Connection：`Connected` / `Disconnected`
- Controller：`LEFT` / `RIGHT`
- 实时 GYRO：X / Y / Z
- 实时 ACCEL：X / Y / Z
- Motion Speed
- Gesture（如 `SLASH RIGHT`，`Strength: 82%`）

**交付物**：`web/src/playground/` + `web/src/input/`（Input Provider 接口）+ `web/src/ui/`。

**验收标准**：有实时图形或数字显示，可用于调试 IMU；断连 / 重连状态正确反映。

---

### Phase 5 — 3D Sword Motion Demo

**目标**：在 Playground 中加入一个简单 3D 模型（推荐 Three.js，模型为一把剑），验证完整 pipeline。

**验收标准**：
- 现实中转动 Joy-Con → 网页中剑同步旋转。
- 现实中快速向右挥 → 网页中 Sword Slash Right。
- 目的为验证 `IMU → orientation → motion → gesture`，不考核画面质量。

---

### Phase 6 — Gesture Engine

**目标**：在 Motion Engine 中实现手势识别。

**初始手势集**：`SLASH_LEFT`、`SLASH_RIGHT`、`SLASH_UP`、`SLASH_DOWN`、`THRUST`、`SHAKE`、`ROTATE`。

**每次手势事件必须包含**：
```json
{ "gesture": "SLASH_RIGHT", "strength": 0.82, "speed": 4.1, "direction": [] }
```

**交付物**：`web/src/motion/`（或 adapter 侧，视架构而定）中的 Motion Engine 模块。

**验收标准**：四方向 slash 可稳定区分；手势事件字段完整；使用原始 timestamp 计算。

---

### Phase 7 — Motion Fruit Slash（第一个正式游戏）

**目标**：交付完整可玩的体感 Demo。

**玩法**：
- 水果（Watermelon / Orange / Apple / Banana）与 Bomb 随机从屏幕底部抛起。
- 玩家挥动 Joy-Con 2；当 `motionSpeed > threshold` 且检测到 `SLASH` 时，创建 Slash Trail。
- Slash Trail 穿过水果 → 水果切开 → `+score`；切到 Bomb → `-score`。
- **不设计 Game Over**，这是爽感型体感游戏。

**交付物**：`web/src/game/`。

**验收标准**：见 §17。

---

### Phase 8 — 文档整理与清理（Documentation + Cleanup）

**目标**：补全并校对全部文档，清理原型代码，确保工程可维护。

**交付物**：`docs/` 下 `RESEARCH.md`、`JOYCON2_PROTOCOL.md`、`ARCHITECTURE.md`、`MOTION_ENGINE.md`、`TESTING.md` 全部完成；`README.md` 含启动流程。

---

## 7. 组件规格

### 7.1 JoyCon2 Adapter

**语言候选（按优先级）**：Python → Rust → Node.js。

**选型标准**：BLE 库稳定性 > Joy-Con 2 已有代码复用程度 > 跨平台性 > 易于调试。
**禁止**为语言偏好而重写已有成熟协议代码。

**职责流水线**：
`BLE Scan → Device Detection → Pair / Connect → Initialization → Enable IMU → Receive Notifications → Decode packets → Calibration → Normalize → WebSocket Output`

**必须实现**：reconnect backoff（应对 rapid reconnect / temporary refusal）。

### 7.2 Motion Engine

游戏**不得**直接使用原始 IMU。Motion Engine 为独立模块。

**输入**：`accelerometer`、`gyroscope`、`orientation`、`timestamp`。

**输出（Motion State）**：
```json
{
  "orientation": {},
  "angularVelocity": {},
  "linearAcceleration": {},
  "motionSpeed": 0.0,
  "gesture": null
}
```

**至少包含的能力**：
1. Sensor calibration
2. Noise filtering
3. Dead zone
4. Drift handling
5. Coordinate normalization
6. Motion magnitude
7. Gesture detection

### 7.3 Browser SDK / Input Provider Interface

游戏、Motion Engine、UI **不依赖具体硬件**。定义 `Input Provider` 接口，实现：

- `JoyCon2Provider`（目标硬件，标记 `EXPERIMENTAL` 直至真机验收通过）
- `JoyCon1Provider`
- `GamepadProvider`
- `KeyboardProvider`
- `MockIMUProvider`

---

## 8. 数据契约（Data Contracts）

### 8.1 Adapter → Browser（统一输出格式）

```json
{
  "timestamp": 0,
  "controller": "left",
  "buttons": {},
  "stick": { "x": 0.0, "y": 0.0 },
  "accelerometer": { "x": 0.0, "y": 0.0, "z": 0.0 },
  "gyroscope": { "x": 0.0, "y": 0.0, "z": 0.0 }
}
```

若能得到姿态，追加：

```json
"orientation": { "pitch": 0, "yaw": 0, "roll": 0 }
```

### 8.2 Motion Engine → Game（Motion State）

见 §7.2。

### 8.3 Gesture 事件

```json
{ "gesture": "SLASH_RIGHT", "strength": 0.82, "speed": 4.1, "direction": [] }
```

数据格式定义统一放在 `shared/protocol/`。

---

## 9. 性能要求

| 指标 | 目标 |
| --- | --- |
| Motion latency | 尽可能 < 50 ms |
| 浏览器渲染 | 60 FPS |
| IMU packet 频率 | 尽量保持设备原始更新率（参考 60–100 Hz） |
| WebSocket | **不得**降低 IMU 数据频率 |
| Gesture Engine | 使用原始 timestamp 计算，与渲染帧率解耦 |

---

## 10. 滤波与姿态解算

至少评估：Low-pass filter、Complementary Filter、Madgwick Filter、Mahony Filter。

**原则**：不盲目使用复杂算法，目标是**低延迟、稳定、游戏体验优先**。选型与理由记录在 `docs/MOTION_ENGINE.md`。

---

## 11. 工程目录结构

```
joycon2-motion-platform/
├── README.md
├── docs/
│   ├── RESEARCH.md
│   ├── JOYCON2_PROTOCOL.md
│   ├── ARCHITECTURE.md
│   ├── MOTION_ENGINE.md
│   └── TESTING.md
├── adapter/
│   └── src/
│       ├── bluetooth/
│       ├── protocol/
│       ├── decoder/
│       ├── calibration/
│       └── websocket/
├── web/
│   └── src/
│       ├── input/
│       ├── motion/
│       ├── playground/
│       ├── game/
│       └── ui/
├── shared/
│   └── protocol/
└── tests/
```

---

## 12. 必需文档产出

### 12.1 `docs/RESEARCH.md`

每个候选项目必须记录：项目名、GitHub URL、Star 数、最近更新时间、支持设备、支持 OS，以及是否支持：Bluetooth / Buttons / Stick / IMU / Rumble / Mouse Sensor。

另需记录：代码质量、成熟程度、License、是否值得复用。

**最终对每个项目给出明确结论**：`REUSE` / `REFERENCE` / `DO NOT USE`。

### 12.2 `docs/JOYCON2_PROTOCOL.md`

必须记录：Bluetooth type、BLE Services、Characteristic UUID、Initialization commands、Notification format、packet structure、Button bytes、Stick bytes、IMU bytes、sample rate、endianness、scale、calibration、Left / Right difference。

**所有内容必须注明来源。**

---

## 13. 风险与 Fallback 策略

若 Joy-Con 2 BLE 在某操作系统暂时无法稳定工作：

- **不停止项目**。通过 `Input Provider` 接口切换到 `JoyCon1Provider` / 手机 IMU / `MockIMUProvider`，继续开发 Motion Engine 与游戏逻辑。
- Joy-Con 2 硬件验证**单独标记 `EXPERIMENTAL`**，独立完成、独立验收，**不得假装已完成**。
- 保证游戏、Motion Engine、UI 三者不依赖具体硬件。

---

## 14. 禁止事项（Hard Constraints）

1. 未经真机验证就声称 Joy-Con 2 支持某功能。
2. 直接把 Joy-Con 1 协议复制过来使用。
3. 把 Joy-Con 2 当作普通 Bluetooth HID。
4. 使用 mock IMU 后声称项目完成。
5. 一开始就做复杂游戏。
6. 把 BLE、Motion、Game 写死在一起。
7. 只留下无法维护的单文件 prototype。

---

## 15. 启动流程（UX）

1. 运行 Adapter。
2. 打开网页。
3. 点击 `Connect Joy-Con 2`。
4. 显示 `Connected`。
5. Calibration：提示「将 Joy-Con 放平保持 2 秒」。
6. `Calibration Complete`。
7. 进入 Motion Playground。
8. 开始游戏。

---

## 16. 第一阶段交付物清单

1. Joy-Con 2 开源生态调研报告（`docs/RESEARCH.md`）
2. Joy-Con 2 protocol summary（`docs/JOYCON2_PROTOCOL.md`）
3. PC BLE connection prototype
4. IMU raw data reader
5. WebSocket bridge
6. Browser Motion Playground
7. 实时 IMU visualization
8. Gesture detector
9. 3D Sword Motion Demo
10. Fruit Slash Game Demo

---

## 17. 最终验收标准（Definition of Done）

**前提**：有 Joy-Con 2 实机。整个流程不依赖 Nintendo Switch 2 主机。

1. 启动 Adapter → Joy-Con 2 成功连接。
2. 页面实时显示 accelerometer 与 gyroscope。
3. 实际转动 Joy-Con → 3D sword 同步变化。
4. 快速挥动 → 正确识别 `SLASH_LEFT` / `SLASH_RIGHT` / `SLASH_UP` / `SLASH_DOWN`。
5. 打开游戏 → 挥 Joy-Con → 水果被切开 → Score 增加。

**若无实机**：可用 Fallback Provider 完成 Motion Engine 与游戏逻辑的验收，但第 1–4 项中依赖 Joy-Con 2 硬件的部分标记为 `EXPERIMENTAL / 未验收`。

---

## 18. 执行顺序（不可调整）

| STEP | 内容 |
| --- | --- |
| 1 | Research |
| 2 | Protocol validation |
| 3 | BLE raw reader |
| 4 | IMU decoder |
| 5 | WebSocket bridge |
| 6 | Motion Playground |
| 7 | 3D Sword |
| 8 | Gesture Engine |
| 9 | Fruit Slash |
| 10 | Documentation + cleanup |

**每完成一个阶段：先测试，再提交 commit。禁止一次性写完所有代码才测试。**

---

## 19. 最终目标（重申）

本项目最终不是「一个 Joy-Con 切水果小游戏」，而是 **Joy-Con 2 Motion Platform**：

- 底层只研究一次：Joy-Con 2。
- 上层持续添加：Fruit Slash、Tennis、Table Tennis、Sword、Boxing、Racing、Bowling、Fishing、Rhythm Games……
- 最终形成一个 **Joy-Con 2 体感游戏实验平台**。
