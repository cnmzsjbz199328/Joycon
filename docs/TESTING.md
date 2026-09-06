# docs/TESTING.md — 测试与验收

> 对应 GOAL.md §16、§17。原则（§6）：**每阶段先测试再 commit**。

---

## 1. 如何跑测试

### Adapter（Python）
```bash
python -m venv .venv && .venv/bin/pip install -r adapter/requirements.txt
cd adapter && ../.venv/bin/python -m pytest -q
```
覆盖：命令帧构造、IMU 使能字节、reconnect 退避、解包（左右 + 参考样例包物理一致性）、
标定（零偏/重力/死区恢复）、WebSocket（200 帧按序不降采样、rad/s 转换、多客户端广播）。

### Web（Node 内置 test runner）
```bash
cd web && npm install && npm test
```
覆盖：四元数恒等式与积分、四方向 slash 区分、THRUST、不应期、手势事件字段、
每帧一个 MotionState、标定后死区。

### Web 端到端（headless Chromium，Mock IMU 驱动）
```bash
cd web
../.venv/bin/pip install playwright && ../.venv/bin/python -m playwright install chromium
~/.claude/skills/webapp-testing/scripts/with_server.py \
  --server "node_modules/.bin/vite --port 5173 --strictPort" --port 5173 \
  -- ../.venv/bin/python test/e2e_smoke.py
```
断言：三个页面无 console error；Playground 连接后控制器显示 LEFT、motionSpeed 峰值 > 0.4、
五种手势全部触发、3D 剑画布非空白；Fruit Slash 分数与切片数随脚本化 mock 上升。

---

## 2. 分阶段测试记录

| Phase | 测试方式 | 结果 |
| --- | --- | --- |
| 0 Research | 人工核对每个仓库的一手来源（README/源码），交叉验证协议 | 通过：6+ 项目均有明确 REUSE/REFERENCE/DO NOT USE 结论 |
| 1 Protocol | `prototype.py --scan` 在无 BLE 环境优雅退出；协议表逐条标源 | 通过；**真机复核（2026-09-06 右 Joy-Con）**：Service UUID、accel/gyro/stick 偏移、int16 LE、全按键 + C 键确认，见 HARDWARE_BRINGUP.md §5 |
| 2 Decoder + Calib | `pytest`：解包 roundtrip、参考样例 \|accel\|≈1g、标定零偏恢复；`reader.py` 对 replay/synthetic 实时打印 | 通过（17 用例） |
| 3 WebSocket | `pytest`：200 帧按序、`out/in==1.00`、多客户端；`service.py` 端到端 in≈out≈58 Hz | 通过 |
| 4 Playground | e2e：连接状态、LEFT/RIGHT、实时 gyro/accel 读数、motionSpeed、gesture 显示 | 通过 |
| 5 3D Sword | e2e：WebGL 画布非空白渲染；手动可见剑随姿态旋转、挥动出 trail | 通过（画面质量不考核） |
| 6 Gesture Engine | `npm test` + e2e：四方向 slash 稳定区分、事件字段完整、用原始 timestamp | 通过（12 用例 + e2e 五手势全中） |
| 7 Fruit Slash | e2e：脚本化 mock 挥砍 → 切片数 / 分数上升；切炸弹扣分且不结束 | 通过 |
| 8 Docs | 全部 docs/ 完成；`npm run build` 三页构建通过 | 通过 |

---

## 3. 最终验收（GOAL.md §17）

前提：**有 Joy-Con 2 实机**。首轮真机 bring-up 已于 **2026-09-06** 在 Mac mini（macOS / CoreBluetooth）用右 Joy-Con 2 执行，详见 [HARDWARE_BRINGUP.md](./HARDWARE_BRINGUP.md) §5：

| # | 验收项 | 状态 |
| --- | --- | --- |
| 1 | 启动 Adapter → Joy-Con 2 连接 | **BLE 链路已验证（右）**：scan→connect→enable IMU→decode 全通；Service UUID 补全；协议偏移与代码一致（仅订正 battery `0x1F`、补 C 键）。仍待：左 Joy-Con（J9）、完整 `--source joycon2` + WS 端到端、延迟分位数（J11）。 |
| 2 | 页面实时显示 accel 与 gyro | **已验收**（Fallback Provider）。Joy-Con 2 驱动的浏览器端到端待跑（Step E）。 |
| 3 | 转动 Joy-Con → 3D sword 同步 | 管线**已验收**（Mock/Keyboard/Gamepad/JoyCon1）；Joy-Con 2 真机驱动 3D 剑待现场跑。 |
| 4 | 快速挥动 → 识别 SLASH_LEFT/RIGHT/UP/DOWN | **已验收**（四方向单元测试 + e2e 全中）；真机手势轴符号待现场微调。 |
| 5 | 打开游戏 → 挥 Joy-Con → 水果被切 → Score 增加 | **已验收**（Fallback Provider）；Joy-Con 2 真机驱动待现场跑。 |

**结论**：Motion Engine、Playground、3D Sword、Gesture Engine、Fruit Slash 五项在 Fallback Provider 下**全部通过验收**。Joy-Con 2 BLE **底层协议链路已在真机验证**（accel 1 g / int16 LE、gyro 定轴、全按键 + C 键、Service UUID）；剩「左 Joy-Con 复核、浏览器端到端、延迟、真机手感」按 [JOYCON2_PROTOCOL.md](./JOYCON2_PROTOCOL.md) §J 清单继续（GOAL.md §13）。

---

## 4. 真机验收步骤（有 Joy-Con 2 时）

> 完整运行手册（含人的物理操作、逐步核对表、失败处理、订正落点）见
> [HARDWARE_BRINGUP.md](./HARDWARE_BRINGUP.md)。下面是精简版。

1. `python -m adapter.src.bluetooth.prototype --scan` → 确认发现设备（J1–J2）。
2. `python -m adapter.src.bluetooth.prototype --connect <addr> --seconds 20` → dump GATT 树 + 原始 notification；核对 §H 偏移、字节序（J3–J7）。
3. `python -m adapter.src.reader --source joycon2 --side left` → 静置看 accel≈(0,0,1)g、gyro≈0；旋转看方向自洽（J5–J6, J9）。
4. 记录实测采样率与延迟分位数（J8, J11）。
5. `python -m adapter.src.service --source joycon2` + 浏览器选 `Joy-Con 2 (adapter)` → 跑 Playground 与 Fruit Slash，完成 §17 第 1、3、4 项。
6. 快速断连 5 次复现控制器冷却，确认 backoff（J10）。
7. 把结果回填到 JOYCON2_PROTOCOL.md（去掉 `[未真机验证]` 标记）与本文件 §3。
