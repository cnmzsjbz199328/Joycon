# docs/ARCHITECTURE.md — 架构与技术选型

> 对应 GOAL.md **Phase 1**。三方案对比 + 最终选型理由 + 分层契约。

---

## 1. 目标架构

```
Joy-Con 2 (L / R)
   │  Bluetooth LE (自定义 GATT, 非 HID)         ← 只研究一次
   ▼
┌───────────────────────────────────────────────┐
│ JoyCon2 Adapter  (Python, bleak)              │
│  bluetooth/  扫描 · 连接 · 重连退避            │
│  protocol/   UUID · 命令 · 使能 IMU           │
│  decoder/    解包 buttons/stick/accel/gyro    │
│  calibration/ 静置标定 · 零偏 · 死区          │
│  websocket/  归一化 JSON 广播 (不降采样)       │
└───────────────────────────────────────────────┘
   │  WebSocket (ws://127.0.0.1:8765)  统一数据契约 §8.1
   ▼
┌───────────────────────────────────────────────┐
│ Browser (web/)                               │
│  input/     InputProvider 接口 + 5 实现       │
│             JoyCon2 · JoyCon1 · Gamepad ·     │
│             Keyboard · MockIMU                │
│  motion/    Motion Engine: 滤波·姿态·手势      │
│  ui/        连接状态 · 校准向导 · HUD          │
│  playground/ 实时 IMU 可视化 + 3D Sword       │
│  game/      Motion Fruit Slash                │
└───────────────────────────────────────────────┘
```

**硬性约束**：Adapter 与 Game 解耦。游戏只消费 `InputProvider` 事件与 `MotionState`，永不接触原始 IMU、永不知道背后是哪种硬件。

---

## 2. 三方案对比（GOAL.md Phase 1 要求）

| 维度 | 方案 A：浏览器直连<br>(Web Bluetooth / WebHID) | **方案 B：Native BLE Adapter → WebSocket** ✅ | 方案 C：虚拟手柄 → Gamepad API |
| --- | --- | --- | --- |
| 链路 | Browser → WebHID/WebBT → Joy-Con 2 | Joy-Con 2 → Python(bleak) → WS → Browser | Joy-Con 2 → ViGEmBus/uinput → Gamepad API |
| 能否拿到 IMU | **否（不可靠）**。WebHID 只认 HID 设备，Joy-Con 2 非 HID；Web Bluetooth 连私有 GATT 需 `chrome://flags` 实验开关，characteristic 受权限/黑名单约束，**社区零成功案例** | **是**。`bleak` 已被 4+ 项目验证可连 Joy-Con 2 并收到含 accel/gyro 的 notification | **否**。Gamepad API 无 orientation 概念，一般只给 buttons/axes；IMU 拿不到（`joy-con-webhid` 作者原话） |
| 跨平台 | Chrome/Edge only，且 flag | Win/mac/Linux（bleak 分别走 WinRT/CoreBluetooth/BlueZ） | ViGEmBus=Windows；Linux uinput 另写 |
| 复用现成代码 | 无 | **高**（joycon2py 协议/解码可改写，MIT） | 中（joycon2cpp 整套，但绑 Windows） |
| 延迟 | 最低（少一跳） | 本机回环 +2~3 ms，可接受（预算 <50 ms 内） | 手柄栈额外抖动 |
| 调试难度 | 浏览器 BLE 调试差 | Python 终端可打印原始字节，最易调 | 黑盒，难 |
| 采样率保真 | — | WebSocket 直转发，不降采样 | 手柄栈可能重采样 |
| 满足 GOAL.md 采用条件 | §6「仅当确认浏览器可直接可靠读 IMU」→ **不满足** | §6「当前优先方案」 | §6「不得仅依赖此方案做 IMU 游戏」 |

### 结论：采用方案 B

理由：
1. **唯一能可靠拿到完整 IMU** 的路径（A/C 都拿不到 gyro）。
2. GOAL.md §6 已把 B 定为「当前优先方案」，A 有严格前置条件且未被满足。
3. 复用度最高：`joycon2py`（MIT）的 UUID / 使能命令 / 解码算法可直接改写。
4. 最好调试：Python 侧可实时 dump 原始字节（Phase 2 交付「终端实时打印 IMU」直接受益）。
5. 分层最干净：Adapter 换语言、Browser 换 Provider 互不影响。

**保留 A 作为未来优化**：若某天 Chrome 稳定支持 Joy-Con 2 GATT，可新增 `JoyCon2WebBluetoothProvider`，架构其余部分不变。

---

## 3. Adapter 语言选型（GOAL.md §7.1：Python → Rust → Node）

**选 Python。**

| 判据（GOAL.md §7.1 优先级） | Python | Rust | Node |
| --- | --- | --- | --- |
| BLE 库稳定性 | `bleak` 成熟、跨三平台、社区大 | `btleplug` 可用但 API 摩擦多 | `@abandonware/noble` 维护弱、macOS 坑多 |
| Joy-Con 2 已有代码复用度 | **高**（joycon2py 直接就是 bleak） | 中（everything-imu 但耦合 SlimeVR） | 低 |
| 跨平台 | ✅ | ✅ | ⚠️ |
| 易调试 | **最好**（REPL、打印） | 编译慢 | 中 |

Node 仅用于 Web 侧构建（Vite），不用于 Adapter。若未来需要更低延迟/打包成单 exe，可移植到 Rust —— 契约（§8.1 JSON）不变，属实现替换。

---

## 4. 分层契约（谁依赖谁）

| 层 | 依赖 | 绝不依赖 | 可独立替换为 |
| --- | --- | --- | --- |
| Adapter | Joy-Con 2 硬件、bleak | 游戏逻辑、浏览器 | Rust/Node 重写 |
| WebSocket 契约 `shared/protocol/` | 无（纯 schema） | 任何实现 | — |
| InputProvider | 契约 schema | 具体硬件、Motion Engine 内部 | 5 种 Provider 任选 |
| Motion Engine | InputProvider 输出的原始帧 | three.js、DOM、游戏规则 | 滤波算法可换 |
| Playground / Game | MotionState + gesture 事件 | 原始 IMU、BLE、WebSocket 细节 | 新玩法叠加 |

**依赖方向单向向下**。任一层 mock 掉下层即可独立测试（Motion Engine 用 `MockIMUProvider` 测，Game 用录制的 MotionState 序列测）。

---

## 5. 数据流与线程模型

- **Adapter**：单 asyncio 事件循环。BLE notification 回调 → 解码 → 标定 → `websockets` 广播。每个 notification 立即转发，无缓冲队列、无节流。
- **WebSocket**：`ws://127.0.0.1:8765`，服务端 = Adapter，客户端 = 浏览器（可多个：Playground + Game 同开）。文本 JSON，每行一帧。心跳 ping 10s。
- **浏览器**：`JoyCon2Provider` 收 WS 消息 → 反序列化 → `emit('frame', rawFrame)`。Motion Engine 订阅 `frame`，用 `frame.timestamp`（Adapter 单调时钟）驱动积分，与 `requestAnimationFrame` 渲染解耦（GOAL.md §9）。
- **手势**：Motion Engine 内部滑动窗口（~0.3 s，≈20 帧）分析角速度/加速度峰值 → `emit('gesture', {...})`。

---

## 6. 目录结构（已按 GOAL.md §11 建立）

```
adapter/src/{bluetooth,protocol,decoder,calibration,websocket}/
web/src/{input,motion,playground,game,ui}/
shared/protocol/
docs/  tests/
```

---

## 7. Fallback 策略落地（GOAL.md §13）

无 Joy-Con 2 实机 / 某 OS BLE 不稳时：
- 浏览器侧切 `MockIMUProvider`（合成正弦 + 脚本化挥砍）或 `KeyboardProvider` / `GamepadProvider` / `JoyCon1Provider`。
- Motion Engine、Playground、Game 三者**完全不改**即可继续开发与验收。
- Joy-Con 2 相关验收项标 `EXPERIMENTAL / 未验收`，见各 Phase 文档与 [TESTING.md](./TESTING.md)。
- `JoyCon2Provider` 类头注释标 `@experimental`。

---

## 8. 决策记录（ADR 摘要）

| # | 决策 | 理由 | 状态 |
| --- | --- | --- | --- |
| ADR-1 | 采用方案 B | 唯一可靠拿到 IMU；GOAL 优先方案 | 已定 |
| ADR-2 | Adapter 用 Python + bleak | 复用 joycon2py、最易调试、跨平台 | 已定 |
| ADR-3 | WebSocket 传文本 JSON（非二进制） | 调试友好；62 Hz × ~300B 带宽无压力 | 已定，可后续优化为 msgpack |
| ADR-4 | gyro 输出 rad/s，accel 输出 g | Motion Engine 积分方便 | 已定 |
| ADR-5 | 姿态解算：Complementary 主 + Madgwick 备选 | 低延迟优先；VQF 过重 | 见 MOTION_ENGINE.md |
| ADR-6 | 静置标定（非出厂标定块） | 社区无 Joy-Con 2 出厂标定解析 | 可被真机发现替换 |
| ADR-7 | 时间戳用 Adapter `time.monotonic()` | packet ID 非绝对时间 | 已定 |
| ADR-8 | 摇杆用手柄自身出厂标定（flash `0x130A8`：中心 + 四向行程）+ 行程自学习 + 圆形限幅 + 径向死区 0.08；读不到时退回静置找中心 | `(raw-2048)/2048` 只到 ±0.6 且静置不为 0；社区的 ×1.7 增益不按单只手柄标定。真机两只：中心误差 ≤15 计数、八方向 r≥0.99 | 已定（2026-10-24） |
| ADR-9 | 协议 v2：一个 adapter 同时连左右，状态按手柄下发，`connected` = 该手柄在线；按键/摇杆不等 IMU 标定（`imuReady` 标记）；状态与帧走同一队列保证“断连之后不再有该手柄的帧” | 外部项目需要区分“WebSocket 通”与“手柄在线”，并且断连时不能卡键 | 已定（2026-10-24） |
| ADR-10 | 外部接入用纯逻辑参考客户端 `shared/protocol/input-client.mjs`（离线/stale/断开即释放），不在 adapter 端发合成“释放帧” | 帧只承载真实数据；释放规则在客户端一处实现、可单测；Python 侧规则见 `examples/input_client.py` | 已定（2026-10-24） |
