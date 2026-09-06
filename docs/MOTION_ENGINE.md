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

**仍未解决（需盯屏迭代）**：
- `THRUST` 判定在 swing 之前、门槛 `thrustAccel = 2.0 g`——真机手臂挥动的线加速度瞬间就 >2 g，导致 `THRUST` 抢在 swing 进入前触发，`SLASH_*` 出得很少。提高 `thrustAccel` 会撞到 Mock THRUST 的 `peak 3.2 g`，需要把硬件调参与 Mock 解耦（超出本次 bring-up 范围）。
- 四方向轴符号（§3 表）在真机上尚未干净复核：初步测试里挥击多被 `+gyro.z` 主导、方向区分不稳，可能是握持姿态或右 Joy-Con 的"指向前方"基准与表格不一致。
- 采样率 33.5 Hz 下一次快挥仅 ~5–7 帧，`windowSpan 0.35s` 峰值捕捉是否够待评估。

---

## 4. 手势判定算法（`GestureRecognizer`）

状态机：`idle → inSwing → idle`。

1. 每帧算 `speed = |ω|`（低通后）。
2. `speed > enterSpeed`(默认 6 rad/s) 且距上次发射 > `refractory`(0.28s) → 进入 `inSwing`，记录峰值向量。
3. `inSwing` 期间持续更新峰值。
4. `speed < exitSpeed`(3 rad/s) → 结束挥动：
   - 先判 `SHAKE`（窗口内主轴符号变化 ≥ 3 次且幅度足够）。
   - 否则按峰值向量**绝对值最大的轴**决定方向（见 §3）。
5. `THRUST` 是并行分支：`|linAccelHP| > thrustAccel`(2 g) 且 `speed < enterSpeed`。
6. 每个 `GestureEvent`：
   ```json
   { "gesture":"SLASH_RIGHT", "strength":0.82, "speed":11.5, "direction":[x,y,z], "timestamp":..., "controller":"left" }
   ```
   `strength = clamp(speed / fullSpeed, 0, 1)`，`fullSpeed` 默认 14 rad/s。`direction` 为峰值向量的单位向量。

**参数**（构造时可调，见 `gestures.js` 顶部）：`enterSpeed` `exitSpeed` `fullSpeed` `thrustAccel` `refractory` `windowSpan`(0.35s)。

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
| Adapter 级 | `adapter/src/calibration/` | 静置 2s：陀螺零偏、单位重力参考、加速度偏置、噪声死区 | 启动流程 step 5（GOAL.md §15） |
| Engine 级 | `motion-engine.js` | 再做一次逐帧收集：残余陀螺零偏 + 死区（应对 provider 未标定的情况，如 `JoyCon1Provider`、`GamepadProvider`） | Playground「Recalibrate」按钮 / 游戏开始前 |

Mock / synthetic 数据无偏，`calibrated=true` 直接给出。

---

## 7. 性能

- 每帧计算：~5 次向量低通 + 1 次四元数积分 + 1 次 slerp 修正 + 窗口维护 ≈ 数百次浮点运算，`O(1)`，62 Hz 下 CPU 可忽略。
- 与渲染解耦：引擎在 `frame` 事件里同步 `feed()`；渲染层每 `rAF` 读 `engine.state` 快照。
- 手势用原始 timestamp，不受掉帧影响。
