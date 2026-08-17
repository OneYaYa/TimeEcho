class_name TimeEchoAIService
extends Node

var local_provider := LocalAIProvider.new()
var web_provider := WebAIProvider.new()
var http_provider: HttpAIProvider
var context_compiler := TimeEchoContextCompiler.new()
var online_enabled: bool = true
var last_provider: String = "local-rules"
var last_context_trace: Dictionary = {}
var context_trace_history: Array[Dictionary] = []


func _ready() -> void:
	var request_node := HTTPRequest.new()
	request_node.name = "NPCDecisionRequest"
	add_child(request_node)
	var endpoint: String = OS.get_environment("TIME_ECHO_AI_ENDPOINT").strip_edges()
	if endpoint.is_empty() and OS.has_feature("web"):
		var origin: Variant = JavaScriptBridge.eval("window.location.origin", true)
		if typeof(origin) == TYPE_STRING:
			endpoint = str(origin).trim_suffix("/") + "/api/npc/decide"
	http_provider = HttpAIProvider.new(request_node, endpoint)


func talk(npc_id: String, message: String, state: Dictionary) -> Dictionary:
	var compilation := build_context(npc_id, message, state)
	var payload: Dictionary = compilation.get("request", {}) as Dictionary
	last_context_trace = (compilation.get("trace", {}) as Dictionary).duplicate(true)
	if not online_enabled:
		last_provider = "local-rules"
		return _local_fallback(npc_id, message, state, "online_disabled")
	var remote: Dictionary = {}
	if web_provider.is_available():
		remote = web_provider.request_decision(payload)
		last_provider = web_provider.provider_name
	elif http_provider != null and http_provider.is_available():
		remote = await http_provider.request_decision(payload)
		last_provider = http_provider.provider_name
	if remote.is_empty():
		last_provider = "local-rules"
		return _local_fallback(npc_id, message, state, "remote_unavailable")
	var reply: String = str(remote.get("reply", "")).strip_edges()
	var action: String = str(remote.get("action", "continue_conversation"))
	var allowed_actions: Array = ((payload.get("npc_profile", {}) as Dictionary).get("allowed_actions", []) as Array)
	var allowed_ids: Array[String] = []
	for action_value: Variant in allowed_actions:
		if action_value is Dictionary:
			allowed_ids.append(str((action_value as Dictionary).get("id", "")))
	if reply.is_empty() or action not in allowed_ids:
		last_provider = "local-rules"
		return _local_fallback(npc_id, message, state, "invalid_remote_decision")
	var deterministic_action := DialogueManager.infer_free_action(npc_id, message, state)
	if action == "continue_conversation" and deterministic_action != "continue_conversation":
		# Never regress an explicit command that the offline rules already understand.
		last_provider = "local-rules"
		return _local_fallback(npc_id, message, state, "deterministic_action_guard")
	if action != "continue_conversation":
		# The model supplied only a semantic proposal. The deterministic dialogue
		# state machine rechecks prerequisites and owns the actual mutation.
		var committed: Dictionary = DialogueManager.apply_action(npc_id, action, state)
		last_provider = "%s+local-validator" % str(remote.get("provider", last_provider))
		var committed_action := "continue_conversation" if bool(committed.get("rejected", false)) else action
		var references := _reference_ids(remote.get("referenced_ids", []))
		var quality_guard := str(remote.get("quality_guard", "")).strip_edges().left(120)
		_record_trace(last_provider, committed_action, references, "rejected_at_commit" if bool(committed.get("rejected", false)) else "committed", quality_guard)
		return {
			"speaker": npc_id,
			"text": str(committed.get("text", "对方没有改变决定。")),
			"action": committed_action,
			"provider": last_provider,
			"memory": _dialogue_memory(message, str(committed.get("text", ""))),
			"referenced_ids": references,
			"quality_guard": quality_guard,
			"trace": last_context_trace.duplicate(true),
			"puzzle": str(committed.get("puzzle", "")),
		}
	var references := _reference_ids(remote.get("referenced_ids", []))
	var quality_guard := str(remote.get("quality_guard", "")).strip_edges().left(120)
	_record_trace(str(remote.get("provider", last_provider)), "continue_conversation", references, "conversation", quality_guard)
	return {
		"speaker": npc_id,
		"text": reply.left(4000),
		"action": "continue_conversation",
		"provider": str(remote.get("provider", last_provider)),
		"memory": _dialogue_memory(message, reply),
		"referenced_ids": references,
		"quality_guard": quality_guard,
		"trace": last_context_trace.duplicate(true),
		"puzzle": "",
	}


func build_context(npc_id: String, message: String, state: Dictionary) -> Dictionary:
	return context_compiler.compile(npc_id, message, state, DialogueManager.get_actions(npc_id, state))


func get_context_trace_history() -> Array[Dictionary]:
	return context_trace_history.duplicate(true)


func _local_fallback(npc_id: String, message: String, state: Dictionary, reason: String) -> Dictionary:
	var result: Dictionary = local_provider.talk(npc_id, message, state)
	result["memory"] = _dialogue_memory(message, str(result.get("text", "")))
	result["trace"] = last_context_trace.duplicate(true)
	result["trace_reason"] = reason
	_record_trace("local-rules", str(result.get("action", "continue_conversation")), [], reason)
	return result


func _record_trace(provider: String, action: String, referenced_ids: Array[String], outcome: String, quality_guard: String = "") -> void:
	var entry := last_context_trace.duplicate(true)
	entry["provider"] = provider
	entry["selected_action"] = action
	entry["referenced_ids"] = referenced_ids.duplicate()
	entry["outcome"] = outcome
	entry["quality_guard"] = quality_guard
	context_trace_history.append(entry)
	if context_trace_history.size() > 64:
		context_trace_history = context_trace_history.slice(context_trace_history.size() - 64)


func _reference_ids(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if not value is Array:
		return result
	var allowed: Array = last_context_trace.get("included_ids", []) as Array
	for raw: Variant in (value as Array).slice(0, 12):
		var reference := str(raw).strip_edges().left(120)
		if not reference.is_empty() and reference in allowed and reference not in result:
			result.append(reference)
	return result


func _dialogue_memory(player_message: String, reply: String) -> String:
	# Store a sourced recollection of the actual turn, never a second free-form
	# model write that could silently promote a hallucination into future context.
	return "玩家说过：“%s” 我记得自己回应：“%s”" % [player_message.strip_edges().left(180), reply.strip_edges().left(260)]
