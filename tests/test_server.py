import json
import unittest
from pathlib import Path

from server import (
    DEFAULT_MODEL,
    DECISION_SCHEMA,
    SYSTEM_PROMPT,
    ServerConfig,
    _extract_decision,
    _responses_url,
    enforce_reply_quality,
)


ROOT = Path(__file__).resolve().parents[1]


class OpenAIResponsesContractTests(unittest.TestCase):
    def test_openai_environment_is_preferred_and_legacy_names_still_work(self):
        config = ServerConfig.from_env(
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "gpt-5.6-luna",
                "OPENAI_REASONING_EFFORT": "low",
            },
            static_root=ROOT,
        )
        self.assertTrue(config.llm_configured)
        self.assertEqual(config.llm_model, "gpt-5.6-luna")
        self.assertEqual(config.llm_reasoning_effort, "low")
        self.assertEqual(config.public_dict()["llm"]["provider"], "openai-responses")

        legacy = ServerConfig.from_env(
            {"LLM_API_KEY": "legacy-key", "LLM_MODEL": "legacy-model"},
            static_root=ROOT,
        )
        self.assertEqual(legacy.llm_model, "legacy-model")

    def test_defaults_and_responses_endpoint(self):
        config = ServerConfig.from_env({}, static_root=ROOT)
        self.assertEqual(config.llm_model, DEFAULT_MODEL)
        self.assertEqual(
            _responses_url("https://api.openai.com/v1"),
            "https://api.openai.com/v1/responses",
        )
        self.assertEqual(
            _responses_url("https://api.openai.com/v1/responses"),
            "https://api.openai.com/v1/responses",
        )

    def test_extracts_structured_responses_output(self):
        decision = {
            "reply": "先把本轮证据放在桌上。",
            "action": "continue_conversation",
            "reason": "只承认共同核验的事实。",
            "memory": "玩家询问了七号房。",
            "referenced_ids": ["belief:dorothea:key_unknown"],
        }
        envelope = {
            "output": [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(decision, ensure_ascii=False),
                }],
            }],
        }
        self.assertEqual(_extract_decision(envelope), decision)

    def test_schema_is_strict_and_closed(self):
        self.assertFalse(DECISION_SCHEMA["additionalProperties"])
        self.assertEqual(
            set(DECISION_SCHEMA["required"]),
            {"reply", "action", "reason", "memory", "referenced_ids"},
        )

    def test_npc_prompt_enforces_continuity_and_executable_actions(self):
        self.assertIn("recent_dialogue", SYSTEM_PROMPT)
        self.assertIn("Do not greet again", SYSTEM_PROMPT)
        self.assertIn("Do not ask the player to present", SYSTEM_PROMPT)
        self.assertIn("Possession is not presentation", SYSTEM_PROMPT)
        self.assertIn(
            "A world-changing action that is absent from the list is forbidden",
            SYSTEM_PROMPT.replace("\n", " "),
        )
        self.assertIn("Treat supplied geography and object facts as a closed world", SYSTEM_PROMPT)
        self.assertIn("a key does not prove that a matching visible door exists", SYSTEM_PROMPT)
        self.assertIn("director_intent influences focus and urgency only", SYSTEM_PROMPT)
        self.assertIn("referenced_ids", SYSTEM_PROMPT)
        self.assertIn("already been decoded", SYSTEM_PROMPT)

    def test_quality_guard_removes_false_hearing_but_keeps_useful_roleplay(self):
        context = {
            "npc_profile": {
                "name": "暗房中的潜影",
                "knowledge": {"known_beliefs": [{
                    "belief_id": "self:memory_gap",
                    "content": "我在暗房中醒来，记忆有缺口。",
                    "truth_status": "known",
                    "confidence": 1.0,
                }]},
            },
            "world_state": {"current_scene": {"place_name": "照相馆暗房"}},
            "player_message": "你是谁？",
            "memories": [],
        }
        decision = enforce_reply_quality(context, {
            "reply": "我没听清你说的话。关于我是谁，我这里只有一段空白。",
            "action": "continue_conversation",
            "reason": "身份未确认。",
            "memory": "我仍说不出身份。",
            "referenced_ids": ["self:memory_gap"],
        })

        self.assertNotIn("没听清", decision["reply"])
        self.assertIn("一段空白", decision["reply"])
        self.assertEqual(decision["quality_guard"], "false_hearing_removed")

    def test_quality_guard_repairs_denial_of_referenced_known_fact(self):
        context = {
            "npc_profile": {
                "name": "林岚",
                "knowledge": {"known_beliefs": [{
                    "belief_id": "obs:east_door",
                    "content": "东侧门通往中央接驳舱。",
                    "truth_status": "known",
                    "confidence": 1.0,
                }]},
            },
            "world_state": {"current_scene": {}},
            "player_message": "Tell me where the east door leads.",
            "memories": [],
        }
        decision = enforce_reply_quality(context, {
            "reply": "我没有确认东门通往哪里。",
            "action": "continue_conversation",
            "reason": "不确定。",
            "memory": "我不知道门的去向。",
            "referenced_ids": ["obs:east_door"],
        })

        self.assertEqual(decision["reply"], "东侧门通往中央接驳舱。")
        self.assertEqual(decision["quality_guard"], "confirmed_fact_repair")

    def test_quality_guard_answers_relevant_known_fact_instead_of_evading(self):
        context = {
            "npc_profile": {
                "name": "多萝西娅",
                "knowledge": {"known_beliefs": [{
                    "belief_id": "place:inn:no_unnumbered_door",
                    "content": "旅店里没有无编号的门：六号与八号之间只有一段空墙。",
                    "truth_status": "known",
                    "confidence": 1.0,
                }]},
            },
            "world_state": {"current_scene": {"place_name": "湖畔旅店"}},
            "player_message": "旅店里到底有没有无编号的门？",
            "memories": [],
        }
        decision = enforce_reply_quality(context, {
            "reply": "我还在整理柜台，你想先问哪一件事？",
            "action": "continue_conversation",
            "reason": "继续交谈。",
            "memory": "玩家来过柜台。",
            "referenced_ids": [],
        })

        self.assertIn("旅店里没有无编号的门", decision["reply"])
        self.assertEqual(
            decision["referenced_ids"],
            ["place:inn:no_unnumbered_door"],
        )
        self.assertEqual(decision["quality_guard"], "relevant_fact_grounded")

    def test_negative_knowledge_boundary_is_not_misread_as_contradiction(self):
        context = {
            "npc_profile": {
                "name": "暗房中的潜影",
                "knowledge": {"known_beliefs": [{
                    "belief_id": "evidence:no_identity_anchor",
                    "content": "玩家尚未出示能固定我身份的本轮证据。",
                    "truth_status": "known",
                    "confidence": 1.0,
                }]},
            },
            "world_state": {"current_scene": {}},
            "player_message": "你承认自己的身份吗？",
            "memories": [],
        }
        decision = enforce_reply_quality(context, {
            "reply": "我无法确认自己的身份。",
            "action": "continue_conversation",
            "reason": "证据不足。",
            "memory": "身份仍未确认。",
            "referenced_ids": ["evidence:no_identity_anchor"],
        })

        self.assertEqual(decision["reply"], "我无法确认自己的身份。")
        self.assertNotIn("quality_guard", decision)


if __name__ == "__main__":
    unittest.main()
