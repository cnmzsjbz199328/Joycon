# docs/MOTION_ENGINE.md — Motion Engine 设计

> 对应 GOAL.md **Phase 6** + §7.2 + §10。
> 代码：[web/src/motion/](../web/src/motion/)。games 只消费 `MotionState` 与 `gesture` 事件，**永不接触原始 IMU**（GOAL.md §14.6）。

---

## 1. 职责（GOAL.md §7.2 的 7 项能力）

| # | 能力 | 实现位置 |
| --- | --- | --- |
| 1 | Sensor calibration | `motion-engine.js` `startCalibration()` + 逐帧收集；adapter 侧另有静置标定（`calibration/calibrator.py`），两级叠加 |
| 2 | Noise filtering | `filters.js` `LowPass`（陀螺 12 Hz、加速度 6 Hz 一阶低通） |
| 3 | Dead zone | `filters.js` `deadZone()`，阈值 = 标定噪声 3σ，平滑再入（边缘无跳变） |
| 4 | Drift handling | 陀螺零偏逐帧扣除；Complementary filter 用重力方向缓修 pitch/roll 漂移；yaw 不校正（无磁力计，游戏可接受） |
| 5 | Coordinate normalization | `orientation.js` 输出统一四元数 `[w,x,y,z]` + ZYX 欧拉角；重力从 world `+Z` 旋到 body 后从加速度里扣除 |
| 6 | Motion magnitude | `motionSpeed = |ω|/fullSpeed + |a_lin_hp|/3`，再过 10 Hz 低通 |
| 7 | Gesture detection | `gestures.js` `GestureRecognizer`（阈值 + 主轴 + 不应期） |

---

## 2. 数据流

```
InputFrame (accel g, gyro rad/s, 已由 adapter 去偏)
  │
  ├─ 运行时再标定：startCalibration(2s) 收集 → 更新 gyroBias / gyroDeadZone
  │
  ├─ gyro:  - bias  → deadZone  → LowPass(12Hz)  ─┐
  ├─ accel: LowPass(6Hz) ─────────────────────────┤
  │                                               ▼
  │                                   Orientation filter (Complementary 默认)
  │                                               │  q (quaternion)
  │                       gravityBody = q⁻¹ · [0,0,1]
  │                       linAccel = accel - gravityBody
  │                       linAccelHP = HighPass(1.5Hz)  (隔离挥砍瞬态)
  │                                               │
  ├─ motionSpeed  ← |ω|/full + |linAccelHP|/3  → LowPass(10Hz)
  │
  └─ GestureRecognizer.update(t, gyroF, linAccelHP)  → GestureEvent?
                                               │
                     ┌─────────────────────────┴─────────────────────────┐
              emit "motion" (MotionState, 每帧一次)          emit "gesture" (完成时)
```

**时间基准**：全部用 `frame.timestamp`（adapter 单调时钟 / provider `performance.now()`），**不用 `requestAnimationFrame`**，因此手势判定与渲染帧率解耦（GOAL.md §9）。`dt` 有 gap 保护（>0.25s 或非正 → 回退 1/62）。

---

## 3. 坐标与手势轴约定

Joy-Con 指向正前方（远离玩家）：

| 轴 | 物理动作 | 手势 |
| --- | --- | --- |
| `gyro.z`（yaw）+ | 向右挥 | `SLASH_RIGHT` |
| `gyro.z`（yaw）− | 向左挥 | `SLASH_LEFT` |
| `gyro.x`（pitch）+ | 向上挑 | `SLASH_UP` |
| `gyro.x`（pitch）− | 向下劈 | `SLASH_DOWN` |
| `gyro.y`（roll）主导 | 拧转 | `ROTATE` |
| 前向线加速度尖峰 + 低转速 | 前刺 | `THRUST` |
| 主轴多次变号 + 无单一主导 | 抖动 | `SHAKE` |

> 真机上若方向与体感相反（取决于 Joy-Con 姿态与 L/R），在 `GestureRecognizer` 构造参数里翻转对应轴符号即可，不动引擎其余部分。

### 3.1 真机标定（2026-09-06，右 Joy-Con 2，macOS）

实测角速度量级（wire 单位 rad/s）：静置 <0.05、手持轻晃 ~0.9、干脆挥击 ~1.6–2.0、**拼尽全力旋转峰值 ~2.7**。
对照 Mock IMU 的合成挥击是 900 dps ≈ **15.7 rad/s**——高了约 6×。原 `enterSpeed 6.0 / fullSpeed 14.0` 在真机上**永远够不到**，每次挥击都落到 `THRUST` 分支。

已改（`gestures.js` 顶部默认值）：`enterSpeed 6.0→1.5`、`exitSpeed 3.0→0.6`、`fullSpeed 14.0→2.6`。
Mock IMU（15.7 rad/s）仍轻松越过新阈值，`gestures.test.js` 用硬编码 `peak:16`／已把"gentle"用例改成 `peak:1.0`，17 项 web 测试全过。

**`THRUST` 抢占已修**（`gestures.js` `update()`）：原来 `THRUST` 只看当前帧转速，挥击起手转速还在爬坡时线加速度已 >2 g，`THRUST` 抢先触发、`refractory` 再吞掉 150 ms 后本该完成的 `SLASH`。改为看**滑动窗口内转速峰值**——最近 0.35 s 内只要越过 `enterSpeed` 就交给 swing 分支，不发 `THRUST`。

**已验证方向：`SLASH_RIGHT`（右 Joy-Con，2026-09-06）**
水平前挥（forehand，手腕带转让手柄"指向"扫过弧线）：稳定产生 `gyro.z` 正、峰值 1.8–2.2 rad/s → 识别器判 `SLASH_RIGHT`，强度 0.6–0.8，方向向量 ≈ `[-0.44, -0.15, +0.87]`。30 s / 22 次判定里 6 次 forehand 全部正确、且前面无 `THRUST` 抢跑。
→ **§3 表的 `gyro.z + → SLASH_RIGHT` 对右 Joy-Con 成立，z 轴不用翻符号。**

**仍待逐个做透**：
- `SLASH_UP`：本轮（见 §3.2）已在左 Joy-Con 上出现，`LEFT/RIGHT/DOWN` 同样确认，方向轴符号暂不需要翻。
- `thrustAccel = 2.0 g` 提高会撞到 Mock THRUST 的 `peak 3.2 g`（现已提到 `peak 6.0` 留出余量，见 §3.2），硬件调参与 Mock 需解耦。
- 采样率 33.5 Hz 下一次快挥仅 ~12–14 帧（`windowSpan 0.35s`），峰值捕捉实测够用。

### 3.2 真机标定（2026-09-28，左 Joy-Con 2，自然/连贯动作）

上一轮（§3.1）的预判命中了：回挥转速常掉到 `enterSpeed` 以下落回 `THRUST`。本轮左手柄真机测试彻底查清楚，是**两个独立问题叠加**，都已修复：

1. **THRUST 判定时机太早**：线加速度比转速先冲高——挥击起手 1-2 帧内 `accelMag` 已 >2g，但滑动窗口内的转速峰值还没爬上来，`THRUST` 当场判定；再过 2-4 帧转速才真正越过 `enterSpeed`，证明其实是一次挥砍。修法：`THRUST` 判定前要求"低转速+高加速度"这个条件**连续保持 N 帧**才下结论（`thrustHoldFrames`，新参数），给转速时间爬升；先试 3 帧不够、调到 4 帧修好了大部分。
2. **真正的根因——阈值本身对不上自然动作**：让用户"自然地""连贯地"挥（不是单次拼尽全力的孤立挥砍）之后，实测挥砍峰值转速普遍只有 **1.2–1.5 rad/s**——低于 §3.1 用**单次孤立右手用力挥砍**标定出的 `enterSpeed=1.5`。连贯/自然动作力度分散在整个组合动作里，峰值天然比孤立全力一击低，不管 `thrustHoldFrames` 等多久都够不到 1.5。**把 `enterSpeed` 从 1.5 降到 1.1**（仍留出高于"轻晃 0.9"的余量）后，左手柄自然连贯挥动 11/12 次正确判为 `SLASH_*`，只 1 次残留误判 `THRUST`。
3. **连贯反向动作会丢一半**（用户提出）：人的自然动作里"挥上接挥下""挥左接挥右"是一口气完成的，转速幅值不会真正掉回 `exitSpeed` 以下——原来的峰值追踪只记录**单个**最大值，第二段动作永远拿不到自己的手势（要么被合并进第一段的峰值，要么第一段直接丢失）。修法：`inSwing` 期间如果峰值主轴**同轴反号**且新方向幅值也过 `enterSpeed`，视为一次动作的自然分界——先对前半段收尾发一个事件，再从当前帧开始追踪后半段。合成数据验证：连贯"挥上接挥下"正确拆成 `SLASH_UP` + `SLASH_DOWN` 两个事件（左右同理）。

**结论**：`enterSpeed 1.5→1.1`、新增 `thrustHoldFrames`（默认 4）、新增峰值同轴反号分段逻辑，均已写入 `gestures.js` 默认值/`update()`；`web/test/gestures.test.js` 沿用现有断言全过，`mock-imu-provider.js` 的合成 THRUST 峰值从 3.2 提到 6.0 g 以确保示例数据仍能稳定越过新的连续帧要求。**残留已知限制**：约 1/12 的连贯挥动仍可能误判 `THRUST`（真实人手动作有噪声，阈值调参不可能做到 100%；继续加大 `thrustHoldFrames` 收益递减且会拖慢真正 THRUST 的响应，暂不继续深抠）。

---

## 4. 手势判定算法（`GestureRecognizer`）

状态机：`idle → inSwing → idle`。

1. 每帧算 `speed = |ω|`（低通后）。
2. `speed > enterSpeed`(默认 1.1 rad/s) 且距上次发射 > `refractory`(0.28s) → 进入 `inSwing`，记录峰值向量。
3. `inSwing` 期间：若当前帧在峰值的**主导轴上同轴反号**且新方向幅值也过 `enterSpeed`（自然的连贯反向动作，如挥上接挥下），先对已追踪的峰值收尾发一个事件，再从当前帧开始追踪新的一段（§3.2）；否则正常持续更新峰值。
4. `speed < exitSpeed`(0.6 rad/s) → 结束挥动：
   - 先判 `SHAKE`（窗口内主轴符号变化 ≥ 3 次且幅度足够）。
   - 否则按峰值向量**绝对值最大的轴**决定方向（见 §3）。
5. `THRUST` 是并行分支：`|linAccelHP| > thrustAccel`(2 g) 且**滑动窗口内转速峰值** < `enterSpeed`，且这个条件连续成立 `thrustHoldFrames`(默认 4) 帧才下结论（§3.2，避免线加速度比转速先冲高导致的抢跑误判）。
6. 每个 `GestureEvent`：
   ```json
   { "gesture":"SLASH_RIGHT", "strength":0.82, "speed":11.5, "direction":[x,y,z], "timestamp":..., "controller":"left" }
   ```
   `strength = clamp(speed / fullSpeed, 0, 1)`，`fullSpeed` 默认 2.6 rad/s。`direction` 为峰值向量的单位向量。

**参数**（构造时可调，见 `gestures.js` 顶部）：`enterSpeed` `exitSpeed` `fullSpeed` `thrustAccel` `thrustHoldFrames` `refractory` `windowSpan`(0.35s)。

**验证**：[web/test/gestures.test.js](../web/test/gestures.test.js) + [web/test/motion-engine.test.js](../web/test/motion-engine.test.js) —— 四方向可稳定区分、不应期生效、事件字段完整、scripted mock 一个周期内产出全部 5 种手势。

---

## 5. 姿态解算选型（GOAL.md §10）

评估四种：

| 算法 | 延迟 | 抗漂移 | 计算量 | 调参难度 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **Low-pass only**（不解算姿态） | 最低 | 无（只滤噪） | 极低 | 无 | 不够——3D Sword 需要绝对姿态 |
| **Complementary**（陀螺积分 + 重力缓修） | 低（陀螺直通） | pitch/roll 好，yaw 漂移 | 低 | 1 个增益 | **默认采用** |
| **Madgwick**（梯度下降融合） | 低 | 略好于 Complementary | 中 | 1 个 β | 已实现，`filter:"madgwick"` 可切；作对照 |
| **Mahony**（PI 反馈） | 低 | 类似 Madgwick | 中 | 2 个增益（Kp/Ki） | 未实现——相对 Madgwick 无额外收益 |
| VQF（`everything-imu` 默认） | 低 | 最好 | 高 | 多参数 + 需要陀螺自适应零偏估计 | 过重，游戏场景不必要 |

**决策（ADR-5）**：默认 **Complementary**。
理由（GOAL.md §10「不盲目使用复杂算法，低延迟、稳定、游戏体验优先」）：
- 陀螺积分直通 → 转动响应零额外延迟。
- 只有 1 个可调增益（`accelGain`，默认 0.02/帧当量），易调稳。
- 切水果/挥剑不需要绝对 yaw；pitch/roll 由重力缓修足够稳。
- Madgwick 保留为一行切换的对照项，真机若发现 Complementary 抖动可换。

**加速度信任门**：仅当 `|accel| ∈ [1-0.15, 1+0.15] g` 时才用它修正姿态（挥动瞬间加速度不可信，跳过修正，纯靠陀螺）。

---

## 6. 两级标定

| 级 | 位置 | 做什么 | 何时 |
| --- | --- | --- | --- |
| Adapter 级 | `adapter/src/calibration/` | 静置 2s：陀螺零偏、单位重力参考、加速度偏置、噪声死区。每只手柄各一份，**须静止**（窗口内陀螺噪声 > 2 dps 则重来），重连后保留 | 连上后自动进行；协议 v2 起帧从第一包就下发，标定完成前帧带 `imuReady:false`，Engine 跳过这些帧（不积分、不收集 Engine 级标定），按键/摇杆不受影响 |
| Engine 级 | `motion-engine.js` | 再做一次逐帧收集：残余陀螺零偏 + 死区（应对 provider 未标定的情况，如 `JoyCon1Provider`、`GamepadProvider`） | Playground「Recalibrate」按钮 / 游戏开始前 |

Mock / synthetic 数据无偏，`calibrated=true` 直接给出。

---

## 7. 性能

- 每帧计算：~5 次向量低通 + 1 次四元数积分 + 1 次 slerp 修正 + 窗口维护 ≈ 数百次浮点运算，`O(1)`，62 Hz 下 CPU 可忽略。
- 与渲染解耦：引擎在 `frame` 事件里同步 `feed()`；渲染层每 `rAF` 读 `engine.state` 快照。
- 手势用原始 timestamp，不受掉帧影响。
