extends Node


func get_actions(npc_id: String, state: Dictionary) -> Array[Dictionary]:
	var actions: Array[Dictionary] = [{"id": "ask_work", "label": "问对方今天在做什么"}]
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	var repairs: Dictionary = state.get("repairs", {}) as Dictionary
	var photos: Dictionary = state.get("photos", {}) as Dictionary
	if npc_id == "ada":
		var records_ready: bool = KnowledgeManager.knows(state, "ada_identity") and KnowledgeManager.has_evidence(state, "master_ar_record") and KnowledgeManager.has_evidence(state, "chapel_ar_log")
		if records_ready and not bool(flags.get("ada_name_anchored", false)):
			actions.append({"id": "anchor_ada_name", "label": "用两份 A.R. 记录确认她的姓名"})
		if KnowledgeManager.knows(state, "ada_residence_anchor") and InventoryManager.has_item(state, "unnumbered_key") and not bool(flags.get("ada_residence_anchored", false)):
			actions.append({"id": "anchor_ada_residence", "label": "用七号房钥匙确认她的住处"})
		if records_ready and not bool(flags.get("ada_duty_anchored", false)):
			actions.append({"id": "anchor_ada_duty", "label": "用中央校准记录确认她的职责"})
		if KnowledgeManager.knows(state, "portrait_face_anchor") and InventoryManager.has_item(state, "unfinished_portrait") and not bool(flags.get("ada_face_anchored", false)):
			actions.append({"id": "anchor_ada_face", "label": "让她认领底片中的面孔"})
		actions.append({"id": "ask_ada_truth", "label": "问她为什么需要第七位见证人"})
		return actions
	match npc_id:
		"dorothea":
			actions.append({"id": "ask_rooms", "label": "问登记簿为什么跳过七号房"})
			if InventoryManager.has_item(state, "room7_tag") and KnowledgeManager.has_evidence(state, "ledger_gap") and not InventoryManager.has_item(state, "unnumbered_key"):
				actions.append({"id": "exchange_room7_key", "label": "把七号房钥匙牌放在柜台上"})
		"arthur":
			if bool(repairs.get("master", false)) and not KnowledgeManager.has_evidence(state, "master_ar_record"):
				actions.append({"id": "ask_master_record", "label": "请他解释七信号控制台"})
			if bool(repairs.get("master", false)) and KnowledgeManager.has_evidence(state, "brake_interface") and bool(flags.get("wrench_identified", false)) and InventoryManager.has_item(state, "installation_wrench") and not bool(flags.get("arthur_stops_clock", false)):
				actions.append({"id": "commit_stop_clock", "label": "出示制动接口与已鉴定扳手，请他亲手停钟"})
		"beatrice":
			if bool(repairs.get("chapel", false)):
				actions.append({"id": "ask_six_bells", "label": "问第七锤为何独立存在"})
			if bool(repairs.get("chapel", false)) and KnowledgeManager.has_evidence(state, "master_ar_record") and bool(flags.get("fork_identified", false)) and InventoryManager.has_item(state, "silver_tuning_fork") and not bool(flags.get("beatrice_rings_seventh", false)):
				actions.append({"id": "commit_seventh_bell", "label": "出示记录和音叉，请她执行第七声"})
		"conrad":
			if bool(repairs.get("tide", false)) and not InventoryManager.has_item(state, "flashlight"):
				actions.append({"id": "receive_flashlight", "label": "询问最低潮时露出的维护洞穴"})
			if bool(flags.get("lens_identified", false)) and KnowledgeManager.has_evidence(state, "chapel_ar_log") and InventoryManager.has_item(state, "spare_lens"):
				if not bool(flags.get("light_route_chapel_square", false)):
					actions.append({"id": "route_surface_light", "label": "请他建立礼拜堂到广场的维修副光"})
				if KnowledgeManager.has_evidence(state, "inn_roof_reflector") and not bool(flags.get("light_route_inn_studio", false)):
					actions.append({"id": "route_darkroom_light", "label": "请他把备用光导向照相馆西墙"})
		"elias":
			if InventoryManager.has_item(state, "cave_negative") and not bool(photos.get("unfinished_portrait", false)):
				actions.append({"id": "develop_cave_negative", "label": "请他显影洞穴底片"})
		"florence":
			var tools: Array = [
				["identify_wrench", "installation_wrench", "wrench_identified", "鉴定安装扳手"],
				["identify_fork", "silver_tuning_fork", "fork_identified", "鉴定银色音叉"],
				["identify_lens", "spare_lens", "lens_identified", "鉴定双槽备用镜片"],
				["identify_flashlight", "flashlight", "flashlight_identified", "鉴定防水手电"],
			]
			for entry: Array in tools:
				if InventoryManager.has_item(state, str(entry[1])) and not bool(flags.get(str(entry[2]), false)):
					actions.append({"id": entry[0], "label": entry[3]})
			if KnowledgeManager.has_evidence(state, "master_ar_record") and KnowledgeManager.has_evidence(state, "chapel_ar_log") and not bool(flags.get("ar_records_compared", false)) and not KnowledgeManager.knows(state, "ada_identity"):
				actions.append({"id": "compare_ar_records", "label": "核验两份 A.R. 原件"})
			if KnowledgeManager.has_evidence(state, "master_ar_record") and KnowledgeManager.has_evidence(state, "chapel_ar_log") and bool(photos.get("unfinished_portrait", false)) and not KnowledgeManager.knows(state, "ada_identity"):
				actions.append({"id": "cross_reference_ada", "label": "并排核验记录与残缺肖像"})
			if not KnowledgeManager.has_evidence(state, "inn_roof_reflector") or not KnowledgeManager.knows(state, "return_exposure"):
				actions.append({"id": "research_return_exposure", "label": "查找回返曝光和旅店屋顶光路"})
	return actions


func is_action_available(npc_id: String, action_id: String, state: Dictionary) -> bool:
	for action: Dictionary in get_actions(npc_id, state):
		if str(action.get("id", "")) == action_id:
			return true
	return false


func apply_action(npc_id: String, action_id: String, state: Dictionary) -> Dictionary:
	var response: Dictionary = {"speaker": npc_id, "text": "对方没有改变决定。", "puzzle": ""}
	# Re-evaluate the authoritative whitelist at commit time. This closes races
	# caused by loop reset, time advance, inventory changes, or delayed AI replies.
	if not is_action_available(npc_id, action_id, state):
		response["text"] = "眼前的条件已经对不上了；这一步没有发生。"
		response["rejected"] = true
		return response
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	var repairs: Dictionary = state.get("repairs", {}) as Dictionary
	if action_id == "ask_work":
		var lines: Dictionary = {
			"arthur": "母钟里有三枚错位齿轮。三条红色维修标记全部朝上才算修复；三座钟恢复后，地下旧校准入口才会解锁。",
			"beatrice": "礼钟本应有六声。第四枚擒纵销不见了，而第七锤仍锁在钟楼。",
			"conrad": "先读三根系船柱的水线，再调潮汐盘。别拿猜测和湖面赌博。",
			"dorothea": "早餐在炉边。三份维修单都送到了八号房——是的，一直都是八号房。",
			"elias": "我只相信能重复显影的东西。带来底片，我会检查重影、反差和反射。",
			"florence": "一份记录只能证明它自己存在。恢复被删掉的名字，至少需要两个独立来源和影像证据。",
			"ada": "我记得自己在这里工作过，也记得母钟、礼拜堂和灯塔，但职位与具体职责都断开了。",
		}
		response["text"] = str(lines.get(npc_id, "对方正在完成日常工作。"))
	elif npc_id == "dorothea" and action_id == "ask_rooms":
		response["text"] = "我看见登记簿的缺口了。若真有七号房，请拿一件属于那间房的东西给我。" if KnowledgeManager.has_evidence(state, "ledger_gap") else "登记簿就在柜台上。请先亲眼看看那一页。"
	elif npc_id == "dorothea" and action_id == "exchange_room7_key" and InventoryManager.has_item(state, "room7_tag") and KnowledgeManager.has_evidence(state, "ledger_gap"):
		InventoryManager.add_item(state, "unnumbered_key")
		flags["room7_key_verified"] = true
		KnowledgeManager.learn(state, "ada_residence_anchor", "七号钥匙牌、缺失登记行与无编号钥匙共同证明：被删除的人住在七号房。")
		response["text"] = "这块铜牌的磨损……我记得每天擦过它。柜台后的钥匙不是‘没有房间’，是我们把号码忘了。你拿去吧。"
	elif npc_id == "arthur" and action_id == "ask_master_record" and bool(repairs.get("master", false)):
		KnowledgeManager.add_evidence(state, "master_ar_record", "主钟控制台显示：A.R.，七次连续击发确认终止。")
		response["text"] = "记录写着：A.R.，七次连续击发确认终止。它证明七声是机械终止信号，但不能单独确认 A.R. 是谁。"
	elif npc_id == "arthur" and action_id == "commit_stop_clock" and KnowledgeManager.has_evidence(state, "brake_interface") and bool(flags.get("wrench_identified", false)) and InventoryManager.has_item(state, "installation_wrench"):
		flags["arthur_stops_clock"] = true
		flags["counterweight_raised"] = true
		GameManager.add_journal("commitment", "阿瑟确认紧急制动接口并承诺亲手停钟；西侧配重随之升起。", true)
		response["text"] = "接口、档案型号和扳手都对得上。它会断开主擒纵，不是锁死主轮。安全操作由我负责；到时候由我停钟。"
	elif npc_id == "beatrice" and action_id == "ask_six_bells":
		response["text"] = "六声用于日常报时。第七锤不参与普通报时；旧规只把它当作送终禁忌，我没有证据证明它真正用于什么。"
	elif npc_id == "beatrice" and action_id == "commit_seventh_bell" and KnowledgeManager.has_evidence(state, "master_ar_record") and bool(flags.get("fork_identified", false)):
		flags["beatrice_rings_seventh"] = true
		GameManager.add_journal("commitment", "贝娅特丽斯核验终止记录与银音叉，答应在协议启动时敲响第七声。", true)
		response["text"] = "终止记录与校准器相符。我会亲手完成第七声，确保没有别人替我承担这项不可逆的决定。"
	elif npc_id == "conrad" and action_id == "receive_flashlight" and bool(repairs.get("tide", false)):
		InventoryManager.add_item(state, "flashlight")
		KnowledgeManager.learn(state, "low_tide_cave_known", "潮汐钟修复后，康拉德确认星期日 02:00–03:00 会露出维护洞穴，并交出防水手电。")
		response["text"] = "02:00 到 03:00，灯塔脚下会露出旧维护洞。带上这支手电，潮回来前别在入口磨蹭。"
	elif npc_id == "conrad" and action_id == "route_surface_light" and bool(flags.get("lens_identified", false)) and KnowledgeManager.has_evidence(state, "chapel_ar_log"):
		flags["light_route_chapel_square"] = true
		flags["light_route_inn_studio"] = false
		flags["conrad_routes_light"] = true
		GameManager.add_journal("commitment", "康拉德按 A.R. 安装记录建立灯塔→礼拜堂→广场光路。", true)
		response["text"] = "记录、镜片和视线都吻合。主航道光保持不变；维修副光会经过礼拜堂反射器，再落到广场。"
	elif npc_id == "conrad" and action_id == "route_darkroom_light" and bool(flags.get("lens_identified", false)) and KnowledgeManager.has_evidence(state, "inn_roof_reflector"):
		flags["light_route_inn_studio"] = true
		flags["light_route_chapel_square"] = false
		flags["conrad_routes_light"] = false
		GameManager.add_journal("commitment", "康拉德用双槽镜建立灯塔→旅店屋顶→照相馆西墙的备用光路。", true)
		response["text"] = "主光不动，维修副光经过旅店屋顶落到照相馆西墙。我现在把镜片锁进副槽。"
	elif npc_id == "elias" and action_id == "develop_cave_negative" and InventoryManager.has_item(state, "cave_negative"):
		response["puzzle"] = "photo"
		response["text"] = "可以显影。先查重影，再拉反差，最后确认湖面反射；顺序错了，乳剂只会变成你想看见的样子。"
	elif npc_id == "florence" and action_id.begins_with("identify_"):
		var tool_actions: Dictionary = {
			"identify_wrench": ["installation_wrench", "wrench_identified", "安装扳手：母钟原设计的紧急制动扳手，可安全断开主擒纵。"],
			"identify_fork": ["silver_tuning_fork", "fork_identified", "银色音叉：第七锤的专用校准器。"],
			"identify_lens": ["spare_lens", "lens_identified", "双槽备用镜片：灯塔的双路维护镜，可分离维修副光。"],
			"identify_flashlight": ["flashlight", "flashlight_identified", "防水手电：普通洞穴照明工具，没有协议用途。"],
		}
		var entry: Array = tool_actions.get(action_id, []) as Array
		if entry.size() == 3 and InventoryManager.has_item(state, str(entry[0])):
			flags[str(entry[1])] = true
			KnowledgeManager.learn(state, str(entry[1]), str(entry[2]))
			response["text"] = str(entry[2])
	elif npc_id == "florence" and action_id == "compare_ar_records" and KnowledgeManager.has_evidence(state, "master_ar_record") and KnowledgeManager.has_evidence(state, "chapel_ar_log"):
		flags["ar_records_compared"] = true
		GameManager.add_journal("evidence", "弗洛伦斯核验两份本轮 A.R. 原件：来源独立、签署者相同，但仍缺影像证据。", true)
		response["text"] = "两份都是本轮原件，来源彼此独立，签名栏都是 A.R.；还不足以补全姓名，交叉核验台仍缺影像证据。"
	elif npc_id == "florence" and action_id == "cross_reference_ada" and bool((state.get("photos", {}) as Dictionary).get("unfinished_portrait", false)):
		flags["ar_records_compared"] = true
		KnowledgeManager.learn(state, "ada_identity", "两份 A.R. 维修记录与残缺肖像交叉核验：Ada Rowan，中央校准员，第七见证人。")
		response["text"] = "两个独立地点都由 A.R. 签字，肖像背面的字母位置一致。旧雇员索引补全为 Ada Rowan——中央校准员，第七席。"
	elif npc_id == "florence" and action_id == "research_return_exposure":
		KnowledgeManager.add_evidence(state, "inn_roof_reflector", "档案图纸证明旅店屋顶反射器可把备用光导向照相馆西墙。")
		KnowledgeManager.learn(state, "return_exposure", "回返曝光会重新投射最后一次有效记录，但档案没有说明记录范围。")
		response["text"] = "档案称回返曝光会重新投射最后一次有效记录。附图还标出旅店屋顶的维护反射器，它能照到照相馆西墙。"
	elif npc_id == "ada":
		response = _apply_ada_action(action_id, state, response)
	state["flags"] = flags
	TimeManager.sync_world_flags(state)
	return response


func _apply_ada_action(action_id: String, state: Dictionary, response: Dictionary) -> Dictionary:
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	match action_id:
		"anchor_ada_name":
			if KnowledgeManager.knows(state, "ada_identity") and KnowledgeManager.has_evidence(state, "master_ar_record") and KnowledgeManager.has_evidence(state, "chapel_ar_log"):
				flags["ada_name_anchored"] = true
				response["text"] = "Ada Rowan。不是缩写，也不是档案员补出的猜测。那是我在两份独立维修记录上写下的名字。"
				GameManager.add_journal("identity", "身份锚点 1/4：两份独立 A.R. 记录共同确认 Ada Rowan 的姓名。", true)
		"anchor_ada_residence":
			if KnowledgeManager.knows(state, "ada_residence_anchor") and InventoryManager.has_item(state, "unnumbered_key"):
				flags["ada_residence_anchored"] = true
				response["text"] = "七号房。窗框朝湖；钥匙磨损的位置，是我每天握住它留下的。"
				GameManager.add_journal("identity", "身份锚点 2/4：登记缺口、钥匙牌与无编号钥匙共同确认 Ada 的住处。", true)
		"anchor_ada_duty":
			if KnowledgeManager.knows(state, "ada_identity"):
				flags["ada_duty_anchored"] = true
				response["text"] = "中央校准员，第七见证人。我负责确认七个人都能一起继续。"
				GameManager.add_journal("identity", "身份锚点 3/4：主钟与礼拜堂记录共同确认 Ada 的职责。", true)
		"anchor_ada_face":
			if KnowledgeManager.knows(state, "portrait_face_anchor") and InventoryManager.has_item(state, "unfinished_portrait"):
				flags["ada_face_anchored"] = true
				response["text"] = "底片里站在主钟前的人是我。请保留重影——那是每次被删除后仍留下的边缘。"
				GameManager.add_journal("identity", "身份锚点 4/4：洞穴底片与 Ada 的亲自认领共同确认她的面孔。", true)
		"ask_ada_truth":
			var anchored: bool = _all_identity_flags(flags)
			response["text"] = "地下协议没有坏。镇子每次都选择更容易的星期日：让六个人继续，让第七个人从共同记忆里消失。白色旋钮保留的是七个人都在场的时间。" if anchored else "先用真正带来的证据，让名字、住处、职责和面孔都指向我。"
	state["flags"] = flags
	return response


func infer_free_action(npc_id: String, message: String, state: Dictionary) -> String:
	var normalized: String = message.to_lower()
	for action: Dictionary in get_actions(npc_id, state):
		var id: String = str(action.get("id", ""))
		match id:
			"ask_rooms":
				if "登记簿" in normalized or "七号房" in normalized: return id
			"ask_master_record":
				if "控制台" in normalized or ("主钟" in normalized and "记录" in normalized): return id
			"ask_six_bells":
				if "第七锤" in normalized or "六声" in normalized: return id
			"exchange_room7_key":
				if _contains_all(normalized, ["七", "钥匙"]): return id
			"commit_stop_clock":
				if ("停钟" in normalized or "制动" in normalized) and ("扳手" in normalized or "接口" in normalized): return id
			"commit_seventh_bell":
				if ("第七" in normalized or "七声" in normalized) and ("音叉" in normalized or "记录" in normalized): return id
			"route_surface_light":
				if "礼拜堂" in normalized and ("光路" in normalized or "镜片" in normalized): return id
			"route_darkroom_light":
				if ("暗房" in normalized or "西墙" in normalized or "旅店屋顶" in normalized) and ("光" in normalized or "镜片" in normalized): return id
			"receive_flashlight":
				if "洞穴" in normalized or "最低潮" in normalized or "手电" in normalized: return id
			"develop_cave_negative":
				if "底片" in normalized and "显影" in normalized: return id
			"identify_wrench":
				if "扳手" in normalized and ("鉴定" in normalized or "用途" in normalized): return id
			"identify_fork":
				if "音叉" in normalized and ("鉴定" in normalized or "用途" in normalized): return id
			"identify_lens":
				if "镜片" in normalized and ("鉴定" in normalized or "用途" in normalized): return id
			"identify_flashlight":
				if "手电" in normalized and ("鉴定" in normalized or "用途" in normalized): return id
			"compare_ar_records":
				if "记录" in normalized and ("核验" in normalized or "对比" in normalized): return id
			"cross_reference_ada":
				if ("肖像" in normalized or "照片" in normalized) and ("记录" in normalized or "a.r" in normalized): return id
			"research_return_exposure":
				if "曝光" in normalized or "屋顶" in normalized: return id
			"anchor_ada_name":
				if "姓名" in normalized or "名字" in normalized: return id
			"anchor_ada_residence":
				if "住处" in normalized or "七号房" in normalized: return id
			"anchor_ada_duty":
				if "职责" in normalized or "校准员" in normalized: return id
			"anchor_ada_face":
				if "面孔" in normalized or "认领" in normalized: return id
			"ask_ada_truth":
				if "第七" in normalized or "协议" in normalized or "为什么" in normalized: return id
	return "continue_conversation"


func local_free_reply(npc_id: String, message: String, state: Dictionary) -> Dictionary:
	var action_id: String = infer_free_action(npc_id, message, state)
	if action_id != "continue_conversation":
		var result: Dictionary = apply_action(npc_id, action_id, state)
		result["action"] = action_id
		result["provider"] = "local-rules"
		return result
	var npc: Dictionary = DataManager.get_npc(npc_id)
	var facts: Array = (npc.get("knowledge", {}) as Dictionary).get("public", []) as Array
	var reply: String = str(facts[0]) if not facts.is_empty() else "我只能谈本轮共同核验过的事情。把问题说得更具体些。"
	if message.length() < 2:
		reply = "湖边风大。我没听清；请把问题说完整。"
	return {"speaker": npc_id, "text": reply, "action": "continue_conversation", "provider": "local-rules", "puzzle": ""}


func complete_photo_development(state: Dictionary) -> bool:
	var photos: Dictionary = state.get("photos", {}) as Dictionary
	if not InventoryManager.has_item(state, "cave_negative") or bool(photos.get("unfinished_portrait", false)):
		return false
	photos["unfinished_portrait"] = true
	state["photos"] = photos
	InventoryManager.add_item(state, "unfinished_portrait")
	KnowledgeManager.learn(state, "portrait_face_anchor", "洞穴底片按重影、反差、反射三步显影，得到带 A.R. 缩写的未完成肖像。")
	return true


func complete_identity_fixing(state: Dictionary) -> bool:
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	var photos: Dictionary = state.get("photos", {}) as Dictionary
	var ready: bool = _all_identity_flags(flags) and KnowledgeManager.knows(state, "ada_identity") \
		and KnowledgeManager.knows(state, "ada_residence_anchor") and KnowledgeManager.knows(state, "portrait_face_anchor") \
		and KnowledgeManager.has_evidence(state, "master_ar_record") and KnowledgeManager.has_evidence(state, "chapel_ar_log") \
		and InventoryManager.has_item(state, "unfinished_portrait") and InventoryManager.has_item(state, "unnumbered_key")
	if not ready or bool(photos.get("fixed_portrait", false)):
		return false
	photos["fixed_portrait"] = true
	state["photos"] = photos
	InventoryManager.add_item(state, "fixed_portrait")
	KnowledgeManager.learn(state, "ada_fixed", "姓名、住处、职责和面孔四个身份锚点完成定影：Ada Rowan 的肖像不再随循环褪色。")
	TimeManager.sync_npc_schedules(state)
	return true


func install_ada_portrait(state: Dictionary) -> bool:
	if not InventoryManager.has_item(state, "fixed_portrait"):
		return false
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	var photos: Dictionary = state.get("photos", {}) as Dictionary
	flags["slot_seven_filled"] = true
	photos["fixed_portrait_installed"] = true
	state["flags"] = flags
	state["photos"] = photos
	GameManager.add_journal("world", "艾达·罗文的定影肖像进入第七见证位。红色删除杆失去电源，白色继续旋钮弹出。", true)
	TimeManager.sync_npc_schedules(state)
	return true


func surface_protocol_ready(state: Dictionary) -> bool:
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	return bool(flags.get("conrad_routes_light", false)) and bool(flags.get("arthur_stops_clock", false)) and bool(flags.get("beatrice_rings_seventh", false))


func missing_identity_anchors(state: Dictionary) -> PackedStringArray:
	var flags: Dictionary = state.get("flags", {}) as Dictionary
	var output: PackedStringArray = []
	for entry: Array in [
		["ada_name_anchored", "姓名"], ["ada_residence_anchored", "住处"],
		["ada_duty_anchored", "职责"], ["ada_face_anchored", "面孔"]
	]:
		if not bool(flags.get(str(entry[0]), false)):
			output.append(str(entry[1]))
	return output


func _all_identity_flags(flags: Dictionary) -> bool:
	return ["ada_name_anchored", "ada_residence_anchored", "ada_duty_anchored", "ada_face_anchored"].all(func(flag: String) -> bool: return bool(flags.get(flag, false)))


func _contains_all(text: String, terms: Array[String]) -> bool:
	return terms.all(func(term: String) -> bool: return term in text)
