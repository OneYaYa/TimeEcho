# TIME ECHO Godot 4.6 测试清单

标记说明：`[x]` 表示已由静态检查、Godot 4.6.3 项目内测试或 headless 启动覆盖；`[ ]` 表示仍需人工操作、听感检查或目标平台验证。本机实际程序位于桌面同名目录内。

## 自动检查

- [x] `project.godot` 存在且 `main_scene` 指向 `res://scenes/main/main.tscn`
- [x] 全部静态 `res://` 引用目标存在
- [x] `world.json`、`maps.json` 可按 UTF-8 JSON 解析
- [x] 7 个 NPC 稳定 ID 完整
- [x] 18 个地点稳定 ID 完整
- [x] 全部 portal 目标存在并有 spawn
- [x] 关键隐藏入口保留 revealFlag
- [x] InputMap 含 move/interact/cancel/journal/inventory/pause
- [x] 玩家、Ada、远景关键贴图存在
- [x] 静态验证脚本无第三方依赖
- [x] 原仓库 Python 契约测试 45/45 通过
- [x] Godot 4.6.3 `--headless --path godot --editor --quit` 无 Parser Error
- [x] Godot 4.6.3 `--headless --path godot --quit-after 10` 主场景运行无 Invalid access
- [x] Godot 4.6.3 项目内 `res://tests/test_runner.tscn` 测试通过
- [x] Godot Movie Writer 以真实 OpenGL 驱动输出 1152×648 广场画面，退出码 0
- [x] 18 个 JSON 地点全部以真实 OpenGL 渲染并输出原分辨率 PNG，0 失败

## 启动和标题

- [x] 主场景实例化后包含可绘制 WorldView、UIRoot/TitleScreen，标题远景可加载
- [ ] 无存档时 Continue 隐藏
- [ ] Begin 打开序章，确认后进入八号房
- [ ] 保存后重启，Continue 能恢复状态
- [ ] Loop Archive 显示已经获得的结局

## 输入

- [x] 工程注册 WASD、方向键、E、Space、J、I/B、Esc、P、Shift
- [ ] WASD 与方向键都能移动
- [ ] Shift 奔跑速度明显高于行走
- [ ] E 与 Space 都能交互
- [ ] 鼠标点击 NPC、landmark 和 portal 可交互
- [ ] UI 输入框聚焦时不会移动玩家
- [ ] Esc/P 暂停和返回，J 打开日志，I/B 打开背包

## 移动、场景和碰撞

- [x] CharacterBody2D 使用原 96/164 px/s 速度
- [x] JSON 建筑、家具、实心 zone、显式 collision landmark 生成 StaticBody2D
- [ ] 玩家不能穿过建筑、池塘、悬崖和实体机构
- [ ] 摄像机在大地图跟随并受地图边界限制
- [ ] 从八号房到走廊、大堂、前庭、广场可连续旅行
- [ ] 广场可分别到礼拜堂、照相馆/档案馆、港口、主钟舱
- [ ] travelSeconds 正确推进游戏时间

## NPC 和对话

- [x] 7 名 NPC 数据均建立索引
- [x] 固定选项只在本轮物品/证据/知识条件满足时出现
- [x] 自由文本剧情动作经过本地白名单和门槛
- [x] AI 上下文按 NPC、当前循环、可见事实与动作前置条件硬过滤
- [x] 模型动作在提交时重新经过当前白名单校验
- [x] 未锚定的 Ada 角色卡不包含姓名、中央校准员或第七见证人信息
- [ ] 至少与多萝西娅完成一次固定对话
- [ ] 自由输入能得到本地回复
- [ ] 对话期间时间为正常速度的 1/4
- [ ] NPC 按白天工作地点与晚间二楼日程切换
- [ ] Ada 未解锁前不渲染，暗房打开后才出现
- [ ] 未配置 AI 时完整流程仍可通关
- [ ] 配置兼容服务端时在线回复可用，断网会回退本地规则

## 三钟与谜题

- [x] 主钟答案保持“中、大、小 + 三条红线朝上”
- [x] 礼拜堂需要长椅下的第四擒纵销
- [x] 潮汐答案保持“低、中、高”
- [x] 底片显影保持“重影 → 反差 → 反射”
- [x] 身份定影需要姓名/住处/职责/面孔四个独立锚点
- [ ] 完成主钟谜题后主钟状态与控制台记录更新
- [ ] 完成礼拜堂谜题后可读取 A.R. 安装记录和七号牌
- [ ] 完成潮汐谜题后康拉德交出手电

## 时间与循环重置

- [x] 1 现实秒对应 2 游戏分钟
- [x] 循环起点为星期六 06:00，05:55 触发重置警告
- [x] 退潮洞穴和隐藏暗房停止时间
- [ ] HUD 日/时正确跨越星期日
- [ ] 星期日 02:00–03:00 洞穴入口出现，窗口外隐藏
- [ ] 05:55 白光演出播放并复位到八号房
- [ ] 维修、承诺、普通物品和本轮证据重置
- [x] 玩家日志、知识和照片保留；普通 NPC 对话与主观记忆清空

## 道具、证据和知识锁

- [x] 9 个静态物品和运行时 `chapel_pin` 兼容 ID 保留
- [x] 6 份证据保留稳定 ID
- [x] 档案工具卡不会自动扫描背包
- [x] NPC 当面核验后才写入关键知识/承诺
- [ ] 登记缺口 + 七号牌能让多萝西娅交出无编号钥匙
- [ ] 弗洛伦斯逐件鉴定扳手、音叉、镜片、手电
- [ ] 两份 A.R. 记录不足以恢复姓名，加入肖像后才可恢复
- [ ] 背包、证据、日志 UI 名称和说明正确

## 隐藏路线和结局

- [x] 地下室需三钟全部修复
- [x] 暗房需升起配重、备用光路和无编号钥匙
- [x] 红杆结局需三名 NPC 的亲自承诺
- [x] 白色旋钮需定影肖像安装到第七见证位
- [ ] 阿瑟核验接口与扳手后升起配重
- [ ] 康拉德可在表层/暗房两条光路之间切换
- [ ] Ada 四锚点逐项确认并完成定影
- [ ] 红杆触发表层结局
- [ ] 肖像安装后红杆断电，白钮触发真结局

## 音频、视觉和 UI

- [x] 原 46 个运行时图片已复制并保持稳定引用
- [x] `art/` 的 147 张图片已完整镜像，旧 `.import` 未混入
- [x] 草地、水面、石路、木地板纹理可由 Godot 4.6.3 导入为 Texture2D
- [x] 项目默认 nearest filtering
- [x] 原 Web Audio 改为 AudioStreamGenerator 程序合成
- [x] Windows/OpenGL 实拍中地图、玩家、钟楼、道具和交互轮廓正常显示
- [x] Windows 实拍中 HUD/日志中文字体正常，无方框或乱码
- [ ] 脚步、交互、钟、保存、重置、结局音效可听
- [ ] 声音开关即时生效并保持 UI 状态
- [ ] HUD、右侧日志、模态框在 1152×648 基准分辨率不重叠
- [ ] 窗口缩放后 Anchor/Container 布局仍可用

## 存档

- [x] 存档路径为 `user://` 而非 `res://`
- [x] 状态带 `version: 1` 并有迁移入口
- [x] 结局档案最多保留 12 条
- [ ] 保存后地点、坐标、时间、物品、证据和 NPC 笔记恢复
- [ ] 损坏存档输出错误并安全回到新游戏
- [ ] Windows、macOS、Linux 的 user:// 写入均正常

## Web 导出

- [x] 使用类型化 GDScript，无 C# 和第三方 Godot 插件
- [x] 渲染器配置为 `gl_compatibility`
- [x] WebAIProvider 使用 JavaScriptBridge 可选钩子
- [x] HTTPProvider 不含 API Key
- [ ] Godot 4.6 Web 模板导出成功
- [ ] HTTP(S) 托管后可启动、读 JSON、保存 IndexedDB-backed user://
- [ ] 同源 `/api/npc/decide` 可用
- [ ] 未配置服务时离线回退可用
