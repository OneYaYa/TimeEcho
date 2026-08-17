extends Node


func learn(state: Dictionary, knowledge_id: String, note: String = "") -> bool:
	var knowledge: Dictionary = state.get("knowledge", {}) as Dictionary
	if bool(knowledge.get(knowledge_id, false)):
		return false
	knowledge[knowledge_id] = true
	state["knowledge"] = knowledge
	if not note.is_empty():
		GameManager.add_journal("knowledge", note, true)
	EventBus.knowledge_changed.emit(knowledge)
	return true


func add_evidence(state: Dictionary, evidence_id: String, note: String = "") -> bool:
	var evidence: Dictionary = state.get("evidence", {}) as Dictionary
	if bool(evidence.get(evidence_id, false)):
		return false
	evidence[evidence_id] = true
	state["evidence"] = evidence
	var knowledge: Dictionary = state.get("knowledge", {}) as Dictionary
	knowledge[evidence_id] = true
	state["knowledge"] = knowledge
	if not note.is_empty():
		GameManager.add_journal("evidence", note, true)
	EventBus.knowledge_changed.emit(knowledge)
	return true


func knows(state: Dictionary, knowledge_id: String) -> bool:
	return bool((state.get("knowledge", {}) as Dictionary).get(knowledge_id, false))


func has_evidence(state: Dictionary, evidence_id: String) -> bool:
	return bool((state.get("evidence", {}) as Dictionary).get(evidence_id, false))


func persistent_snapshot(state: Dictionary) -> Dictionary:
	var persistent_journal: Array = []
	for entry: Variant in state.get("journal", []) as Array:
		if typeof(entry) == TYPE_DICTIONARY and bool((entry as Dictionary).get("persistent", true)):
			persistent_journal.append((entry as Dictionary).duplicate(true))
	return {
		"knowledge": (state.get("knowledge", {}) as Dictionary).duplicate(true),
		"photos": (state.get("photos", {}) as Dictionary).duplicate(true),
		"journal": persistent_journal,
	}
