class_name TimeEchoContextCompiler
extends RefCounted


const TEMPLATE_VERSION := "time-echo-context-v2"
const MAX_DIALOGUE_ITEMS := 8
const MAX_MEMORY_ITEMS := 8
const MAX_BELIEF_ITEMS := 24


## Build one NPC's partial-observation view. Canonical state is projected into
## safe belief objects here; private flags and the player's full meta-knowledge
## never enter the request.
func compile(npc_id: String, player_message: String, state: Dictionary, eligible_actions: Array[Dictionary]) -> Dictionary:
	var npc: Dictionary = DataManager.get_npc(npc_id)
	var npc_state: Dictionary = _dictionary(_dictionary(state.get("npcs", {})).get(npc_id, {}))
	var flags: Dictionary = _dictionary(state.get("flags", {}))
	var current_loop := int(state.get("loopCount", 0)) + 1
	var profile := _compile_profile(npc_id, npc, flags, npc_state)
	var beliefs := _visible_beliefs(npc_id, npc, state)
	var recent_dialogue := _recent_dialogue(npc_id, state, current_loop)
	var memories := _current_loop_memories(npc_state, current_loop)
	var actions := _compile_actions(eligible_actions)
	var snapshot_version := int(state.get("loopCount", 0)) * 1440 + int(state.get("minute", 360))
	var turn_id := "loop:%d:npc:%s:turn:%d" % [current_loop, npc_id, recent_dialogue.size() + 1]
	var scene_mode := _scene_mode(npc_id, flags, state)
	var relationship := _relationship_state(npc_state)
	var director := _director_intent(actions, state)
	profile["persona_core"] = {
		"identity": "%s · %s" % [profile.get("name", "镇民"), profile.get("role", "")],
		"long_term_goal": profile.get("goal", ""),
		"default_strategy": profile.get("concern", ""),
		"voice": profile.get("voice", ""),
		"stable_boundaries": ["不把玩家跨轮记忆当作本轮证据", "不读取其他 NPC 的记忆", "不从物品名称推断隐藏地点"],
	}
	profile["active_scene_mode"] = scene_mode
	profile["knowledge"] = {
		"public": beliefs.map(func(item: Dictionary) -> String: return str(item.get("content", ""))),
		"residual": _array(_dictionary(npc.get("knowledge", {})).get("suggestive", [])).duplicate(true),
		"known_beliefs": beliefs,
	}
	profile["relationship_state"] = relationship
	profile["allowed_actions"] = actions

	var scene_data: Dictionary = DataManager.get_scene_data(str(state.get("placeId", "")))
	var world_state := {
		"day": str(state.get("dayLabel", "SATURDAY")),
		"minute": int(state.get("minute", 360)),
		"loop": current_loop,
		"snapshot_version": snapshot_version,
		"current_scene": {
			"place_id": str(state.get("placeId", "")),
			"place_name": str(scene_data.get("name", state.get("placeId", ""))),
			"npc_present": str(npc_state.get("placeId", "")) == str(state.get("placeId", "")),
			"world_time": "%s %s" % [state.get("dayLabel", "SATURDAY"), TimeManager.format_time(int(state.get("minute", 360)))],
		},
		"story_context": {"public": _array(DataManager.get_story_context().get("publicFacts", [])).duplicate(true)},
		"recent_dialogue": recent_dialogue,
		"director_intent": director,
		# World-changing flags are deliberately represented only through beliefs
		# and allowed_actions after NPC-specific access checks.
		"flags": {},
	}
	var request := {
		"npc_profile": profile,
		"world_state": world_state,
		"player_message": player_message.strip_edges().left(2000),
		"memories": memories,
	}
	var included_ids: Array[String] = []
	for belief: Dictionary in beliefs:
		included_ids.append(str(belief.get("belief_id", "")))
	for memory: Dictionary in memories:
		included_ids.append(str(memory.get("memory_id", "")))
	var raw_notes: Array = _array(_dictionary(state.get("npcNotes", {})).get(npc_id, []))
	var raw_memories: Array = _array(npc_state.get("memories", []))
	var dropped: Array[Dictionary] = []
	var old_note_count := maxi(0, raw_notes.size() - recent_dialogue.size())
	var old_memory_count := maxi(0, raw_memories.size() - memories.size())
	if old_note_count > 0:
		dropped.append({"partition": "recent_dialogue", "reason": "old_loop_or_quota", "count": old_note_count})
	if old_memory_count > 0:
		dropped.append({"partition": "memories", "reason": "old_loop_or_quota", "count": old_memory_count})
	var trace := {
		"trace_id": turn_id,
		"template_version": TEMPLATE_VERSION,
		"snapshot_version": snapshot_version,
		"included_ids": included_ids,
		"dropped": dropped,
		"partition_token_estimates": {
			"persona": _estimate_tokens(profile.get("persona_core", {})),
			"scene": _estimate_tokens(world_state.get("current_scene", {})),
			"beliefs": _estimate_tokens(beliefs),
			"memories": _estimate_tokens(memories),
			"recent_dialogue": _estimate_tokens(recent_dialogue),
			"director_intent": _estimate_tokens(director),
		},
		"hard_filters": ["npc_id", "current_loop", "npc_visible_facts", "hard_action_prerequisites"],
	}
	return {"request": request, "trace": trace}


func _compile_profile(npc_id: String, npc: Dictionary, flags: Dictionary, npc_state: Dictionary) -> Dictionary:
	var profile_id := npc_id
	var profile_name := str(npc.get("name", "镇民"))
	var profile_role := str(npc.get("role", ""))
	var profile_goal := str(npc.get("goal", ""))
	var profile_concern := str(npc.get("concern", ""))
	if npc_id == "ada" and not bool(flags.get("ada_name_anchored", false)):
		profile_id = "hidden_figure"
		profile_name = "暗房中的潜影"
		profile_role = "身份尚未固定的人形潜影"
	elif npc_id == "ada" and not bool(flags.get("ada_duty_anchored", false)):
		profile_id = "hidden_figure"
		profile_role = "身份仍在恢复的暗房潜影"
	if npc_id == "ada" and not bool(flags.get("ada_duty_anchored", false)):
		profile_goal = "弄清缺失的姓名、住处、职责和面孔，让外部证据逐项固定残缺记忆"
		profile_concern = "害怕所有人接受一个从未有过她的世界，但无法说明自己为何被删除"
	return {
		"id": profile_id,
		"name": profile_name,
		"role": profile_role,
		"goal": profile_goal,
		"traits": _array(npc.get("traits", [])).duplicate(true),
		# The source character card mixes prose style with plot preconditions.
		# Runtime context keeps only the behavioral voice layer; facts live in beliefs.
		"voice": _safe_voice(npc_id),
		"concern": profile_concern,
		"current_state": {
			"mood": str(npc_state.get("mood", "neutral")),
			"status": str(npc_state.get("status", "active")),
			"place_id": str(npc_state.get("placeId", "")),
			"activity": "试图辨认残缺记忆" if npc_id == "ada" and not bool(flags.get("ada_duty_anchored", false)) else str(npc_state.get("activity", "")),
		},
	}


func _visible_beliefs(npc_id: String, npc: Dictionary, state: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var public_facts: Array = _array(_dictionary(npc.get("knowledge", {})).get("public", []))
	for index: int in range(public_facts.size()):
		_add_belief(result, "npc:%s:public:%d" % [npc_id, index], str(public_facts[index]), "canonical_public", 1.0)
	var repairs: Dictionary = _dictionary(state.get("repairs", {}))
	var evidence: Dictionary = _dictionary(state.get("evidence", {}))
	var flags: Dictionary = _dictionary(state.get("flags", {}))
	var photos: Dictionary = _dictionary(state.get("photos", {}))
	var knowledge: Dictionary = _dictionary(state.get("knowledge", {}))
	match npc_id:
		"arthur":
			if bool(repairs.get("master", false)): _add_belief(result, "event:master_repaired", "主钟在本轮已经修复。", "current_loop_event", 1.0)
			if bool(evidence.get("master_ar_record", false)): _add_belief(result, "evidence:master_ar_record", "修复后的主钟留下 A.R. 签署的七次连续击发记录。", "shared_evidence", 1.0)
			if bool(evidence.get("brake_interface", false)): _add_belief(result, "evidence:brake_interface", "玩家本轮检查过地下室紧急制动接口。", "player_report", 0.75)
			if bool(flags.get("arthur_stops_clock", false)): _add_belief(result, "event:arthur_commitment", "阿瑟本轮已经核验接口与扳手，并承诺亲手停钟。", "current_loop_event", 1.0)
		"beatrice":
			if bool(repairs.get("chapel", false)): _add_belief(result, "event:chapel_repaired", "礼拜堂六锤在本轮已经修复。", "current_loop_event", 1.0)
			if bool(evidence.get("chapel_ar_log", false)): _add_belief(result, "evidence:chapel_ar_log", "礼拜堂安装记录由 A.R. 签署，并记录独立第七锤。", "shared_evidence", 1.0)
			if bool(flags.get("beatrice_rings_seventh", false)): _add_belief(result, "event:beatrice_commitment", "贝娅特丽斯本轮已经核验证据，并承诺亲手完成第七声。", "current_loop_event", 1.0)
		"conrad":
			if bool(repairs.get("tide", false)): _add_belief(result, "event:tide_repaired", "潮汐钟在本轮已经修复。", "current_loop_event", 1.0)
			if bool(flags.get("low_tide", false)): _add_belief(result, "state:low_tide", "现在正处于 SUNDAY 02:00–03:00 的最低潮窗口。", "current_world_state", 1.0)
			if bool(flags.get("lens_identified", false)): _add_belief(result, "event:lens_identified", "档案员已把玩家带来的双槽镜鉴定为灯塔备用镜。", "shared_evidence", 1.0)
			if _has_item(state, "flashlight"): _add_belief(result, "event:flashlight_transferred", "康拉德本轮已经把防水手电交给玩家。", "current_loop_event", 1.0)
			if bool(flags.get("light_route_inn_studio", false)): _add_belief(result, "event:darkroom_light_route", "康拉德本轮已经建立通往照相馆西墙的备用光路。", "current_loop_event", 1.0)
		"dorothea":
			_add_belief(result, "place:inn:no_unnumbered_door", "旅店里没有无编号的门：六号与八号之间只有一段没有门的空墙。", "direct_observation", 1.0)
			_add_belief(result, "belief:dorothea:key_unknown", "多萝西娅不知道无编号钥匙如今能打开哪里，不能据此猜测隐藏房间。", "knowledge_boundary", 1.0)
			if bool(evidence.get("ledger_gap", false)): _add_belief(result, "evidence:ledger_gap", "玩家本轮亲眼看过旅店登记簿缺失的第七行。", "shared_evidence", 1.0)
			if _has_item(state, "room7_tag"): _add_belief(result, "visible_item:room7_tag", "玩家本轮带着七号房铜钥匙牌，但持有不等于已经放到柜台上。", "visible_possession", 1.0)
			if bool(flags.get("room7_key_verified", false)): _add_belief(result, "event:room7_key_verified", "多萝西娅本轮已核验铜牌，并把无编号钥匙交给玩家。", "current_loop_event", 1.0)
		"elias":
			if _has_item(state, "cave_negative"): _add_belief(result, "visible_item:cave_negative", "玩家本轮带着退潮洞穴中的受潮底片；是否已放上工作台要看当前发言。", "visible_possession", 1.0)
			if bool(photos.get("unfinished_portrait", false)): _add_belief(result, "event:portrait_developed", "底片已按重影、反差、湖面反射三步显影成未完成肖像。", "current_loop_event", 1.0)
		"florence":
			if bool(evidence.get("master_ar_record", false)): _add_belief(result, "visible_evidence:master_ar_record", "玩家本轮带有主钟 A.R. 记录。", "visible_possession", 1.0)
			if bool(evidence.get("chapel_ar_log", false)): _add_belief(result, "visible_evidence:chapel_ar_log", "玩家本轮带有礼拜堂 A.R. 安装记录。", "visible_possession", 1.0)
			if bool(photos.get("unfinished_portrait", false)): _add_belief(result, "visible_item:unfinished_portrait", "玩家本轮带有已显影但身份未固定的肖像。", "visible_possession", 1.0)
			if bool(flags.get("ar_records_compared", false)): _add_belief(result, "event:ar_records_compared", "弗洛伦斯本轮已核验两份 A.R. 原件；它们仍缺影像证据才能补全姓名。", "current_loop_event", 1.0)
			if bool(knowledge.get("ada_identity", false)): _add_belief(result, "knowledge:ada_identity", "档案交叉核验已经恢复 Ada Rowan 的姓名与中央校准员职责。", "verified_knowledge", 1.0)
		"ada":
			var anchor_names: Array[String] = []
			for entry: Array in [["ada_name_anchored", "姓名"], ["ada_residence_anchored", "住处"], ["ada_duty_anchored", "职责"], ["ada_face_anchored", "面孔"]]:
				if bool(flags.get(str(entry[0]), false)): anchor_names.append(str(entry[1]))
			_add_belief(result, "state:ada_anchors", "当前已经共同核验的身份锚点：%s。" % ("无" if anchor_names.is_empty() else "、".join(anchor_names)), "current_world_state", 1.0)
			if bool(flags.get("ada_name_anchored", false)):
				_add_belief(result, "identity:ada_name", "两份独立 A.R. 记录与残缺肖像已经共同确认她的姓名是 Ada Rowan。", "shared_evidence", 1.0)
			elif bool(knowledge.get("ada_identity", false)):
				_add_belief(result, "claim:unanchored_ada_name", "玩家持有档案恢复的姓名结论，但尚未与当前潜影共同核验；她不能据此自报姓名。", "unverified_for_self", 0.5)
	return result.slice(0, mini(MAX_BELIEF_ITEMS, result.size()))


func _add_belief(output: Array[Dictionary], belief_id: String, content: String, source: String, confidence: float) -> void:
	output.append({
		"belief_id": belief_id,
		"content": content.left(300),
		"truth_status": "known" if confidence >= 1.0 else "uncertain",
		"confidence": clampf(confidence, 0.0, 1.0),
		"source": source,
	})


func _compile_actions(source: Array[Dictionary]) -> Array[Dictionary]:
	var result: Array[Dictionary] = [{
		"id": "continue_conversation",
		"label": "只继续对话，不改变世界状态",
		"instruction": "玩家没有明确请求当前动作时选择此项。",
	}]
	var seen: Dictionary = {"continue_conversation": true}
	for action: Dictionary in source:
		var action_id := str(action.get("id", "")).strip_edges()
		if action_id.is_empty() or seen.has(action_id):
			continue
		seen[action_id] = true
		result.append({
			"id": action_id.left(120),
			"label": str(action.get("label", action_id)).left(160),
			"instruction": "只有玩家当前发言明确请求、出示或确认这项行为时才可选择。",
		})
	return result.slice(0, mini(30, result.size()))


func _recent_dialogue(npc_id: String, state: Dictionary, current_loop: int) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var notes: Array = _array(_dictionary(state.get("npcNotes", {})).get(npc_id, []))
	for value: Variant in notes:
		if not value is Dictionary:
			continue
		var entry: Dictionary = value as Dictionary
		if int(entry.get("loop", current_loop)) != current_loop:
			continue
		result.append({
			"event_id": str(entry.get("event_id", "dialogue:%s:%d" % [npc_id, result.size()])),
			"player": str(entry.get("player", "")).left(400),
			"reply": str(entry.get("reply", "")).left(600),
			"action": str(entry.get("action", "continue_conversation")).left(120),
		})
	return result.slice(maxi(0, result.size() - MAX_DIALOGUE_ITEMS))


func _current_loop_memories(npc_state: Dictionary, current_loop: int) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for value: Variant in _array(npc_state.get("memories", [])):
		if not value is Dictionary:
			continue
		var entry: Dictionary = value as Dictionary
		if int(entry.get("loop", current_loop)) != current_loop:
			continue
		var subjective := str(entry.get("subjective_text", entry.get("text", ""))).strip_edges().left(500)
		if subjective.is_empty():
			continue
		result.append({
			"memory_id": str(entry.get("memory_id", "memory:%d" % result.size())).left(120),
			"subjective_text": subjective,
			"event_ref": str(entry.get("event_ref", "")).left(120),
			"salience": clampf(float(entry.get("salience", entry.get("importance", 1))) / (10.0 if float(entry.get("importance", 1)) > 1.0 else 1.0), 0.0, 1.0),
			"valence": str(entry.get("valence", "neutral")).left(30),
			"tier": "current_loop",
			"truth_status": "subjective_recollection",
			"source": "dialogue_event",
		})
	return result.slice(0, mini(MAX_MEMORY_ITEMS, result.size()))


func _relationship_state(npc_state: Dictionary) -> Dictionary:
	var level := str(npc_state.get("relationshipLevel", "stranger"))
	var trust_by_level := {"hostile": 15, "wary": 35, "stranger": 50, "familiar": 65, "trusted": 80}
	return {
		"level": level,
		"trust": int(trust_by_level.get(level, 50)),
		"fear": 20 if str(npc_state.get("memoryPressure", "stable")) == "stable" else 55,
		"debt": 0,
		"source": "authoritative_relationship_projection",
	}


func _scene_mode(npc_id: String, flags: Dictionary, state: Dictionary) -> Dictionary:
	if int(state.get("minute", 360)) >= 1435:
		return {"id": "reset_imminent", "trigger": "reset_warning", "energy": "urgent", "behavior_rules": ["短句", "只说此刻已知事实", "不剧透结局"]}
	if npc_id == "ada" and not bool(flags.get("ada_duty_anchored", false)):
		return {"id": "identity_fragment", "trigger": "identity_not_anchored", "energy": "fading", "behavior_rules": ["只使用已锚定身份片段", "句子可有停顿", "玩家说出答案不能代替证据"]}
	return {"id": "working_resident", "trigger": "default", "energy": "grounded", "behavior_rules": ["先回答实际问题", "使用职业词汇但不口号化", "不在每句结尾追加建议"]}


func _safe_voice(npc_id: String) -> String:
	var voices := {
		"arthur": "句子完整、克制、用词精确；谈操作时区分记录、许可和责任，普通交谈直接回答。",
		"beatrice": "庄重但口语自然；只在不可逆后果上用一次简短钟声比喻，不连续反问。",
		"conrad": "务实寡言，以风、潮、航路和实际风险判断；能一句说清就不补第二句。",
		"dorothea": "温和周到，初次招呼后直接承接当前话题；触及记忆缺口时会短暂停顿。",
		"elias": "谈影像时准确使用曝光、银盐、反差和重影等术语；其他话题保持简洁。",
		"florence": "严谨耐心；需要判断来源时才区分原件、抄本、推断和结论。",
		"ada": "身份未固定时句子短、有停顿，只用已恢复的具体片段；逐步固定后恢复平静日常表达。",
	}
	return str(voices.get(npc_id, "像当地正在工作的人一样直接、具体地说话。"))


func _director_intent(actions: Array[Dictionary], state: Dictionary) -> Dictionary:
	var urgency := "foreshadow"
	var priority := 20
	var goal := "回应当前话题；不知道时明确不知道，不主动重复线索。"
	if int(state.get("minute", 360)) >= 1435:
		urgency = "emergency"
		priority = 100
		goal = "承认白光临近带来的当下变化，但不替玩家选择结局。"
	elif actions.size() > 1:
		urgency = "guidance"
		priority = 50
		goal = "若玩家当前发言明确请求已开放的证据动作，可提出该动作；否则继续对话。"
	return {
		"goal": goal,
		"urgency": urgency,
		"priority": priority,
		"preconditions": ["npc_present", "current_loop"],
		"forbidden_moves": ["泄露未获得线索", "替玩家决定结局", "把持有说成已经出示"],
		"ttl_turns": 1,
		"max_mentions": 1,
		"cooldown_turns": 2,
	}


func _has_item(state: Dictionary, item_id: String) -> bool:
	return int(_dictionary(state.get("inventory", {})).get(item_id, 0)) > 0


func _estimate_tokens(value: Variant) -> int:
	return ceili(float(JSON.stringify(value).length()) / 3.0)


func _dictionary(value: Variant) -> Dictionary:
	return value as Dictionary if value is Dictionary else {}


func _array(value: Variant) -> Array:
	return value as Array if value is Array else []
