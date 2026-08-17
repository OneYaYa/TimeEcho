class_name TimeEchoMain
extends Node

@onready var world: TimeEchoWorldController = $WorldController
@onready var ui: TimeEchoUI = $GameUI

var interaction_service := InteractionService.new()
var flow := GameFlowStateMachine.new()
var ai_service: TimeEchoAIService
var current_npc_id: String = ""
var _ui_elapsed: float = 0.0
var _autosave_elapsed: float = 0.0
var _reset_started: bool = false
var _talk_pending: bool = false


func _ready() -> void:
	ai_service = TimeEchoAIService.new()
	ai_service.name = "AIService"
	add_child(ai_service)
	_connect_signals()
	if not DataManager.loaded:
		ui.show_title(false)
		ui.show_inspect("THE CLOCK FAILED TO START", "数据校验失败：\n%s" % "\n".join(DataManager.validation_errors))
		return
	ui.show_title(SaveManager.has_save())


func _process(delta: float) -> void:
	if not GameManager.started or GameManager.state.is_empty():
		return
	var state: Dictionary = GameManager.state
	var events: Array[Dictionary] = TimeManager.advance(state, delta)
	_handle_time_events(events)
	world.load_state(state)
	var allow_input: bool = flow.accepts_world_input() and not ui.is_blocking() and state.get("cinematic") in [null, ""] and state.get("endingId") in [null, ""]
	world.set_input_enabled(allow_input)
	_ui_elapsed += delta
	_autosave_elapsed += delta
	if _ui_elapsed >= 0.12:
		_ui_elapsed = 0.0
		var scene: Dictionary = DataManager.get_scene_data(str(state.get("placeId", "player-room")))
		ui.update_state(state, scene)
		ui.set_interaction(world.get_nearest_interaction() if allow_input else {})
	if _autosave_elapsed >= 15.0 and not _reset_started:
		_autosave_elapsed = 0.0
		GameManager.save(false)
	AudioManager.update_ambience(str(state.get("placeId", "town")), state, delta)


func _connect_signals() -> void:
	ui.new_game_requested.connect(_start_new_game)
	ui.continue_requested.connect(_continue_game)
	ui.save_requested.connect(_save_game)
	ui.prologue_completed.connect(_finish_prologue)
	ui.dialogue_action_requested.connect(_on_dialogue_action)
	ui.dialogue_text_requested.connect(_on_dialogue_text)
	ui.dialogue_closed.connect(_on_dialogue_closed)
	ui.modal_dismissed.connect(_on_modal_dismissed)
	ui.puzzle_completed.connect(_on_puzzle_completed)
	ui.restart_requested.connect(_restart_after_ending)
	ui.loop_cinematic_finished.connect(_finish_loop_reset)
	world.interaction_requested.connect(_on_interaction_requested)


func _start_new_game() -> void:
	var state: Dictionary = GameManager.new_game()
	state["cinematic"] = "prologue"
	flow.transition(GameFlowStateMachine.State.PROLOGUE)
	ui.show_game()
	world.load_state(state, true)
	ui.show_prologue()


func _continue_game() -> void:
	var state: Dictionary = GameManager.continue_game()
	ui.show_game()
	world.load_state(state, true)
	if state.get("endingId") not in [null, ""]:
		flow.transition(GameFlowStateMachine.State.ENDING)
		ui.show_ending(str(state["endingId"]))
	else:
		flow.transition(GameFlowStateMachine.State.PLAYING)
		ui.notify("已读取 LOOP %02d。" % (int(state.get("loopCount", 0)) + 1))


func _finish_prologue() -> void:
	GameManager.state["cinematic"] = null
	flow.transition(GameFlowStateMachine.State.PLAYING)
	GameManager.save(false)
	var scene: Dictionary = DataManager.get_scene_data(str(GameManager.state.get("placeId", "player-room")))
	ui.notify("%s · %s" % [scene.get("name", "湖畔旅店"), scene.get("subtitle", "")])


func _save_game() -> void:
	if GameManager.save(true):
		AudioManager.play("save")
		ui.notify("已保存当前循环。跨轮日志、照片与知识会保留；本轮实物会在白光后复位。")
	else:
		ui.notify("存档失败；请检查 user:// 写入权限。")


func _on_interaction_requested(target: Dictionary) -> void:
	if ui.is_blocking() or target.is_empty():
		return
	match str(target.get("type", "")):
		"npc":
			_open_conversation(target.get("value", {}) as Dictionary)
		"landmark":
			AudioManager.play("talk")
			var result: Dictionary = interaction_service.interact(target.get("value", {}) as Dictionary, GameManager.state)
			_dispatch_interaction_result(result)
			GameManager.save(false)
		"portal":
			_travel(target.get("value", {}) as Dictionary)


func _travel(portal: Dictionary) -> void:
	if str(portal.get("id", "")) == "enter_low_tide_cave" and not InventoryManager.has_item(GameManager.state, "flashlight"):
		ui.show_inspect("退潮洞口", "洞口已经露出，但里面没有自然光。康拉德也许有适合水下维护的照明工具。")
		return
	AudioManager.play("travel")
	var events: Array[Dictionary] = SceneManager.travel(GameManager.state, portal)
	world.load_state(GameManager.state, true)
	var scene: Dictionary = DataManager.get_scene_data(str(GameManager.state.get("placeId", "")))
	ui.notify("%s · %s" % [scene.get("name", ""), scene.get("subtitle", "")])
	_handle_time_events(events)
	GameManager.save(false)


func _dispatch_interaction_result(result: Dictionary) -> void:
	match str(result.get("kind", "inspect")):
		"inspect":
			ui.show_inspect(str(result.get("title", "现场记录")), str(result.get("text", "")))
		"journal":
			ui.show_journal(str(result.get("tab", "journal")))
		"rest":
			var events: Array[Dictionary] = TimeManager.advance_travel(GameManager.state, float(result.get("real_seconds", 15.0)))
			world.load_state(GameManager.state)
			ui.update_state(GameManager.state, DataManager.get_scene_data(str(GameManager.state.get("placeId", "player-room"))))
			ui.show_inspect(str(result.get("title", "休息")), str(result.get("text", "")))
			_handle_time_events(events)
			GameManager.save(false)
		"puzzle":
			flow.transition(GameFlowStateMachine.State.PUZZLE)
			ui.show_puzzle(str(result.get("puzzle", "")), GameManager.state)
		"ending":
			_reach_ending(str(result.get("ending", "surface")))


func _open_conversation(npc: Dictionary) -> void:
	current_npc_id = str(npc.get("id", ""))
	flow.transition(GameFlowStateMachine.State.DIALOGUE)
	GameManager.state["conversationOpen"] = true
	AudioManager.play("talk")
	ui.show_dialogue(npc, GameManager.state, DialogueManager.get_actions(current_npc_id, GameManager.state))
	EventBus.dialogue_opened.emit(current_npc_id)


func _on_dialogue_action(action_id: String) -> void:
	if current_npc_id.is_empty():
		return
	var result: Dictionary = DialogueManager.apply_action(current_npc_id, action_id, GameManager.state)
	var npc: Dictionary = DataManager.get_npc(current_npc_id)
	ui.append_dialogue(str(npc.get("name", "镇民")), str(result.get("text", "对方没有改变决定。")))
	_record_dialogue_turn(current_npc_id, "[%s]" % action_id, str(result.get("text", "")), action_id, str(result.get("text", "")))
	if not str(result.get("puzzle", "")).is_empty():
		GameManager.state["conversationOpen"] = false
		flow.transition(GameFlowStateMachine.State.PUZZLE)
		ui.show_puzzle(str(result["puzzle"]), GameManager.state)
		current_npc_id = ""
	else:
		ui.refresh_dialogue_actions(DialogueManager.get_actions(current_npc_id, GameManager.state))
	GameManager.save(false)


func _on_dialogue_text(message: String) -> void:
	if current_npc_id.is_empty() or _talk_pending:
		return
	_talk_pending = true
	var npc_id: String = current_npc_id
	var npc: Dictionary = DataManager.get_npc(npc_id)
	ui.append_dialogue("你", message, true)
	var result: Dictionary = await ai_service.talk(npc_id, message, GameManager.state)
	if current_npc_id != npc_id:
		_talk_pending = false
		return
	var reply: String = str(result.get("text", "湖边的风吞掉了这句话。"))
	ui.append_dialogue(str(npc.get("name", "镇民")), reply)
	ui.append_dialogue("SYSTEM", "%s · 剧情状态由本地规则验证" % result.get("provider", "local-rules"))
	_record_dialogue_turn(npc_id, message, reply, str(result.get("action", "continue_conversation")), str(result.get("memory", reply)))
	ui.refresh_dialogue_actions(DialogueManager.get_actions(npc_id, GameManager.state))
	if not str(result.get("puzzle", "")).is_empty():
		GameManager.state["conversationOpen"] = false
		flow.transition(GameFlowStateMachine.State.PUZZLE)
		ui.show_puzzle(str(result["puzzle"]), GameManager.state)
		current_npc_id = ""
	GameManager.save(false)
	_talk_pending = false


func _record_dialogue_turn(npc_id: String, player_text: String, reply: String, action: String, subjective_memory: String = "") -> void:
	var notes_by_npc: Dictionary = GameManager.state.get("npcNotes", {}) as Dictionary
	var notes: Array = notes_by_npc.get(npc_id, []) as Array
	var current_loop := int(GameManager.state.get("loopCount", 0)) + 1
	var event_id := "dialogue:%d:%s:%d" % [current_loop, npc_id, notes.size() + 1]
	notes.append({"event_id": event_id, "loop": current_loop, "player": player_text, "reply": reply, "action": action})
	if notes.size() > 16:
		notes = notes.slice(notes.size() - 16)
	notes_by_npc[npc_id] = notes
	GameManager.state["npcNotes"] = notes_by_npc
	var npcs: Dictionary = GameManager.state.get("npcs", {}) as Dictionary
	if npcs.has(npc_id):
		var npc_state: Dictionary = npcs[npc_id] as Dictionary
		var memories: Array = npc_state.get("memories", []) as Array
		var memory_text := subjective_memory.strip_edges().left(500)
		if memory_text.is_empty():
			memory_text = reply.left(500)
		memories.push_front({
			"memory_id": "memory:%s" % event_id,
			"event_ref": event_id,
			"subjective_text": memory_text,
			"salience": 0.8 if action != "continue_conversation" else 0.45,
			"valence": "tense" if action != "continue_conversation" else "neutral",
			"tier": "current_loop",
			"loop": current_loop,
		})
		npc_state["memories"] = memories.slice(0, mini(8, memories.size()))
		npcs[npc_id] = npc_state
		GameManager.state["npcs"] = npcs


func _on_dialogue_closed() -> void:
	if not current_npc_id.is_empty():
		EventBus.dialogue_closed.emit(current_npc_id)
	GameManager.state["conversationOpen"] = false
	current_npc_id = ""
	if GameManager.state.get("endingId") in [null, ""]:
		flow.transition(GameFlowStateMachine.State.PLAYING)
	GameManager.save(false)


func _on_modal_dismissed(kind: String) -> void:
	if kind == "puzzle" and GameManager.started and GameManager.state.get("endingId") in [null, ""]:
		GameManager.state["conversationOpen"] = false
		current_npc_id = ""
		flow.transition(GameFlowStateMachine.State.PLAYING)


func _on_puzzle_completed(puzzle_id: String) -> void:
	flow.transition(GameFlowStateMachine.State.PLAYING)
	var completed: bool = false
	match puzzle_id:
		"master": completed = GameManager.mark_repair("master")
		"chapel": completed = InventoryManager.has_item(GameManager.state, "chapel_pin") and GameManager.mark_repair("chapel")
		"tide": completed = GameManager.mark_repair("tide")
		"photo": completed = DialogueManager.complete_photo_development(GameManager.state)
		"identity": completed = DialogueManager.complete_identity_fixing(GameManager.state)
	if completed:
		AudioManager.play("event")
		ui.notify("机构发出一声干净的咬合声。")
		world.load_state(GameManager.state)
		GameManager.save(false)


func _handle_time_events(events: Array[Dictionary]) -> void:
	if _reset_started:
		return
	for event: Dictionary in events:
		if str(event.get("type", "")) == "reset-warning":
			_reset_started = true
			flow.transition(GameFlowStateMachine.State.RESETTING)
			GameManager.state["cinematic"] = "reset"
			GameManager.add_journal("loop", "05:55，湖面出现一条逆向升起的白线。镇民停住，影子全部转向湖心。", true)
			GameManager.save(false)
			ui.play_reset(int(GameManager.state.get("loopCount", 0)))
			return


func _finish_loop_reset() -> void:
	GameManager.reset_loop()
	GameManager.state["cinematic"] = null
	_reset_started = false
	flow.transition(GameFlowStateMachine.State.PLAYING)
	world.load_state(GameManager.state, true)
	ui.show_game()
	ui.notify("星期六 06:00 · 湖畔旅店八号房")
	GameManager.save(false)


func _reach_ending(ending_id: String) -> void:
	flow.transition(GameFlowStateMachine.State.ENDING)
	AudioManager.play("ending")
	GameManager.finish_ending(ending_id)
	ui.show_ending(ending_id)


func _restart_after_ending() -> void:
	GameManager.reset_loop()
	GameManager.state["endingId"] = null
	flow.transition(GameFlowStateMachine.State.PLAYING)
	ui.close_modal(false)
	ui.show_game()
	world.load_state(GameManager.state, true)
	GameManager.save(false)
