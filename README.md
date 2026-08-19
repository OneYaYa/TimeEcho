# TIME ECHO / 时间回响

**简体中文** | [English](README.en.md)

《时间回响》是一款浏览器运行的像素风时间循环探索游戏。目前开发基于godot4.6，html版本仅为初稿，不再维护。测试请基于godot4.6版本启动。

## 启动

html初稿版本

在 PowerShell 中运行：

```powershell
cd C:\Users\ethanypan\Desktop\mygame
python server.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

不要直接双击 `index.html`，浏览器会阻止模块和 JSON 数据加载。

## Godot 4.6 版本

完整 Godot 4.6 工程位于 [`godot/`](godot/)，主场景为 `godot/scenes/main/main.tscn`。使用 Godot 4.6 打开 `godot/project.godot`，或在仓库根目录运行：

```在powershell运行启动游戏
& "your-path-to-godot.exe" --path .\godot
```

Godot 版保留相同 JSON 数据、18 个地点、7 位 NPC、时间循环、谜题、AI 本地回退和存档语义，并迁移了 `art/` 美术资产。详细信息：

- [迁移报告](godot/MIGRATION_REPORT.md)
- [迁移分析](godot/MIGRATION_ANALYSIS.md)
- [18 个地图实际渲染画廊](godot/MAP_RENDER_GALLERY.md)
- [测试清单](godot/TEST_CHECKLIST.md)
- [AI NPC 技术升级说明](godot/docs/AI_NPC_TECH_UPGRADE.md)

Godot 自动测试：

```powershell
godot --headless --path godot --editor --quit
godot --headless --path godot res://tests/test_runner.tscn
python godot/tests/validate_project.py
```

## 操作

- `WASD` / 方向键：移动
- `Shift`：疾跑
- `E`：与居民、现场物件、门和道路互动
- `J`：打开跨循环维修日志
- 自由对话期间：游戏时间以四分之一速度继续
- 退潮洞穴、隐藏暗房：游戏时间暂停

一轮从星期六 06:00 到星期日 06:00，对应现实约 12 分钟。05:55 开始白光重置演出。

## 当前可玩内容

- 英文标题界面与独立雇主序章
- 六个超过一屏的公共场景：湖畔旅店前庭、钟影广场、礼拜堂山坡、银盐巷、档案坡道、回潮港
- 十余个室内/隐藏空间：旅店大堂与二楼、八号房、主钟维修舱与地下室、礼拜堂钟厅与钟楼、照相馆与第二暗房、档案室、港务控制室、退潮洞穴
- 三种不同的维修谜题：齿轮交换/校准、六锤擒纵、三环潮汐刻度
- 洞穴底片的三步显影谜题与四锚点身份定影
- 七位居民的职业位置、晚间作息、走动、角色立绘与六帧步行/疾跑动画
- `art` 原始素材经过透明化、裁边和 WebP 优化后进入实际场景；建筑、家具、装饰与船只加载失败时仍有程序绘制回退
- 分场景的原创程序化环境声、脚步、钟声与轻量五声音阶配乐
- 电影化湖镇全景用于白光重置和两个结局演出
- 跨轮日志、照片保留和本轮实物复位
- 表层结局与真结局

## 对话与证据边界

自由输入负责开放表达，固定选项定义可验证行动。自由输入只有在同一固定动作已经由引擎开放、且模型明确选中该动作时，才能走进相同的本地验证与状态变更流程：

1. NPC 只接收其当前状态允许知道的公开事实。
2. 玩家提前说出 `Ada Rowan`、七号房或第七见证人，不会直接解锁知识。
3. 需要居民亲自执行的动作必须同时满足本轮实物、记录、身份和责任条件。
4. 跨轮日志属于玩家记忆，不会伪装成本轮已经与 NPC 共同调查过的证据。
5. 大模型通过 Responses API 的严格 JSON Schema 返回结果，并且只能使用动作白名单；最终状态仍由本地规则验证。
6. 艾达的姓名、住处、职责和面孔必须分别在冻结时间的暗房里由她本人核验；无论玩家点击选项还是自由输入，都必须逐一通过四个固定证据动作。

未配置大模型时，七名居民使用按职业与性格手写的本地对话规则，游戏流程完整可玩。

### Godot AI NPC v2

Godot 主版本现在使用独立上下文编译器，而不是把角色卡和世界状态直接拼进 Prompt。每轮只投影当前 NPC 有资格知道的规范事实、本轮共同证据、主观记忆、关系、场景模式和带 TTL/冷却字段的导演意图；角色写作规则与秘密知识也已拆开，身份未固定的艾达不会从角色卡偷看到姓名或职责。

大模型可以把自然语言理解为一个已满足硬前置条件的剧情动作提案，但不能直接改状态。返回动作会在当前世界快照上重新经过 `DialogueManager` 白名单验证，再由本地规则提交；等待模型期间如果循环、物品或证据发生变化，动作会被拒绝。生成后质量门会剥离无依据的“没听清”，补全玩家明确询问却被模型回避的高置信事实，并拒绝台词否认自己的引用。每轮还会生成事实/记忆引用 ID、分区 Token 估算、裁剪原因、`quality_guard` 与最近 64 轮本地 trace。

普通居民的对话和主观记忆只属于当前循环，白光重置时清空；玩家日志、已获得知识和按设计保留的照片继续跨循环。终端实验台现在也按当前循环硬过滤普通对话与主观记忆，并在不发送给模型的独立区显示上下文 trace；“保留记忆”开关仍只是回归实验能力，不代表正式游戏规则。

## 终端 AI NPC 状态实验台

不启动游戏也可以逐个测试 NPC。交互模式：

~~~powershell
python tools/npc_terminal.py
~~~

离线检查某个剧情阶段实际发送的上下文，不调用 OpenAI：

~~~powershell
python tools/npc_terminal.py --dry-run --npc dorothea --preset records
python tools/npc_terminal.py --dry-run --npc ada --preset darkroom --once "你记得自己的名字吗？"
~~~

终端中可用 /npc 选择七位 NPC，/preset 切换经过整理的剧情阶段，或用 /item、/evidence、/repair、/flag、/knowledge、/photo 和 /time 精确修改测试状态。/state 显示完整世界状态，/facts 对比每位 NPC 当前可知的事实，/context 显示下一轮将发送给模型的完整 JSON。输入 /help 可查看全部命令。

测试状态与 NPC 上下文是两层数据。背包、证据和机关旗标保留在本地状态中；每次对话前才按 NPC 重新投影为可见事实。例如背包加入 room7_tag 后，多萝西娅能看到“玩家带着七号房钥匙牌”，其他 NPC 不会收到玩家的完整背包。

NPC 动作进一步区分“玩家持有”“当面出示”“解释证据关系”和“NPC 承诺/执行”。只有世界前置条件与当前对话触发同时成立的动作才会进入发给模型的白名单；模型即使返回另一个动作，也会被本地规则降级为继续对话。不可逆动作各有固定证据链：阿瑟需要档案已鉴定的扳手、地下制动接口与当面核对，安全原理由他自行解释和承担；贝娅特丽斯需要终止记录、音叉和七次终止说明；康拉德需要镜片、路线记录、接收/落点与主航道安全说明；艾达的四个身份锚点必须逐项展示对应证据。弗洛伦斯每次只鉴定玩家实际放到桌上的一件工具，不会批量读取背包。

动作效果和固定剧情台词仍由本地规则执行，模型不能自行改写物品、证据或剧情旗标。

终端实验台中的成功在线对话会把最多八条记忆只写入当前 NPC，并自动保存到 tmp/npc-terminal-state.json。之后可用 --load-state 恢复；应用剧情预设默认保留各 NPC 自己的记忆，/reset all 才会清空。这是测试长对话一致性的显式实验模式；Godot 正式游戏会在白光重置时清除普通 NPC 记忆。

## 大模型配置

复制 `.env.example` 为 `.env`，填写服务端环境变量：

```env
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.6-luna
OPENAI_REASONING_EFFORT=low
```

浏览器不会读取 API Key。`server.py` 使用 OpenAI Responses API、`store: false` 和严格结构化输出，只向前端公开“是否配置、使用哪个模型”等非敏感状态。旧的 `LLM_*` 名称仍可兼容，但新部署建议统一使用 `OPENAI_*`。

## 剧情路线简表

表层终止路线：

```text
修复三座钟
  → 地下室读取三项外部协议
  → 康拉德确认灯塔→礼拜堂→广场光路
  → 阿瑟确认紧急接口并亲手停钟
  → 贝娅特丽斯用银音叉完成第七声
  → 拉下红色删除杆
  → 星期日到来，艾达的共同记录消失
```

七人继续路线：

```text
潮汐钟 → 02:00 退潮洞穴 → 旧底片 → 三步显影
主钟 A.R. 记录 + 钟楼 A.R. 记录 + 残缺肖像 → 恢复姓名/职责
七号钥匙牌 + 旅店登记簿缺口 → 恢复住处
停主钟抬起配重 + 双路光照西墙 + 无编号钥匙 → 第二暗房
与艾达逐一核验姓名 + 住处 + 职责 + 面孔 → 定影肖像
肖像放入地下室第七见证位 → 按下白色继续旋钮
```

## 目录

```text
mygame/
├─ data/world.json      角色、物品、证据与循环配置
├─ data/maps.json       公共场景、室内空间、地形、家具与交互点
├─ js/simulation.js     时间循环、知识/物品边界、NPC 行动与结局条件
├─ js/game.js           输入、移动、旅行、互动、存档和主循环
├─ js/renderer.js       摄像机、碰撞、角色动画与像素场景渲染
├─ js/ui.js             标题、日志、对话、谜题和重置/结局演出
├─ js/ai.js             浏览器侧 NPC 对话与本地回退
├─ art/runtime/         游戏实际加载的透明 WebP 与电影化全景
├─ tools/build_runtime_art.py  从 art 源素材重建运行时资产
├─ tools/npc_terminal.py  可编辑状态的终端 NPC 对话实验台
├─ server.py            静态服务器与可选同源 LLM 代理
└─ my_script.doc        原始剧情脚本
```

`my_script.doc` 是固定剧情源文件，本轮完善没有修改它。若替换或补充 `art` 下的同名源素材，可运行 `python tools/build_runtime_art.py` 重新生成运行时 WebP。
