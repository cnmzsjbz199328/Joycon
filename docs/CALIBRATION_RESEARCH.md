# docs/CALIBRATION_RESEARCH.md — 校准（Calibration）专题调研

> 触发原因：用户实机玩 Nintendo Switch Sports 时观察到官方流程包含「两个 Joy-Con 放平校准」+
> 「对着屏幕按 X / 右键」，而本项目目前只实现了前半段。本报告调研 Nintendo 官方校准到底分几层、
> 「指向屏幕」那一步的技术本质是什么、Joy-Con 2 出厂校准数据是否可用、第三方开源项目怎么处理这个
> 问题，并给出结论。不是本次的实现任务，只落地为调研记录，供后续决策。
>
> 调研日期：2026-09-27。信息源优先级同 [RESEARCH.md](./RESEARCH.md)：一手源码/官方支持页 > 逆向文档 >
> 二手视频/论坛（**不作为唯一依据**）。本报告聚焦「校准」这一个主题，Joy-Con 2 协议本身的通用调研见
> [RESEARCH.md](./RESEARCH.md)。

---

## 0. 执行摘要（结论先行）

| 问题 | 结论 |
| --- | --- |
| 本项目现在的「校准」是什么？ | 只有一层：连接后「放平静止 2 秒」→ 陀螺零偏 + 重力参考 + 死区阈值（[`calibrator.py`](../adapter/src/calibration/calibrator.py) + [`calibration.js`](../web/src/ui/calibration.js)，对应 GOAL.md §15 步骤 5–6）。**不建立任何朝向屏幕的 yaw 参考**，且已有随时可点的「重新校准」按钮（`#recal`，见 [`playground/main.js:29`](../web/src/playground/main.js)）。 |
| 用户看到的「放平」和「对屏幕按 X」是同一层校准的两半吗？ | **不是。** 这是两件不同的事被使用者当成了一套流程：「放平」对应 Nintendo **系统级**「校正体感操作」菜单（Switch 主机设置里的功能）；「对屏幕按 X/右键」是**游戏自己（如 Switch Sports）实现的软件层动作**，系统 API 里没有这一步。 |
| 「对屏幕按 X」的技术本质是什么？ | 推断为**朝向锚点（yaw zero）+ 就绪确认**的复合手势，不是硬件校准。原因：陀螺仪积分姿态时，pitch/roll 能靠重力方向持续修正，**yaw 没有任何绝对参考**，只能靠某个人工事件「在这一帧，认为我正对着屏幕」来清零。Joy-Con 没有 Wii 那种红外感应条，Switch 也不支持指哪打哪的光学定位，所以只能靠这种「按键确认朝向」的软件约定替代。本项目 [MOTION_ENGINE.md](./MOTION_ENGINE.md) 第 4 条已自行承认「yaw 不校正（无磁力计，游戏可接受）」——即本项目目前的手势判定不依赖朝向锚点，但这正是这一步存在的原因。 |
| Joy-Con 出厂校准数据（SPI flash）对 Joy-Con 2 适用吗？ | 第一代（Switch 1）**已被逆向确认**：SPI flash `0x6020–0x6037` 是工厂 6 轴校准，`0x8026–0x803F` 是用户 6 轴校准（magic bytes `0xB2 0xA1` 标记是否写入），摇杆同理另有两组地址（dekuNukem）。**Joy-Con 2 尚未见公开逆向确认同类地址**——本项目自己的 [`calibrator.py`](../adapter/src/calibration/calibrator.py) 文档字符串已经记录过这个结论："No factory calibration block is known for Joy-Con 2 ([FR-PY] uses linear scales only)"。这是一个**开放问题**，不是「没有」，而是「社区还没查到 / 公开」。 |
| 第三方开源项目怎么做校准 UX？ | `JoyShockMapper`/`JoyShockLibrary`：手动触发式——放平控制器，按一下 Calibrate 键开始「持续校准」（采集陀螺读数取平均），再按一次结束；官方建议每次开局做一次，控制器发热后可能要再做一次。这与本项目「随时可重新点击 Start」的设计理念一致，属于已验证的最佳实践，**本项目已经具备**，不需要新增。`BetterJoy` 有一个已知未修复问题：其「re-center gyro」按键映射实际不生效（[#533](https://github.com/Davidobot/BetterJoy/issues/533)）——反面案例，提醒「重置」如果只重置显示朝向、不重置陀螺积分状态，容易做错。 |
| 要不要补一个「指向屏幕」校准步骤？ | **视后续玩法而定，不是现在的阻塞项。** 当前 `gestures.js` 用的是机体坐标系相对量（`gyro.z` 等），不依赖朝向锚点，SLASH/THRUST 判定不需要这一步。但如果要做瞄准类、需要「正面朝向屏幕」的玩法（保龄球助跑方向、网球持拍朝向、多人对战朝向一致性），就需要补上——好消息是这**不需要**读硬件 SPI，纯软件动作：在某一帧采样当前 orientation，定义为 `yaw = 0`，成本很低。 |

---

## 1. 本项目现状（对照基线）

- 代码位置：[`adapter/src/calibration/calibrator.py`](../adapter/src/calibration/calibrator.py)（`min_samples=60` ≈1s，`target_samples=124` ≈2s @ 62Hz）+ [`web/src/ui/calibration.js`](../web/src/ui/calibration.js)（进度条 UI）。
- 输出：`gyro_bias`（逐帧扣除）、`accel_bias`、`gravity_ref`（重力方向，pitch/roll 参考）、`gyro_noise` / `gyro_deadzone_dps`。
- 触发时机：`provider.calibrated` 为 false 时自动弹出（[`playground/main.js:21`](../web/src/playground/main.js)），同时有 `#recal` 按钮可随时重新触发。
- 明确不做的事：不建立 yaw 参考，不读取任何硬件出厂校准数据（純用当场采样的线性 offset）。
- 对应设计文档：GOAL.md §15「启动流程」步骤 5–6 只写了「放平保持 2 秒」，**没有**「指向屏幕」这一步——说明这不是遗漏了原计划的功能，而是原计划本身没覆盖到，是本次调研新发现的差距。

---

## 2. Nintendo 官方校准分几层

### 2.1 系统级：`系统设置 → 控制器与感应器 → 校正体感操作`

据 Nintendo 官方支持页（见来源清单），操作是：进入该菜单后，选择要校正的控制器，**按住该控制器上的 `-` 或 `+` 键**，同时**将控制器摇杆朝上平放在稳定的水平面上**保持几秒。

技术本质：这对应第一代 Joy-Con 已被逆向确认的 **用户校准区**写入操作——系统现场采样后，把新的 offset **写回控制器 SPI flash 的 user calibration 区**（`0x8026` 起，见 §3），覆盖/补充出厂值。这是「写入持久化到控制器本体」的校准，插到别的主机上也保留；本项目当前的校准是「每次连接都现场算、只存在软件进程内存里」，不持久化到控制器——这是两者的关键差异，也是它更接近 JoyShockMapper 而不是 Nintendo 系统菜单的地方。

### 2.2 出厂校准（Factory calibration，只读参考）

见 §3，逐台在工厂写入 SPI flash，系统/游戏可读取作为「没有用户校准时的默认值」。

### 2.3 游戏内「面向屏幕 + 按键确认」——不是系统 API

**这一步在 Nintendo 官方系统层面没有对应功能**（Switch 没有 Wii 那种红外感应条，系统设置菜单里也只有 2.1 那一种「校正体感操作」）。据此推断它是 Switch Sports（大概率延续自 Wii Sports 系列一贯的设计惯例）**自己在游戏逻辑里实现**的一次性动作，用途是给「正面朝向屏幕」定义一个 yaw 零点，同时兼作「这一局准备好了」的确认手势。之所以每个游戏要自己做，是因为：

- 陀螺仪只能测**角速度**，姿态是靠积分获得的；pitch/roll 能被重力方向（加速度计）持续拉回，**yaw（绕重力轴转）没有任何物理量能提供绝对参考**，纯积分必然随时间漂移。
- 唯一能消除 yaw 漂移的办法是磁力计（罗盘）或外部光学定位（如 Wii 感应条），而 Joy-Con（一代二代）实测都没有可靠的磁力计输出——本项目自己抓包 Joy-Con 2 的磁力计字段（`0x16`/`0x18`/`0x1A`）**恒为 0，未使能**（见 [JOYCON2_PROTOCOL.md:224-226](./JOYCON2_PROTOCOL.md)），Switch 主机也没有给 Joy-Con 配红外感应条。
- 于是只能靠「玩家自己对准屏幕，按键的那一刻」当作人工锚点：游戏在收到按键的那一帧，把当前姿态估计的 yaw 分量重置为 0（或记录一个 offset，后续渲染时减去它）。这是纯软件动作，和 §2.1/§3 的硬件出厂/用户校准完全无关。

---

## 3. Joy-Con SPI flash 出厂校准——逐代对比

| | Joy-Con 1（Switch 1） | Joy-Con 2（Switch 2，本项目目标） |
| --- | --- | --- |
| 硬件 | SPI 总线上挂 1 颗 flash（MX25U4033E）+ 1 颗 LSM6DS3 6 轴 IMU | 未知具体 IMU 型号；BLE 协议已被 `joycon2py`/`joycon2cpp` 等逆向（见 [RESEARCH.md](./RESEARCH.md) §1） |
| 工厂 6 轴校准地址 | `0x6020–0x6037`（4 组 × 3 × int16 LE：accel/gyro 的 origin + 灵敏度系数） | **未见公开逆向确认**——`joycon2py`（本项目 `REFERENCE` 主参考）用的是固定线性比例常数（accel `4096=1G`、gyro `48000=360°/s`），不是逐台 SPI 校准值 |
| 用户 6 轴校准地址 | `0x8026–0x803F`，magic bytes `0xB2 0xA1` 标记是否已写入用户值 | 同上，未见资料 |
| 摇杆工厂/用户校准 | 工厂 `0x603D–0x604E`（左右各一段）；用户 `0x8010–0x8025` | 未见资料；`joycon2py` 摇杆按 12-bit packed + 固定中心值 `2048` 解码，同样不读 SPI |
| 已知怪癖 | "gyro calibration is always 13371"（社区戏称的固定校准魔数，见 issue 讨论） | 本项目自己实测：反复连接会触发数分钟的控制器级冷却（[RESEARCH.md](./RESEARCH.md) §1.1），与校准无直接关系但同属「现场探测有代价」的坑 |

**结论**：JC1 的 SPI 校准结构由 `dekuNukem/Nintendo_Switch_Reverse_Engineering` 完整记录，属于社区公认的一手资料。JC2 目前没有等价的公开记录——这不代表 JC2 一定没有类似机制（新硬件大概率仍然复用「SPI flash + 出厂校准块」这套设计，只是还没人逆向确认地址），但在有人验证之前，**不能假设**它存在或地址不变。

**可选的下一步验证（本次调研范围之外，仅记录思路，不在本报告中执行）**：本项目 adapter 已经具备向 Joy-Con 2 发送自定义写命令的能力（`0x91` 系列命令，见 [RESEARCH.md](./RESEARCH.md) §1.1），理论上可以模仿 JC1 的 SPI-read 子命令格式，对 JC2 的 `0x6020` 附近地址发探测请求，看是否返回类似「4 组 3×int16」结构的非零数据。这需要真机 + 抓包比对，属于新的实验任务，不属于本次「文档调研」的交付范围。

---

## 4. 第三方开源项目的校准 UX 惯例

| 项目 | 校准方式 | 触发时机 | 对本项目的参考价值 |
| --- | --- | --- | --- |
| `JibbSmart/JoyShockLibrary` + `JoyShockMapper` | 按住/点击 Calibrate 键（PS/Home/Capture 键）开始「持续校准」，采集陀螺数据取平均作为零偏；再按一次关闭 | 每次开局建议做一次；控制器发热后可能需要重新做 | **已验证的最佳实践**，与本项目「自动 2 秒 + 随时可点 `#recal` 重新校准」的设计一致，说明当前方案没有偏离社区共识 |
| `Davidobot/BetterJoy` | 提供「re-center gyro」按键映射 | 手动 | **反面案例**：[issue #533](https://github.com/Davidobot/BetterJoy/issues/533) 报告该映射实际不生效——常见错误是只重置了姿态显示/渲染层，没有真正清零陀螺积分状态。本项目若未来加朝向锚点功能，需确保清零的是 Motion Engine 内部积分状态，而不是只在 UI 层做视觉复位 |
| `TheFrano/joycon2py` / `joycon2cpp` | 无校准 UI，固定线性 scale 常数 | N/A | 印证 §3 的结论：现有 JC2 社区实现都没有做 SPI 出厂校准读取 |
| Nintendo 系统菜单（§2.1） | 放平 + 按 `-`/`+`，结果写回控制器 | 用户主动进入设置菜单 | 「写回控制器持久化」这一层，本项目和所有上述第三方项目都没有做（也没必要——本项目场景是 PC 单机调试，跨主机持久化的价值低） |

---

## 5. 结论与建议（供后续决策，本报告不包含实现）

1. **不建议现在投入**：Joy-Con 2 SPI 出厂校准读取。价值不确定（§3 的开放问题），且当前「现场 2 秒采样」的精度已经支撑到 SLASH_RIGHT 端到端验证通过（见 [HARDWARE_BRINGUP.md](./HARDWARE_BRINGUP.md) §5）。
2. **不需要新增**：「随时可重新校准」的按钮式 UX——已经存在（`#recal`），符合 JoyShockMapper 的社区惯例。
3. **值得规划、但优先级取决于后续玩法**：「面向屏幕 + 按键」朝向锚点。只有当项目往指向类/朝向敏感类玩法（瞄准、需要区分「正面挥」还是「侧身挥」的运动项目）发展时才是必须项；纯相对角速度手势（当前 SLASH/THRUST）不需要。技术上是纯软件事件（采样当前 yaw 并置零），不依赖 §3 的开放问题，可以独立于 SPI 调研随时排期。

---

## 6. 来源清单

- Nintendo 官方支持（系统级校正体感操作）— https://en-americas-support.nintendo.com/app/answers/detail/a_id/44640/~/how-to-calibrate-motion-controls-on-nintendo-switch
- Nintendo 官方支持（校正控制器，含摇杆）— https://en-americas-support.nintendo.com/app/answers/detail/a_id/22340/~/how-to-calibrate-the-controllers-on-nintendo-switch
- dekuNukem/Nintendo_Switch_Reverse_Engineering — https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering
- dekuNukem — SPI flash notes（工厂/用户校准地址）— https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering/blob/master/spi_flash_notes.md
- dekuNukem — IMU sensor notes — https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering/blob/master/imu_sensor_notes.md
- JibbSmart/JoyShockLibrary — https://github.com/JibbSmart/JoyShockLibrary
- JibbSmart/JoyShockMapper — https://github.com/JibbSmart/JoyShockMapper
- JoyShockMapper 使用指南（Calibrate 按键行为）— https://gyrowiki.jibbsmart.com/blog:joyshockmapper-guide
- Davidobot/BetterJoy — re-center gyro 失效 issue — https://github.com/Davidobot/BetterJoy/issues/533
- 本项目一手代码：[`adapter/src/calibration/calibrator.py`](../adapter/src/calibration/calibrator.py)、[`web/src/ui/calibration.js`](../web/src/ui/calibration.js)、[`web/src/playground/main.js`](../web/src/playground/main.js)、[`docs/JOYCON2_PROTOCOL.md`](./JOYCON2_PROTOCOL.md)、[`docs/MOTION_ENGINE.md`](./MOTION_ENGINE.md)、`GOAL.md` §15
