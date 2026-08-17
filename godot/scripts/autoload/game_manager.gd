extends Node

const STATE_VERSION: int = 1

var state: Dictionary = {}
var started: bool = false


func _ready() -> void:
	if not DataManager.loaded:
		DataManager.load_all()


func new_game() -> Dictionary:
	state = create_initial_state()
	started = true
	EventBus.state_changed.emit(state)
	return state


func continue_game() -> Dictionary:
	var raw: Dictionary = SaveManager.load_game()
	if raw.is_empty():
		return new_game()
	state = normalize_loaded_state(raw)
	started = true
	EventBus.state_changed.emit(state)
	return state


func create_initial_state(persistent: Dictionary = {}) -> Dictionary:
	var npc_states: Dictionary = {}
	for npc_value: Variant in DataManager.world.get("npcs", []):
		var npc: Dictionary = npc_value as Dictionary
		var npc_id: String = str(npc.get("id", ""))
		npc_states[npc_id] = _initial_npc_state(npc)
	var initial: Dictionary = {
		"version": STATE_VERSION,
		"seed": int(persistent.get("seed", randi() & 0x7fffffff)),
		"rngState": int(persistent.get("rngState", 73129)),
		"mode": "player",
		"regionId": "town",
		"placeId": "player-room",
		"player": {"x": 384.0, "y": 370.0, "facing": "down", "present": true},
		"loopCount": int(persistent.get("loopCount", 0)),
		"loopElapsed": 0.0,
		"minute": TimeManager.LOOP_START_MINUTE,
		"dayLabel": "SATURDAY",
		"speed": 1.0,
		"weather": "晴",
		"flags": {"repair_orders_read": false},
		"repairs": {"master": false, "chapel": false, "tide": false},
		"inventory": {},
		"evidence": {},
		"knowledge": (persistent.get("knowledge", {}) as Dictionary).duplicate(true),
		"photos": (persistent.get("photos", {}) as Dictionary).duplicate(true),
		"journal": (persistent.get("journal", []) as Array).duplicate(true),
		# Ordinary resident dialogue is current-loop state. Only explicitly authored
		# exceptional characters may gain cross-loop memory in a future rule.
		"npcNotes": {},
		"npcs": npc_states,
		"conversationOpen": false,
		"cinematic": null,
		"endingId": null,
		"lastLocation": null,
	}
	var photos: Dictionary = initial["photos"] as Dictionary
	if bool(photos.get("unfinished_portrait", false)):
		(initial["inventory"] as Dictionary)["unfinished_portrait"] = 1
	if bool(photos.get("fixed_portrait", false)):
		(initial["inventory"] as Dictionary)["fixed_portrait"] = 1
	if (initial["npcs"] as Dictionary).has("ada"):
		((initial["npcs"] as Dictionary)["ada"] as Dictionary)["placeId"] = "erased-space"
	state = initial
	add_journal(
		"loop",
		"第 %d 次醒来。床边的钟仍是星期六 06:00。" % (int(initial["loopCount"]) + 1) if int(initial["loopCount"]) > 0 else "星期六 06:00，在湖畔旅店八号房醒来。",
		true
	)
	TimeManager.sync_world_flags(initial)
	TimeManager.sync_npc_schedules(initial)
	return initial


func normalize_loaded_state(raw: Dictionary) -> Dictionary:
	var base: Dictionary = create_initial_state(raw)
	base.merge(raw, true)
	var default_player: Dictionary = {"x": 384.0, "y": 370.0, "facing": "down", "present": true}
	default_player.merge(raw.get("player", {}) as Dictionary, true)
	base["player"] = default_player
	var repairs: Dictionary = {"master": false, "chapel": false, "tide": false}
	repairs.merge(raw.get("repairs", {}) as Dictionary, true)
	base["repairs"] = repairs
	for key: String in ["flags", "inventory", "evidence", "knowledge", "photos", "npcNotes"]:
		base[key] = (raw.get(key, {}) as Dictionary).duplicate(true)
	var normalized_npcs: Dictionary = base.get("npcs", {}) as Dictionary
	for npc_id: Variant in (raw.get("npcs", {}) as Dictionary).keys():
		var merged_npc: Dictionary = (normalized_npcs.get(npc_id, {}) as Dictionary).duplicate(true)
		merged_npc.merge((raw["npcs"] as Dictionary)[npc_id] as Dictionary, true)
		normalized_npcs[npc_id] = merged_npc
	base["npcs"] = normalized_npcs
	state = base
	TimeManager.sync_clock(state)
	TimeManager.sync_world_flags(state)
	TimeManager.sync_npc_schedules(state)
	return state


func _initial_npc_state(npc: Dictionary) -> Dictionary:
	var x: float = float(npc.get("x", 384.0))
	var y: float = float(npc.get("y", 280.0))
	return {
		"regionId": str(npc.get("regionId", "town")),
		"placeId": str(npc.get("placeId", npc.get("regionId", "town"))),
		"x": x,
		"y": y,
		"targetX": x,
		"targetY": y,
		"facing": "down",
		"relationshipLevel": "stranger",
		"evidenceLevel": "none",
		"memoryPressure": "stable",
		"actionState": "unavailable",
		"memories": [],
	}


func add_journal(type: String, text: String, persistent: bool = true) -> void:
	if state.is_empty() or text.is_empty():
		return
	var journal: Array = state.get("journal", []) as Array
	for index: int in range(maxi(0, journal.size() - 4), journal.size()):
		if str((journal[index] as Dictionary).get("text", "")) == text:
			return
	journal.append({
		"id": "%d:%d:%d" % [int(state.get("loopCount", 0)), int(state.get("loopElapsed", 0.0)), journal.size()],
		"loop": int(state.get("loopCount", 0)) + 1,
		"stamp": "%s %s" % [state.get("dayLabel", "SATURDAY"), TimeManager.format_time(int(state.get("minute", 360)))],
		"type": type,
		"text": text,
		"persistent": persistent,
	})
	if journal.size() > 180:
		journal = journal.slice(journal.size() - 180)
	state["journal"] = journal


func mark_repair(repair_id: String) -> bool:
	if repair_id not in ["master", "chapel", "tide"]:
		return false
	var repairs: Dictionary = state.get("repairs", {}) as Dictionary
	if bool(repairs.get(repair_id, false)):
		return false
	repairs[repair_id] = true
	state["repairs"] = repairs
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	flags["%s_repaired" % repair_id] = true
	state["flags"] = flags
	var names: Dictionary = {"master": "广场主钟", "chapel": "礼拜堂六声钟", "tide": "港口潮汐钟"}
	add_journal("repair", "%s恢复运转。它没有解决时间异常，却打开了一条新的调查路径。" % names[repair_id], true)
	TimeManager.sync_world_flags(state)
	EventBus.state_changed.emit(state)
	return true


func reset_loop() -> Dictionary:
	var persistent: Dictionary = KnowledgeManager.persistent_snapshot(state)
	persistent["seed"] = int(state.get("seed", 0))
	persistent["rngState"] = int(state.get("rngState", 73129))
	persistent["loopCount"] = int(state.get("loopCount", 0)) + 1
	state = create_initial_state(persistent)
	EventBus.loop_reset.emit(int(state.get("loopCount", 0)))
	EventBus.state_changed.emit(state)
	return state


func finish_ending(ending_id: String) -> void:
	if ending_id not in ["surface", "true"]:
		return
	state["endingId"] = ending_id
	add_journal(
		"ending",
		"七名见证人共同进入星期日；时间没有倒退，只是继续。" if ending_id == "true" else "六人终止协议完成；星期日到来，艾达的共同记录被永久删除。",
		true
	)
	SaveManager.record_ending(ending_id, int(state.get("loopCount", 0)) + 1)
	save(false)
	EventBus.ending_reached.emit(ending_id)


func save(notify: bool = false) -> bool:
	if state.is_empty():
		return false
	var ok: bool = SaveManager.save_game(state)
	if notify and ok:
		EventBus.state_changed.emit(state)
	return ok
