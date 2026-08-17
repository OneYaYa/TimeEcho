extends Node

var failures: int = 0
var checks: int = 0


func _ready() -> void:
	call_deferred("_run")


func _run() -> void:
	await get_tree().process_frame
	_check(DataManager.loaded, "JSON content loads and validates")
	for texture_path: String in [
		"res://assets/images/source_art/world/tile_grass.png",
		"res://assets/images/source_art/world/tile_water.png",
		"res://assets/images/source_art/world/tile_cobble.png",
		"res://assets/images/source_art/world/tile_wood.png",
	]:
		_check(ResourceLoader.exists(texture_path), "migrated surface exists: %s" % texture_path.get_file())
		_check(load(texture_path) is Texture2D, "migrated surface imports as Texture2D: %s" % texture_path.get_file())
	var main_scene: PackedScene = load("res://scenes/main/main.tscn") as PackedScene
	_check(main_scene != null, "main scene loads as PackedScene")
	var main_instance: Node = main_scene.instantiate()
	add_child(main_instance)
	await get_tree().process_frame
	_check(main_instance.get_node_or_null("WorldController/WorldView") != null, "main scene contains a drawable world")
	_check(main_instance.get_node_or_null("GameUI/UIRoot/TitleScreen") != null, "main scene builds a visible title layer")
	_check(str(ProjectSettings.get_setting("rendering/renderer/rendering_method", "")) == "gl_compatibility", "desktop renderer remains Web-compatible GL Compatibility")
	_check(str(ProjectSettings.get_setting("rendering/renderer/rendering_method.mobile", "")) == "gl_compatibility", "mobile/Web fallback remains GL Compatibility")
	main_instance.queue_free()
	await get_tree().process_frame
	_check(DataManager.npcs_by_id.size() == 7, "exact seven-NPC cast")
	_check(DataManager.scenes_by_id.size() == 18, "one region plus seventeen places")
	_check(DataManager.items_by_id.has("fixed_portrait"), "stable item IDs are indexed")
	var art_catalog := TimeEchoArtCatalog.new()
	_check(art_catalog.load_catalog(), "typed art manifest loads without resource failures")
	_check(art_catalog.assets_by_id.size() == 253, "art manifest inventories the frozen benchmark catalog and all 178 full-map rollout assets")
	_check((art_catalog.get_asset("prop_buckets") as Dictionary).get("category") == "concept_only", "semantic mismatch is disabled as concept-only")
	_check(art_catalog.get_texture("spr_player") is Texture2D, "processed player sprite imports as Texture2D")
	_check(art_catalog.tile_count("grass_base_variants") == 16, "generated grass atlas exposes sixteen tiles")
	_check(art_catalog.get_atlas_tile("grass_base_variants", 0) is AtlasTexture, "generated atlas tiles load through typed art catalog")
	_check(art_catalog.tile_semantics_by_asset.size() == 45, "all benchmark, P0 fix, and full-map rollout atlases expose named semantics")
	_check(art_catalog.tile_index("grass_base_variants", "base_a") == 0, "named grass semantics resolve without a map-side magic index")
	_check(art_catalog.tile_index("water_shallow_deep_set", "transition_corner_se") == 11, "repaired water atlas exposes the southeast transition corner by name")
	_check(art_catalog.tile_index("water_shallow_deep_set", "deep_c") == 15, "repaired water atlas keeps a third low-noise deep-water variant")
	_check(art_catalog.tile_index("water_transition_patch_set", "shallow_to_deep_outer_nw") == 8, "water transition patch corners resolve by semantic name")
	_check(art_catalog.tile_index("harbor_dock_entry_set", "dock_pile_left") == 4, "harbor dock-entry parts resolve by semantic name")
	_check(art_catalog.get_texture("inn_staircase") is Texture2D, "inn staircase imports as a typed runtime texture")
	_check(art_catalog.get_texture("inn_main_door_closed") is Texture2D, "inn main-door state imports as a typed runtime texture")
	_check(art_catalog.get_named_tile("interior_wall_modular_set", "inn_warm_door_compatible") is AtlasTexture, "named inn doorway tile loads")
	_check(not art_catalog.is_tile_marked_unsafe("natural_shoreline_set", "stone_inner_corner_ne"), "repaired shoreline corner is no longer marked unsafe")
	_check(art_catalog.tile_size("interior_wall_modular_set") == Vector2i(32, 48), "interior wall modules preserve integer 32x48 scale")
	var layout_catalog := TimeEchoArtLayoutCatalog.new()
	_check(layout_catalog.load_catalog(), "all Godot-only art layouts parse and validate")
	_check(layout_catalog.layouts_by_id.size() == 18, "all eighteen locations have stable art layouts")
	var art_review_scene: PackedScene = load("res://scenes/tools/art_review.tscn") as PackedScene
	_check(art_review_scene != null, "art review developer scene loads")
	var vertical_slice_ids: Array[String] = ["player-room", "chapel-belfry", "low-tide-cave", "clock-basement"]
	var expected_slice_zoom: Dictionary = {
		"player-room": 1.25,
		"chapel-belfry": 1.20,
		"low-tide-cave": 1.15,
		"clock-basement": 1.15,
	}
	for scene_value: Variant in DataManager.scenes_by_id.values():
		var scene: Dictionary = scene_value as Dictionary
		for portal_value: Variant in scene.get("portals", []):
			var portal: Dictionary = portal_value as Dictionary
			_check(DataManager.scenes_by_id.has(str(portal.get("targetPlaceId", ""))), "portal target %s exists" % portal.get("id", "?"))
	for benchmark_map_id: String in ["town", "harbor", "inn-lobby"] + vertical_slice_ids:
		var benchmark_scene: Dictionary = DataManager.scenes_by_id.get(benchmark_map_id, {}) as Dictionary
		for portal_value: Variant in benchmark_scene.get("portals", []):
			var benchmark_portal: Dictionary = portal_value as Dictionary
			var travel_state: Dictionary = GameManager.create_initial_state()
			travel_state["placeId"] = benchmark_map_id
			SceneManager.travel(travel_state, benchmark_portal)
			var expected_spawn: Dictionary = benchmark_portal.get("spawn", {}) as Dictionary
			var traveled_player: Dictionary = travel_state.get("player", {}) as Dictionary
			_check(str(travel_state.get("placeId", "")) == str(benchmark_portal.get("targetPlaceId", "")), "%s portal %s travels to its authored target" % [benchmark_map_id, benchmark_portal.get("id", "?")])
			_check(is_equal_approx(float(traveled_player.get("x", -1.0)), float(expected_spawn.get("x", -2.0))) and is_equal_approx(float(traveled_player.get("y", -1.0)), float(expected_spawn.get("y", -2.0))), "%s portal %s applies its authored spawn" % [benchmark_map_id, benchmark_portal.get("id", "?")])

	var runtime_scene: PackedScene = load("res://scenes/locations/location_runtime.tscn") as PackedScene
	var runtime: TimeEchoWorldController = runtime_scene.instantiate() as TimeEchoWorldController
	add_child(runtime)
	await get_tree().process_frame
	var art_state: Dictionary = GameManager.create_initial_state()
	art_state["speed"] = 0.0
	art_state["repairs"] = {"master": true, "chapel": true, "tide": true}
	var art_flags: Dictionary = art_state.get("flags", {}) as Dictionary
	art_flags["counterweight_raised"] = true
	art_flags["light_route_inn_studio"] = true
	art_flags["slot_seven_filled"] = true
	art_flags["arthur_stops_clock"] = true
	art_flags["beatrice_rings_seventh"] = true
	art_state["flags"] = art_flags
	InventoryManager.add_item(art_state, "unnumbered_key")
	InventoryManager.add_item(art_state, "flashlight")
	TimeManager.sync_npc_schedules(art_state)
	for scene_value: Variant in DataManager.scenes_by_id.values():
		var scene: Dictionary = scene_value as Dictionary
		var map_id: String = str(scene.get("id", "?"))
		art_state["placeId"] = map_id
		var player_state: Dictionary = art_state.get("player", {}) as Dictionary
		var review_layout: Dictionary = layout_catalog.get_layout(map_id)
		var review_position: Array = review_layout.get("review_player_position", [roundf(float(scene.get("width", 768)) * 0.5), roundf(float(scene.get("height", 480)) * 0.58)]) as Array
		player_state["x"] = float(review_position[0])
		player_state["y"] = float(review_position[1])
		art_state["player"] = player_state
		runtime.load_state(art_state, true)
		var metrics: Dictionary = runtime.get_art_review_metrics()
		_check((metrics.get("asset_errors", PackedStringArray()) as PackedStringArray).is_empty(), "%s has no art resource failures" % scene.get("id", "?"))
		_check((metrics.get("warnings", PackedStringArray()) as PackedStringArray).is_empty(), "%s has integer art transforms and no flagged overlap" % scene.get("id", "?"))
		var generated_tiles: int = int(metrics.get("generated_tile_count", 0))
		_check(generated_tiles > 0, "%s builds its authored static semantic atlas layer" % map_id)
		for portal_value: Variant in metrics.get("portal_reachability", []):
			var portal: Dictionary = portal_value as Dictionary
			_check(bool(portal.get("reachable", false)), "%s portal %s is reachable" % [scene.get("id", "?"), portal.get("portal_id", "?")])
		if map_id in vertical_slice_ids:
			_check(is_equal_approx(float(metrics.get("camera_zoom", 0.0)), float(expected_slice_zoom[map_id])), "%s uses its reviewed gameplay camera zoom" % map_id)
			_check(int(metrics.get("foreground_count", 0)) > 0, "%s instantiates an authored foreground occlusion layer" % map_id)
			var level_art_metrics: Dictionary = review_layout.get("level_art_metrics", {}) as Dictionary
			_check(float(level_art_metrics.get("empty_ratio_estimate", 1.0)) <= 0.30, "%s keeps unassigned empty floor at or below the Level Art threshold" % map_id)
			_check(int(level_art_metrics.get("function_clusters", 0)) >= 3, "%s declares at least three authored function clusters" % map_id)
			_check((level_art_metrics.get("new_raster_asset_ids", []) as Array).is_empty(), "%s adds no decorative raster asset IDs" % map_id)
			for interaction_value: Variant in metrics.get("interaction_reachability", []):
				var interaction: Dictionary = interaction_value as Dictionary
				_check(bool(interaction.get("reachable", false)), "%s interaction %s is reachable" % [map_id, interaction.get("landmark_id", "?")])
			if map_id in ["chapel-belfry", "clock-basement"]:
				_check(not (metrics.get("npc_reachability", []) as Array).is_empty(), "%s instantiates its committed story NPC" % map_id)
				for npc_value: Variant in metrics.get("npc_reachability", []):
					var npc_reach: Dictionary = npc_value as Dictionary
					_check(bool(npc_reach.get("reachable", false)), "%s NPC %s is reachable from the entry path" % [map_id, npc_reach.get("npc_id", "?")])
			if map_id == "chapel-belfry":
				_check(bool((review_layout.get("canvas", {}) as Dictionary).get("open_structure", false)), "chapel-belfry disables the ordinary rectangular room shell")
			if map_id == "clock-basement":
				var slot_positions: Dictionary = {}
				var signal_ids: Array[String] = []
				for object_value: Variant in review_layout.get("objects", []):
					var art_object: Dictionary = object_value as Dictionary
					var object_id: String = str(art_object.get("object_id", ""))
					if object_id.begins_with("basement_slot_"):
						var position_values: Array = art_object.get("position", []) as Array
						slot_positions[str(position_values)] = true
					if object_id in ["basement_signal_red", "basement_signal_gold", "basement_signal_white"]:
						signal_ids.append(object_id)
				_check(slot_positions.size() == 7, "clock-basement presents seven spatially distinct witness slots")
				_check(signal_ids.size() == 3, "clock-basement presents exactly three elevated external signal lights")

	art_state["placeId"] = "town"
	var movement_state: Dictionary = art_state.get("player", {}) as Dictionary
	movement_state["x"] = 576.0
	movement_state["y"] = 600.0
	art_state["player"] = movement_state
	runtime.load_state(art_state, true)
	var test_player := runtime.get_node("WorldView/Characters/Player") as TimeEchoPlayer
	test_player.active = true
	var player_before: Vector2 = test_player.position
	Input.action_press("move_right")
	await get_tree().physics_frame
	await get_tree().physics_frame
	Input.action_release("move_right")
	_check(test_player.position.x > player_before.x, "player moves through the rebuilt town route under real physics")
	_check(test_player.z_index == roundi(test_player.position.y), "player Y sort follows the moved world position")
	_check(runtime.get_node("WorldView/Collisions").get_child_count() > 0, "rebuilt benchmark collision bodies instantiate at runtime")
	_check((runtime.get_node("WorldView/WorldObjects") as Node2D).y_sort_enabled, "world props retain Y sorting")

	var slice_movement_cases: Dictionary = {
		"player-room": {"position": Vector2(384.0, 405.0), "action": "move_up"},
		"chapel-belfry": {"position": Vector2(120.0, 350.0), "action": "move_right"},
		"low-tide-cave": {"position": Vector2(120.0, 320.0), "action": "move_right"},
		"clock-basement": {"position": Vector2(384.0, 405.0), "action": "move_down"},
	}
	for map_id: String in vertical_slice_ids:
		var movement_case: Dictionary = slice_movement_cases[map_id] as Dictionary
		var slice_player_state: Dictionary = art_state.get("player", {}) as Dictionary
		var slice_position: Vector2 = movement_case["position"] as Vector2
		slice_player_state["x"] = slice_position.x
		slice_player_state["y"] = slice_position.y
		art_state["player"] = slice_player_state
		art_state["placeId"] = map_id
		runtime.load_state(art_state, true)
		var slice_player := runtime.get_node("WorldView/Characters/Player") as TimeEchoPlayer
		slice_player.active = true
		var slice_before: Vector2 = slice_player.position
		var movement_action: String = str(movement_case["action"])
		Input.action_press(movement_action)
		for frame: int in range(6):
			await get_tree().physics_frame
		Input.action_release(movement_action)
		await get_tree().physics_frame
		_check(slice_player.position.distance_to(slice_before) > 0.5, "%s player traverses its entrance path under real physics" % map_id)
		_check(slice_player.z_index == roundi(slice_player.position.y), "%s player Y sort follows physical movement" % map_id)
		_check(runtime.get_node("WorldView/Collisions").get_child_count() > 0, "%s collision bodies instantiate at runtime" % map_id)

	var npc_scene := load("res://scenes/characters/npc.tscn") as PackedScene
	var test_npc := npc_scene.instantiate() as TimeEchoNPCActor
	add_child(test_npc)
	var conrad_profile: Dictionary = DataManager.npcs_by_id.get("conrad", {}) as Dictionary
	var moving_npc_state: Dictionary = {"x": 100.0, "y": 180.0, "targetX": 134.0, "targetY": 180.0, "facing": "right"}
	test_npc.configure(conrad_profile, moving_npc_state)
	test_npc.update_from_state(moving_npc_state, 0.5)
	_check(test_npc.position.x > 100.0, "NPC actor moves toward its scheduled target")
	_check(test_npc.z_index == roundi(test_npc.position.y), "NPC Y sort follows its scheduled movement")
	test_npc.queue_free()
	runtime.queue_free()
	await get_tree().process_frame

	var state: Dictionary = GameManager.create_initial_state()
	_check(state.get("placeId") == "player-room", "new game starts in room eight")
	_check(is_equal_approx(float((state.get("player", {}) as Dictionary).get("x", -1.0)), 384.0) and is_equal_approx(float((state.get("player", {}) as Dictionary).get("y", -1.0)), 370.0), "new game uses the retained player-room spawn")
	_check(int(state.get("minute", 0)) == 360, "loop starts Saturday 06:00")
	var context_compiler := TimeEchoContextCompiler.new()
	var ada_compilation: Dictionary = context_compiler.compile("ada", "你叫什么名字？", state, DialogueManager.get_actions("ada", state))
	var ada_request: Dictionary = ada_compilation.get("request", {}) as Dictionary
	var ada_profile: Dictionary = ada_request.get("npc_profile", {}) as Dictionary
	var ada_encoded := JSON.stringify(ada_request)
	_check(str(ada_profile.get("id", "")) == "hidden_figure" and str(ada_profile.get("name", "")) == "暗房中的潜影", "unanchored Ada uses a staged identity profile")
	_check(not ada_encoded.contains("中央校准员") and not ada_encoded.contains("第七见证人"), "unanchored Ada context contains no hidden identity facts")
	_check((ada_profile.get("allowed_actions", []) as Array).any(func(action: Variant) -> bool: return action is Dictionary and str((action as Dictionary).get("id", "")) == "continue_conversation"), "typed context always retains a no-mutation action")
	_check(((ada_request.get("world_state", {}) as Dictionary).get("flags", {}) as Dictionary).is_empty(), "private world flags never enter the NPC request")
	var compiler_trace: Dictionary = ada_compilation.get("trace", {}) as Dictionary
	_check(not str(compiler_trace.get("trace_id", "")).is_empty() and not (compiler_trace.get("partition_token_estimates", {}) as Dictionary).is_empty(), "context compiler emits replay and token-budget trace data")
	var trace_service := TimeEchoAIService.new()
	add_child(trace_service)
	trace_service.online_enabled = false
	var traced_reply: Dictionary = await trace_service.talk("arthur", "今天风很大。", state)
	var trace_history: Array = trace_service.get_context_trace_history()
	_check(not (traced_reply.get("trace", {}) as Dictionary).is_empty() and trace_history.size() == 1, "AI service keeps a bounded local trace for offline and online turns")
	_check(str((trace_history[0] as Dictionary).get("provider", "")) == "local-rules", "trace records the provider and fallback outcome")
	trace_service.queue_free()

	var memory_state: Dictionary = GameManager.create_initial_state()
	var arthur_state: Dictionary = ((memory_state.get("npcs", {}) as Dictionary).get("arthur", {}) as Dictionary)
	arthur_state["memories"] = [
		{"memory_id": "memory:old", "subjective_text": "上一轮的普通对话", "loop": 0},
		{"memory_id": "memory:current", "subjective_text": "本轮共同检查了主钟", "loop": 1},
	]
	(memory_state.get("npcNotes", {}) as Dictionary)["arthur"] = [
		{"event_id": "dialogue:old", "loop": 0, "player": "上一轮", "reply": "旧回复"},
		{"event_id": "dialogue:current", "loop": 1, "player": "本轮", "reply": "当前回复"},
	]
	var memory_compilation: Dictionary = context_compiler.compile("arthur", "还记得吗？", memory_state, DialogueManager.get_actions("arthur", memory_state))
	var memory_request: Dictionary = memory_compilation.get("request", {}) as Dictionary
	var compiled_memories: Array = memory_request.get("memories", []) as Array
	var compiled_dialogue: Array = ((memory_request.get("world_state", {}) as Dictionary).get("recent_dialogue", []) as Array)
	_check(compiled_memories.size() == 1 and str((compiled_memories[0] as Dictionary).get("memory_id", "")) == "memory:current", "old-loop NPC memory is hard-filtered before retrieval")
	_check(compiled_dialogue.size() == 1 and str((compiled_dialogue[0] as Dictionary).get("event_id", "")) == "dialogue:current", "old-loop dialogue never enters current context")
	var persistent_memory: Dictionary = KnowledgeManager.persistent_snapshot(memory_state)
	_check(not persistent_memory.has("npcNotes"), "ordinary NPC dialogue is excluded from cross-loop persistence")
	var reset_projection: Dictionary = GameManager.create_initial_state(persistent_memory)
	_check((reset_projection.get("npcNotes", {}) as Dictionary).is_empty() and (((reset_projection.get("npcs", {}) as Dictionary).get("arthur", {}) as Dictionary).get("memories", []) as Array).is_empty(), "loop reset clears ordinary resident memories")
	var invalid_commit_state: Dictionary = GameManager.create_initial_state()
	var rejected_commit: Dictionary = DialogueManager.apply_action("beatrice", "commit_seventh_bell", invalid_commit_state)
	_check(bool(rejected_commit.get("rejected", false)), "mutation validator rejects an action absent from the current authoritative whitelist")
	_check(not bool((invalid_commit_state.get("flags", {}) as Dictionary).get("beatrice_rings_seventh", false)), "rejected AI proposal cannot mutate quest state")
	var before: float = float(state.get("loopElapsed", 0.0))
	TimeManager.advance(state, 1.0)
	_check(is_equal_approx(float(state.get("loopElapsed", 0.0)) - before, 2.0), "one real second advances two game minutes")
	state["conversationOpen"] = true
	before = float(state.get("loopElapsed", 0.0))
	TimeManager.advance(state, 1.0)
	_check(is_equal_approx(float(state.get("loopElapsed", 0.0)) - before, 0.5), "dialogue uses quarter-speed time")
	state["conversationOpen"] = false
	state["placeId"] = "low-tide-cave"
	before = float(state.get("loopElapsed", 0.0))
	TimeManager.advance(state, 1.0)
	_check(is_equal_approx(float(state.get("loopElapsed", 0.0)), before), "low-tide cave pauses time")

	var slice_interaction_service := InteractionService.new()
	var room_state: Dictionary = GameManager.create_initial_state()
	GameManager.state = room_state
	var bed_result: Dictionary = slice_interaction_service.interact({"id": "player_bed"}, room_state)
	_check(bed_result.get("kind") == "rest" and bool((room_state.get("flags", {}) as Dictionary).get("rested_in_room", false)), "player-room bed exposes a real rest interaction and stable state flag")
	var rest_before: float = float(room_state.get("loopElapsed", 0.0))
	TimeManager.advance_travel(room_state, float(bed_result.get("real_seconds", 0.0)))
	_check(is_equal_approx(float(room_state.get("loopElapsed", 0.0)) - rest_before, 30.0), "player-room rest advances the authored half-hour")
	var journal_result: Dictionary = slice_interaction_service.interact({"id": "player_journal"}, room_state)
	var memory_result: Dictionary = slice_interaction_service.interact({"id": "player_memory_board"}, room_state)
	_check(journal_result.get("kind") == "journal" and journal_result.get("tab") == "journal", "player-room journal interaction opens retained notes")
	_check(memory_result.get("kind") == "journal" and memory_result.get("tab") == "inventory", "player-room memory board opens retained photos and items")

	var belfry_state: Dictionary = GameManager.create_initial_state()
	GameManager.state = belfry_state
	InventoryManager.add_item(belfry_state, "silver_tuning_fork")
	var belfry_flags: Dictionary = belfry_state.get("flags", {}) as Dictionary
	belfry_flags["fork_identified"] = true
	belfry_flags["beatrice_rings_seventh"] = true
	belfry_state["flags"] = belfry_flags
	slice_interaction_service.interact({"id": "seventh_hammer"}, belfry_state)
	var rope_result: Dictionary = slice_interaction_service.interact({"id": "belfry_calibration_rope"}, belfry_state)
	_check(bool((belfry_state.get("flags", {}) as Dictionary).get("seventh_hammer_calibrated", false)), "identified tuning fork calibrates the belfry seventh-hammer frame")
	_check(bool((belfry_state.get("flags", {}) as Dictionary).get("seventh_signal_ready", false)) and rope_result.get("kind") == "inspect", "belfry rope connects the calibrated hammer to Beatrice's commitment")
	TimeManager.sync_npc_schedules(belfry_state)
	_check(str(((belfry_state.get("npcs", {}) as Dictionary)["beatrice"] as Dictionary).get("placeId", "")) == "chapel-belfry", "committed Beatrice is reachable at the authored belfry maintenance position")

	var cave_state: Dictionary = GameManager.create_initial_state()
	GameManager.state = cave_state
	slice_interaction_service.interact({"id": "cave_negative_pickup"}, cave_state)
	_check(not InventoryManager.has_item(cave_state, "cave_negative"), "cave evidence remains hidden without the flashlight")
	InventoryManager.add_item(cave_state, "flashlight")
	slice_interaction_service.interact({"id": "cave_negative_pickup"}, cave_state)
	_check(InventoryManager.has_item(cave_state, "cave_negative"), "flashlight reveals and collects the cave negative")

	GameManager.state = state
	GameManager.mark_repair("master")
	GameManager.mark_repair("chapel")
	GameManager.mark_repair("tide")
	_check(bool((state.get("flags", {}) as Dictionary).get("basement_open", false)), "three repairs reveal basement")
	KnowledgeManager.add_evidence(state, "ledger_gap")
	InventoryManager.add_item(state, "room7_tag")
	var dorothea_actions: Array[Dictionary] = DialogueManager.get_actions("dorothea", state)
	_check(dorothea_actions.any(func(action: Dictionary) -> bool: return action.get("id") == "exchange_room7_key"), "room-seven evidence unlocks authored handoff")
	DialogueManager.apply_action("dorothea", "exchange_room7_key", state)
	_check(InventoryManager.has_item(state, "unnumbered_key"), "NPC action gives unnumbered key")

	KnowledgeManager.learn(state, "persistent_test")
	InventoryManager.add_item(state, "temporary_test")
	GameManager.state = state
	var reset_state: Dictionary = GameManager.reset_loop()
	_check(KnowledgeManager.knows(reset_state, "persistent_test"), "knowledge survives loop reset")
	_check(not InventoryManager.has_item(reset_state, "temporary_test"), "physical inventory resets")
	_check(InputMap.has_action("run"), "sprint input remains registered")
	_check(TimeManager.scene_pauses_time("hidden-darkroom"), "hidden darkroom pauses time")

	var logic_state: Dictionary = GameManager.create_initial_state()
	GameManager.state = logic_state
	logic_state["loopElapsed"] = 20.0 * 60.0
	TimeManager.sync_world_flags(logic_state)
	_check(bool((logic_state.get("flags", {}) as Dictionary).get("low_tide", false)), "low-tide cave reveal window opens at the authored time")
	InventoryManager.add_item(logic_state, "flashlight")
	InventoryManager.add_item(logic_state, "cave_negative")
	_check(DialogueManager.complete_photo_development(logic_state), "cave negative develops through the authored photo flow")
	_check(InventoryManager.has_item(logic_state, "unfinished_portrait"), "photo development grants the unfinished portrait")

	var hidden_flags: Dictionary = logic_state.get("flags", {}) as Dictionary
	hidden_flags["counterweight_raised"] = true
	hidden_flags["light_route_inn_studio"] = true
	logic_state["flags"] = hidden_flags
	InventoryManager.add_item(logic_state, "unnumbered_key")
	TimeManager.sync_world_flags(logic_state)
	_check(bool((logic_state.get("flags", {}) as Dictionary).get("hidden_darkroom_open", false)), "hidden darkroom requires both routes and the unnumbered key")
	KnowledgeManager.add_evidence(logic_state, "master_ar_record")
	KnowledgeManager.add_evidence(logic_state, "chapel_ar_log")
	KnowledgeManager.learn(logic_state, "ada_identity")
	KnowledgeManager.learn(logic_state, "ada_residence_anchor")
	KnowledgeManager.learn(logic_state, "portrait_face_anchor")
	for action_id: String in ["anchor_ada_name", "anchor_ada_residence", "anchor_ada_duty", "anchor_ada_face"]:
		DialogueManager.apply_action("ada", action_id, logic_state)
	_check(DialogueManager.missing_identity_anchors(logic_state).is_empty(), "all four Ada identity anchors remain independently required")
	_check(DialogueManager.complete_identity_fixing(logic_state), "four anchored facts produce the fixed portrait")
	_check(DialogueManager.install_ada_portrait(logic_state), "fixed portrait installs into witness slot seven")
	var interaction_service := InteractionService.new()
	var true_result: Dictionary = interaction_service.interact({"id": "white_continue_knob"}, logic_state)
	_check(true_result.get("kind") == "ending" and true_result.get("ending") == "true", "white continuation control reaches the true ending")
	var locked_red: Dictionary = interaction_service.interact({"id": "red_erase_lever"}, logic_state)
	_check(locked_red.get("kind") != "ending", "red erasure control is disabled after restoring witness seven")

	var surface_state: Dictionary = GameManager.create_initial_state()
	GameManager.state = surface_state
	var surface_flags: Dictionary = surface_state.get("flags", {}) as Dictionary
	surface_flags["conrad_routes_light"] = true
	surface_flags["arthur_stops_clock"] = true
	surface_flags["beatrice_rings_seventh"] = true
	surface_state["flags"] = surface_flags
	var surface_result: Dictionary = interaction_service.interact({"id": "red_erase_lever"}, surface_state)
	_check(surface_result.get("kind") == "ending" and surface_result.get("ending") == "surface", "red erasure control reaches the surface ending when three commitments are ready")

	var scheduled_state: Dictionary = GameManager.create_initial_state()
	scheduled_state["loopElapsed"] = 4.0 * 60.0
	TimeManager.sync_npc_schedules(scheduled_state)
	_check(str(((scheduled_state.get("npcs", {}) as Dictionary)["dorothea"] as Dictionary).get("placeId", "")) == "inn-lobby", "NPC schedule semantics still place the innkeeper at reception")
	var local_reply: Dictionary = DialogueManager.local_free_reply("arthur", "主钟怎么修？", scheduled_state)
	_check(local_reply.get("provider") == "local-rules" and not str(local_reply.get("text", "")).is_empty(), "AI dialogue retains an offline local-rules fallback")
	var legacy_save: Dictionary = {"version": 0, "placeId": "town"}
	var migrated_save: Dictionary = SaveManager._migrate(legacy_save)
	_check(int(migrated_save.get("version", 0)) == SaveManager.CURRENT_VERSION, "legacy save version remains compatibility-readable without disk writes")
	if "--save-io-test" in OS.get_cmdline_user_args():
		const TEST_USER_DIR: String = "time-echo-art-refactor-save-test"
		ProjectSettings.set_setting("application/config/use_custom_user_dir", true)
		ProjectSettings.set_setting("application/config/custom_user_dir_name", TEST_USER_DIR)
		var isolated_root: String = ProjectSettings.globalize_path("user://")
		print("Isolated save I/O root: %s" % isolated_root)
		var isolated: bool = TEST_USER_DIR in isolated_root.to_lower()
		_check(isolated, "save I/O test resolves to its isolated user directory")
		if isolated:
			var directory_error: Error = DirAccess.make_dir_recursive_absolute(isolated_root)
			_check(directory_error in [OK, ERR_ALREADY_EXISTS], "isolated save directory can be created")
			var io_state: Dictionary = GameManager.create_initial_state()
			io_state["placeId"] = "harbor-control"
			io_state["loopCount"] = 7
			_check(SaveManager.save_game(io_state), "isolated user directory accepts a real save write")
			var loaded_state: Dictionary = SaveManager.load_game()
			_check(loaded_state.get("placeId") == "harbor-control" and int(loaded_state.get("loopCount", -1)) == 7, "real save data reads back with stable fields")
			var cleanup_file: Error = DirAccess.remove_absolute(ProjectSettings.globalize_path(SaveManager.SAVE_PATH))
			var cleanup_directory: Error = DirAccess.remove_absolute(isolated_root.trim_suffix("/"))
			_check(cleanup_file == OK and cleanup_directory == OK, "isolated save I/O artifacts are removed after verification")

	print("TIME ECHO tests: %d checks, %d failures" % [checks, failures])
	call_deferred("_finish", 1 if failures > 0 else 0)


func _finish(exit_code: int) -> void:
	get_tree().quit(exit_code)


func _check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: %s" % label)
