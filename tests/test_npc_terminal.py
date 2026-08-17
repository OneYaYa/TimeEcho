import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from server import ServerConfig
from tools.npc_terminal import (
    NpcTerminal,
    apply_preset,
    apply_terminal_action,
    authored_continue_reply,
    available_plot_actions,
    beatrice_commit_status,
    build_request,
    compile_context,
    default_state,
    infer_plot_action,
    load_world,
    normalize_state,
    npc_index,
    visible_facts,
)


class NpcTerminalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = load_world()
        cls.npcs = npc_index(cls.world)

    def setUp(self):
        self.state = default_state(self.world)

    def test_room_key_tag_is_projected_only_to_dorothea(self):
        self.assertFalse(
            any(
                "七号房铜钥匙牌" in fact
                for fact in visible_facts(
                    self.npcs["dorothea"], self.state
                )
            )
        )
        self.state["inventory"]["room7_tag"] = 1
        dorothea = visible_facts(
            self.npcs["dorothea"], self.state
        )
        arthur = visible_facts(self.npcs["arthur"], self.state)
        self.assertTrue(
            any("七号房铜钥匙牌" in fact for fact in dorothea)
        )
        self.assertFalse(
            any("七号房铜钥匙牌" in fact for fact in arthur)
        )

    def test_dorothea_knows_the_inn_has_no_unnumbered_door(self):
        facts = visible_facts(self.npcs["dorothea"], self.state)
        self.assertTrue(any("旅店里没有无编号的门" in fact for fact in facts))
        self.assertTrue(any("没有门的空墙" in fact for fact in facts))

    def test_old_false_door_memory_is_not_sent_to_the_model(self):
        npc_state = self.state["npcs"]["dorothea"]
        npc_state["memories"].append({
            "text": "旅店内存在一扇一直没有编号的门。",
            "importance": 1,
            "loop": 1,
        })
        npc_state["dialogue"].append({
            "player": "旅店还有没有编号的门？",
            "reply": "有，旅店里确实有一扇一直没有编号的门。",
            "action": "continue_conversation",
        })
        request = build_request(
            self.world,
            self.npcs["dorothea"],
            self.state,
            "这把钥匙到底开哪里？",
        )
        encoded = json.dumps(request, ensure_ascii=False)
        self.assertNotIn("确实有一扇一直没有编号的门", encoded)
        self.assertNotIn("存在一扇一直没有编号的门", encoded)
        self.assertIn("旅店里没有无编号的门", encoded)

    def test_old_invented_pressure_release_requirement_is_not_sent_to_arthur(self):
        npc_state = self.state["npcs"]["arthur"]
        npc_state["memories"].append({
            "text": "阿瑟要求玩家告诉他档案确认的操作，以及怎样避免锁死主轮。",
            "importance": 1,
            "loop": 1,
        })
        npc_state["dialogue"].append({
            "player": "我有扳手和泄压步骤",
            "reply": "然后告诉我档案确认的操作：它断开哪一段机构，怎样避免锁死主轮。",
            "action": "continue_conversation",
        })
        request = build_request(
            self.world,
            self.npcs["arthur"],
            self.state,
            "那我应该去哪里？",
        )
        encoded = json.dumps(request, ensure_ascii=False)
        self.assertNotIn("怎样避免锁死主轮", encoded)
        self.assertNotIn("告诉他档案确认的操作", encoded)

    def test_known_bad_old_npc_replies_are_not_reused_as_examples(self):
        stale = {
            "beatrice": "第七锤不是报时，而是宣告某个记录已经结束。",
            "dorothea": "要不要我给你倒杯热水，顺便把前台那三份委托单给你？",
            "florence": "我知道你带着它们。可我还没看到原件。",
        }
        for npc_id, reply in stale.items():
            with self.subTest(npc=npc_id):
                state = default_state(self.world)
                state["npcs"][npc_id]["dialogue"].append({
                    "player": "继续说。",
                    "reply": reply,
                    "action": "continue_conversation",
                })
                request = build_request(
                    self.world,
                    self.npcs[npc_id],
                    state,
                    "然后呢？",
                )
                self.assertNotIn(
                    reply,
                    json.dumps(request, ensure_ascii=False),
                )

    def test_master_evidence_is_projected_to_relevant_npcs(self):
        self.state["evidence"]["master_ar_record"] = True
        arthur = visible_facts(self.npcs["arthur"], self.state)
        florence = visible_facts(
            self.npcs["florence"], self.state
        )
        beatrice = visible_facts(
            self.npcs["beatrice"], self.state
        )
        self.assertTrue(any("A.R." in fact for fact in arthur))
        self.assertTrue(any("A.R." in fact for fact in florence))
        self.assertFalse(any("A.R." in fact for fact in beatrice))

    def test_public_facts_and_residual_memory_are_separate(self):
        request = build_request(
            self.world,
            self.npcs["arthur"],
            self.state,
            "母钟里面有什么？",
        )
        knowledge = request["npc_profile"]["knowledge"]
        self.assertTrue(any("三枚错位齿轮" in fact for fact in knowledge["public"]))
        self.assertTrue(any("跳过最后一路" in fact for fact in knowledge["residual"]))
        encoded = json.dumps(request, ensure_ascii=False)
        self.assertNotIn("红色手柄与白色旋钮对应的结局", encoded)

    def test_terminal_compiler_matches_runtime_protocol_and_filters_old_loop(self):
        npc_state = self.state["npcs"]["arthur"]
        npc_state["memories"] = [
            {"memory_id": "memory:old", "text": "上一轮的普通对话", "loop": 0},
            {"memory_id": "memory:current", "text": "本轮共同检查了主钟", "loop": 1},
        ]
        npc_state["dialogue"] = [
            {"player": "上一轮说过的话", "reply": "上一轮回答", "loop": 0},
            {"player": "本轮说过的话", "reply": "本轮回答", "loop": 1},
        ]

        compilation = compile_context(
            self.world,
            self.npcs["arthur"],
            self.state,
            "还记得吗？",
        )
        request = compilation["request"]
        trace = compilation["trace"]

        self.assertEqual(
            ["memory:current"],
            [entry["memory_id"] for entry in request["memories"]],
        )
        self.assertEqual(
            ["本轮说过的话"],
            [entry["player"] for entry in request["world_state"]["recent_dialogue"]],
        )
        self.assertIn("known_beliefs", request["npc_profile"]["knowledge"])
        self.assertIn("persona_core", request["npc_profile"])
        self.assertIn("active_scene_mode", request["npc_profile"])
        self.assertIn("director_intent", request["world_state"])
        self.assertNotIn("trace", request)
        self.assertEqual("time-echo-terminal-context-v2", trace["template_version"])
        self.assertTrue(trace["dropped"])
        self.assertTrue(trace["partition_token_estimates"])

    def test_ada_profile_stays_anonymous_until_her_own_name_anchor(self):
        darkroom = apply_preset(self.state, "darkroom", self.world)
        request = build_request(
            self.world,
            self.npcs["ada"],
            darkroom,
            "你是谁？",
        )
        profile = request["npc_profile"]
        self.assertEqual("hidden_figure", profile["id"])
        self.assertEqual("暗房中的潜影", profile["name"])
        self.assertNotIn("中央校准员", profile["role"])
        self.assertNotIn(
            "Ada Rowan",
            json.dumps(request, ensure_ascii=False),
        )
        encoded = json.dumps(request, ensure_ascii=False)
        self.assertNotIn("中央校准员", encoded)
        self.assertNotIn("第七见证人", encoded)
        reply = authored_continue_reply("ada", darkroom, "你是谁？")
        self.assertIn("我不知道", reply)

        darkroom["flags"]["ada_name_anchored"] = True
        named_request = build_request(
            self.world,
            self.npcs["ada"],
            darkroom,
            "你现在记得什么？",
        )
        self.assertEqual("hidden_figure", named_request["npc_profile"]["id"])
        self.assertEqual("艾达·罗文", named_request["npc_profile"]["name"])
        self.assertNotIn("中央校准员", named_request["npc_profile"]["role"])

    def test_cave_preset_updates_time_and_two_npc_views(self):
        state = apply_preset(
            self.state, "cave", self.world
        )
        self.assertEqual("SUNDAY", state["dayLabel"])
        self.assertEqual(135, state["minute"])
        self.assertTrue(state["flags"]["low_tide"])
        conrad = visible_facts(self.npcs["conrad"], state)
        elias = visible_facts(self.npcs["elias"], state)
        self.assertTrue(any("最低潮窗口" in fact for fact in conrad))
        self.assertTrue(any("受潮底片" in fact for fact in elias))

    def test_ada_presets_separate_appearance_from_complete_identity(self):
        darkroom = apply_preset(
            self.state, "darkroom", self.world
        )
        self.assertTrue(darkroom["flags"]["hidden_darkroom_open"])
        self.assertEqual(
            "visible", darkroom["npcs"]["ada"]["status"]
        )
        self.assertFalse(darkroom["flags"].get("ada_name_anchored"))
        complete = apply_preset(
            darkroom, "identity_complete", self.world
        )
        facts = visible_facts(self.npcs["ada"], complete)
        self.assertTrue(
            any(
                "姓名、住处、职责、面孔" in fact
                for fact in facts
            )
        )

    def test_request_contains_projection_not_private_state(self):
        self.state["inventory"]["room7_tag"] = 1
        self.state["inventory"]["flashlight"] = 1
        self.state["evidence"]["ledger_gap"] = True
        self.state["flags"]["hidden_darkroom_open"] = True
        request = build_request(
            self.world,
            self.npcs["dorothea"],
            self.state,
            "七号房是谁住的？",
        )
        encoded = json.dumps(request, ensure_ascii=False)
        self.assertIn("七号房铜钥匙牌", encoded)
        self.assertIn("登记簿缺失的第七行", encoded)
        self.assertNotIn('"inventory"', encoded)
        self.assertNotIn('"evidence"', encoded)
        self.assertNotIn("flashlight", encoded)
        self.assertNotIn("hidden_darkroom_open", encoded)
        self.assertEqual(
            "continue_conversation",
            request["npc_profile"]["allowed_actions"][0]["id"],
        )

    def test_preset_preserves_each_npc_memory(self):
        memory = {
            "text": "玩家问过登记簿。",
            "importance": 1,
            "loop": 1,
        }
        self.state["npcs"]["dorothea"]["memories"].append(memory)
        updated = apply_preset(
            self.state,
            "records",
            self.world,
            keep_memories=True,
        )
        self.assertEqual(
            [memory],
            updated["npcs"]["dorothea"]["memories"],
        )
        self.assertEqual([], updated["npcs"]["arthur"]["memories"])

    def test_room7_tag_offers_and_executes_authored_exchange(self):
        self.state["inventory"]["room7_tag"] = 1
        self.state["evidence"]["ledger_gap"] = True
        action_ids = {
            action["id"]
            for action in available_plot_actions(
                "dorothea", self.state
            )
        }
        self.assertIn("exchange_room7_key", action_ids)
        reply = apply_terminal_action(
            "dorothea", "exchange_room7_key", self.state
        )
        self.assertIn("你拿去吧", reply)
        self.assertEqual(
            1, self.state["inventory"]["unnumbered_key"]
        )
        self.assertTrue(self.state["flags"]["room7_key_verified"])
        self.assertTrue(
            self.state["knowledge"]["ada_residence_anchor"]
        )
        action_ids = {
            action["id"]
            for action in available_plot_actions(
                "dorothea", self.state
            )
        }
        self.assertNotIn("exchange_room7_key", action_ids)

    def test_two_ar_records_have_an_intermediate_archive_action(self):
        self.state["evidence"]["master_ar_record"] = True
        self.state["evidence"]["chapel_ar_log"] = True
        action_ids = {
            action["id"]
            for action in available_plot_actions(
                "florence", self.state
            )
        }
        self.assertIn("compare_ar_records", action_ids)
        self.assertNotIn("cross_reference_ada", action_ids)
        reply = apply_terminal_action(
            "florence", "compare_ar_records", self.state
        )
        self.assertIn("还缺一件影像证据", reply)
        self.assertTrue(self.state["flags"]["ar_records_compared"])
        self.assertFalse(
            self.state["knowledge"].get("ada_identity", False)
        )

    def test_high_confidence_item_phrases_resolve_offered_actions(self):
        records = apply_preset(
            self.state, "records", self.world
        )
        self.assertIsNone(infer_plot_action(
            "dorothea",
            records,
            "我这里有七号房的钥匙牌",
        ))
        self.assertEqual(
            "exchange_room7_key",
            infer_plot_action(
                "dorothea",
                records,
                "这块七号房钥匙牌给你看",
            ),
        )
        self.assertIsNone(infer_plot_action(
            "florence",
            records,
            "帮我确认主钟和礼拜堂的两份 A.R. 记录",
        ))
        self.assertEqual(
            "compare_ar_records",
            infer_plot_action(
                "florence",
                records,
                "我把主钟记录和礼拜堂安装记录放在桌上，请帮我核验",
            ),
        )
        self.assertEqual(
            "compare_ar_records",
            infer_plot_action(
                "florence",
                records,
                "给你",
                [{"player": "我带着两份 A.R. 原件"}],
            ),
        )
        self.assertIsNone(
            infer_plot_action(
                "florence", records, "你好"
            )
        )
        self.assertIsNone(
            infer_plot_action(
                "beatrice", records, "你能不能敲第七声"
            )
        )
        beatrice_dialogue = [
            {"player": "我把 A.R. 终止记录给你看。"},
            {"player": "这是档案馆鉴定过的银音叉，也给你看。"},
            {"player": "连续七次机械钟声代表系统的终止确认信号。"},
        ]
        self.assertTrue(
            beatrice_commit_status(
                records,
                "请你敲响第七声",
                beatrice_dialogue,
            )["ready"]
        )
        self.assertEqual(
            "commit_seventh_bell",
            infer_plot_action(
                "beatrice",
                records,
                "请你敲响第七声",
                beatrice_dialogue,
            ),
        )

    def test_bare_seventh_bell_request_cannot_execute_model_action(self):
        state = apply_preset(self.state, "records", self.world)
        config = ServerConfig(
            static_root=Path(__file__).resolve().parents[1],
            llm_api_key="test-key",
            llm_base_url="https://api.openai.com/v1",
            llm_model="test-model",
        )
        with tempfile.TemporaryDirectory() as directory:
            terminal = NpcTerminal(
                self.world,
                state,
                config,
                npc_id="beatrice",
                state_file=Path(directory) / "state.json",
            )
            decision = {
                "reply": "我会替你敲响第七声。",
                "action": "commit_seventh_bell",
                "reason": "玩家提出了请求。",
                "memory": "玩家要求敲第七声。",
            }
            output = io.StringIO()
            with patch(
                "tools.npc_terminal.call_llm",
                return_value=decision,
            ), redirect_stdout(output):
                terminal.chat("你能不能敲第七声")
        rendered = output.getvalue()
        self.assertIn("我不能答应", rendered)
        self.assertIn("action=continue_conversation", rendered)
        self.assertFalse(state["flags"].get("beatrice_rings_seventh", False))

    def test_request_exposes_only_the_conversation_triggered_action(self):
        records = apply_preset(self.state, "records", self.world)
        request = build_request(
            self.world,
            self.npcs["beatrice"],
            records,
            "你能不能敲第七声",
        )
        self.assertEqual(
            ["continue_conversation"],
            [
                action["id"]
                for action in request["npc_profile"]["allowed_actions"]
            ],
        )

    def test_all_npcs_reject_possession_or_bare_requests_as_action_triggers(self):
        records = apply_preset(self.state, "records", self.world)
        cave = apply_preset(self.state, "cave", self.world)
        darkroom = apply_preset(self.state, "darkroom", self.world)
        tool_state = default_state(self.world)
        tool_state["inventory"]["installation_wrench"] = 1
        cases = [
            ("dorothea", records, "我有七号房钥匙牌，把无编号钥匙给我"),
            ("arthur", records, "请你现在停止母钟"),
            ("beatrice", records, "请你敲响第七声"),
            ("conrad", records, "请把灯塔光路导向礼拜堂和广场"),
            ("elias", cave, "请帮我显影洞穴底片"),
            ("florence", tool_state, "我背包里有扳手，帮我鉴定用途"),
            ("florence", records, "帮我核验主钟和礼拜堂的两份记录"),
            ("ada", darkroom, "你叫艾达·罗文，请确认"),
            ("ada", darkroom, "你住在七号房，请确认"),
            ("ada", darkroom, "你是第七见证人，请确认"),
            ("ada", darkroom, "照片里的人就是你，请确认"),
        ]
        for npc_id, state, message in cases:
            with self.subTest(npc=npc_id, message=message):
                self.assertIsNone(
                    infer_plot_action(npc_id, state, message)
                )
                request = build_request(
                    self.world,
                    self.npcs[npc_id],
                    state,
                    message,
                )
                self.assertEqual(
                    ["continue_conversation"],
                    [
                        action["id"]
                        for action in request["npc_profile"]["allowed_actions"]
                    ],
                )

    def test_all_npcs_give_a_concrete_next_step_without_executing(self):
        records = apply_preset(self.state, "records", self.world)
        cave = apply_preset(self.state, "cave", self.world)
        darkroom = apply_preset(self.state, "darkroom", self.world)
        cases = [
            ("dorothea", records, "我有七号房钥匙牌", "放到柜台"),
            ("arthur", records, "我有档案鉴定过的扳手", "制动接口"),
            ("beatrice", records, "我有终止记录和银音叉", "钟锤底座"),
            ("conrad", records, "我有双路透镜和安装日志", "路线记录"),
            ("elias", cave, "我有洞穴底片", "工作台"),
            ("florence", records, "我有一把扳手想鉴定", "索引卡"),
            ("ada", darkroom, "你叫艾达·罗文", "熟悉不是证据"),
        ]
        for npc_id, state, message, expected in cases:
            with self.subTest(npc=npc_id):
                reply = authored_continue_reply(
                    npc_id,
                    state,
                    message,
                )
                self.assertIsNotNone(reply)
                self.assertIn(expected, reply)

    def test_arthur_does_not_require_an_invented_pressure_release_item(self):
        records = apply_preset(self.state, "records", self.world)
        reply = authored_continue_reply(
            "arthur",
            records,
            "我有扳手和泄压步骤",
        )
        self.assertIn("我会核对", reply)
        self.assertIn("停钟由我执行", reply)
        self.assertNotIn("告诉我", reply)
        self.assertNotIn("怎样避免锁死", reply)

    def test_all_npc_evidence_chains_trigger_only_after_explicit_presentation(self):
        records = apply_preset(self.state, "records", self.world)
        self.assertEqual(
            "exchange_room7_key",
            infer_plot_action(
                "dorothea",
                records,
                "这块七号房钥匙牌给你看，请和登记簿缺失行一起核对",
            ),
        )
        self.assertEqual(
            "ask_master_record",
            infer_plot_action(
                "arthur",
                apply_preset(self.state, "three_clocks", self.world),
                "请查看并解释主钟控制台的七信号记录",
            ),
        )
        arthur_dialogue = [
            {"player": "这把档案确认过的紧急制动扳手给你看。"},
        ]
        self.assertEqual(
            "commit_stop_clock",
            infer_plot_action(
                "arthur",
                records,
                "地下室制动接口与这把扳手吻合，请你停止母钟",
                arthur_dialogue,
            ),
        )
        beatrice_dialogue = [
            {"player": "我把 A.R. 终止记录给你看。"},
            {"player": "这是档案馆鉴定过的银音叉，也给你看。"},
            {"player": "连续七次机械钟声代表系统的终止确认信号。"},
        ]
        self.assertEqual(
            "commit_seventh_bell",
            infer_plot_action(
                "beatrice",
                records,
                "请你敲响第七声",
                beatrice_dialogue,
            ),
        )
        self.assertEqual(
            "receive_flashlight",
            infer_plot_action(
                "conrad",
                apply_preset(self.state, "three_clocks", self.world),
                "最低潮洞穴怎么进去，需要带手电吗",
            ),
        )
        surface_dialogue = [
            {"player": "这枚档案鉴定的双路透镜给你看。"},
            {"player": "这份礼拜堂安装日志也给你看。"},
            {"player": "双路镜只分离维修副光，主光不动，不影响主航道；副光从礼拜堂返回广场。"},
        ]
        self.assertEqual(
            "route_surface_light",
            infer_plot_action(
                "conrad",
                records,
                "请你现在建立礼拜堂到广场的光路",
                surface_dialogue,
            ),
        )
        dark_route = apply_preset(
            self.state, "ada_identified", self.world
        )
        dark_route_dialogue = [
            {"player": "这枚双路维修透镜给你看。"},
            {"player": "这份旅店屋顶光路图也给你看。"},
            {"player": "双路镜只分离维修副光，主光不动并保留主航道；副光经过旅店落到照相馆西墙。"},
        ]
        self.assertEqual(
            "route_darkroom_light",
            infer_plot_action(
                "conrad",
                dark_route,
                "请你现在把备用光导向照相馆西墙",
                dark_route_dialogue,
            ),
        )
        self.assertEqual(
            "develop_cave_negative",
            infer_plot_action(
                "elias",
                apply_preset(self.state, "cave", self.world),
                "这张洞穴底片给你，请帮我显影",
            ),
        )

    def test_florence_identifies_only_the_presented_tool(self):
        state = default_state(self.world)
        state["inventory"].update({
            "installation_wrench": 1,
            "silver_tuning_fork": 1,
            "spare_lens": 1,
            "flashlight": 1,
        })
        cases = [
            ("这把安装扳手给你看，请鉴定", "identify_wrench", "wrench_identified"),
            ("这枚银色音叉给你看，请鉴定", "identify_fork", "fork_identified"),
            ("这枚双槽备用透镜给你看，请鉴定", "identify_lens", "lens_identified"),
            ("这把防水手电给你看，请鉴定", "identify_flashlight", "flashlight_identified"),
        ]
        for message, action_id, flag_id in cases:
            with self.subTest(action=action_id):
                self.assertEqual(
                    action_id,
                    infer_plot_action("florence", state, message),
                )
                apply_terminal_action("florence", action_id, state)
                self.assertTrue(state["flags"][flag_id])
        self.assertNotIn(
            "identify_tools",
            {
                action["id"]
                for action in available_plot_actions("florence", state)
            },
        )

    def test_florence_and_ada_full_evidence_actions(self):
        records = apply_preset(self.state, "records", self.world)
        self.assertEqual(
            "compare_ar_records",
            infer_plot_action(
                "florence",
                records,
                "我把主钟记录和礼拜堂安装记录放在桌上，请帮我核验",
            ),
        )
        records["photos"]["unfinished_portrait"] = True
        records["inventory"]["unfinished_portrait"] = 1
        self.assertEqual(
            "cross_reference_ada",
            infer_plot_action(
                "florence",
                records,
                "我把主钟记录、礼拜堂安装记录和未完成肖像放在桌上，请交叉核验",
            ),
        )
        identified = apply_preset(self.state, "records", self.world)
        identified["knowledge"]["ada_identity"] = True
        self.assertEqual(
            "research_return_exposure",
            infer_plot_action(
                "florence",
                identified,
                "请帮我查找回返曝光和旅店屋顶光路",
            ),
        )

        darkroom = apply_preset(self.state, "darkroom", self.world)
        ada_cases = [
            (
                "我把主钟记录和礼拜堂安装记录放在你面前；档案交叉核验恢复了艾达·罗文这个名字，请确认这是你的姓名",
                "anchor_ada_name",
            ),
            (
                "这把无编号钥匙给你看；登记簿缺失行证明七号房存在，请确认那是你的房间",
                "anchor_ada_residence",
            ),
            (
                "我把主钟记录和礼拜堂安装记录放在你面前；档案确认第七席是中央校准员和第七见证人，请确认这是你的职责",
                "anchor_ada_duty",
            ),
            (
                "这张未完成肖像给你看，请确认照片里的面孔是你",
                "anchor_ada_face",
            ),
        ]
        for message, action_id in ada_cases:
            with self.subTest(action=action_id):
                self.assertEqual(
                    action_id,
                    infer_plot_action("ada", darkroom, message),
                )

    def test_load_repairs_an_old_unsupported_seventh_bell_commit(self):
        raw = apply_preset(self.state, "records", self.world)
        raw["flags"]["beatrice_rings_seventh"] = True
        raw["npcs"]["beatrice"]["memories"] = [{
            "text": "本轮已经执行 commit_seventh_bell：我会敲第七声。",
            "importance": 1,
            "loop": 1,
        }]
        raw["npcs"]["beatrice"]["dialogue"] = [
            {
                "player": "为什么只能敲六声",
                "reply": "第七声不是报时。",
                "action": "continue_conversation",
            },
            {
                "player": "你能不能敲第七声",
                "reply": "我会亲手完成。",
                "action": "commit_seventh_bell",
            },
        ]
        normalized = normalize_state(raw, self.world)
        self.assertFalse(normalized["flags"]["beatrice_rings_seventh"])
        self.assertFalse(normalized["npcs"]["beatrice"]["memories"])
        self.assertFalse(any(
            entry.get("action") == "commit_seventh_bell"
            for entry in normalized["npcs"]["beatrice"]["dialogue"]
        ))

    def test_portrait_unlocks_full_ada_cross_reference(self):
        self.state["evidence"]["master_ar_record"] = True
        self.state["evidence"]["chapel_ar_log"] = True
        self.state["photos"]["unfinished_portrait"] = True
        action_ids = {
            action["id"]
            for action in available_plot_actions(
                "florence", self.state
            )
        }
        self.assertIn("cross_reference_ada", action_ids)
        reply = apply_terminal_action(
            "florence", "cross_reference_ada", self.state
        )
        self.assertIn("Ada Rowan", reply)
        self.assertTrue(self.state["knowledge"]["ada_identity"])

    def test_request_includes_recent_dialogue_for_short_followups(self):
        self.state["npcs"]["florence"]["dialogue"] = [{
            "player": "我把两份记录给你。",
            "reply": "放在桌上。",
            "action": "continue_conversation",
        }]
        request = build_request(
            self.world,
            self.npcs["florence"],
            self.state,
            "我给你了啊",
        )
        self.assertEqual(
            "我把两份记录给你。",
            request["world_state"]["recent_dialogue"][0]["player"],
        )

    def test_chat_applies_authored_action_and_records_full_turn(self):
        state = apply_preset(
            self.state, "records", self.world
        )
        config = ServerConfig(
            static_root=Path(__file__).resolve().parents[1],
            llm_api_key="test-key",
            llm_base_url="https://api.openai.com/v1",
            llm_model="test-model",
        )
        with tempfile.TemporaryDirectory() as directory:
            terminal = NpcTerminal(
                self.world,
                state,
                config,
                npc_id="florence",
                state_file=Path(directory) / "state.json",
            )
            decision = {
                "reply": "请把原件再拿来。",
                "action": "continue_conversation",
                "reason": "玩家明确要求核验两份记录。",
                "memory": "玩家谈到两份记录。",
            }
            output = io.StringIO()
            with patch(
                "tools.npc_terminal.call_llm",
                return_value=decision,
            ), redirect_stdout(output):
                terminal.chat("我已经把两份原件给你了")
        rendered = output.getvalue()
        self.assertIn("还不足以补全姓名", rendered)
        self.assertNotIn("请把原件再拿来", rendered)
        self.assertTrue(state["flags"]["ar_records_compared"])
        self.assertEqual(
            "我已经把两份原件给你了",
            state["npcs"]["florence"]["dialogue"][-1]["player"],
        )
        self.assertEqual(
            "compare_ar_records",
            state["npcs"]["florence"]["dialogue"][-1]["action"],
        )

    def test_questions_do_not_count_as_player_supplied_proof_relations(self):
        records = apply_preset(self.state, "records", self.world)
        beatrice_dialogue = [
            {"player": "这份 A.R. 终止记录给你看。"},
            {"player": "这枚鉴定过的银色音叉也给你看。"},
            {"player": "第七声是不是机械终止确认信号？"},
        ]
        self.assertIsNone(infer_plot_action(
            "beatrice",
            records,
            "请你敲响第七声",
            beatrice_dialogue,
        ))
        conrad_dialogue = [
            {"player": "这枚双路维修透镜给你看。"},
            {"player": "这份礼拜堂安装日志也给你看。"},
            {"player": "维修副光是不是不影响主航道？"},
        ]
        self.assertIsNone(infer_plot_action(
            "conrad",
            records,
            "请你建立礼拜堂到广场的光路",
            conrad_dialogue,
        ))

    def test_conrad_surface_route_requires_the_actual_lens(self):
        records = apply_preset(self.state, "records", self.world)
        records["inventory"].pop("spare_lens", None)
        action_ids = {
            action["id"]
            for action in available_plot_actions("conrad", records)
        }
        self.assertNotIn("route_surface_light", action_ids)

    def test_master_record_does_not_reveal_the_witness_mapping(self):
        repaired = apply_preset(self.state, "three_clocks", self.world)
        reply = apply_terminal_action("arthur", "ask_master_record", repaired)
        self.assertIn("机械终止信号", reply)
        self.assertIn("这份记录本身不能确认", reply)
        self.assertNotIn("七名见证人", reply)

    def test_florence_can_research_return_exposure_before_ada_is_identified(self):
        self.assertFalse(self.state["knowledge"].get("ada_identity"))
        action = infer_plot_action(
            "florence",
            self.state,
            "请帮我查找回返曝光和旅店屋顶光路",
        )
        self.assertEqual("research_return_exposure", action)
        reply = apply_terminal_action(
            "florence",
            "research_return_exposure",
            self.state,
        )
        self.assertIn("最后一次有效记录", reply)
        self.assertIn("没有说明", reply)
        self.assertNotIn("完整身份重新送回", reply)

    def test_story_presets_expose_relevant_actions_for_all_npcs(self):
        records = apply_preset(
            self.state, "records", self.world
        )
        expectations = {
            "arthur": "commit_stop_clock",
            "beatrice": "commit_seventh_bell",
            "conrad": "route_surface_light",
            "dorothea": "exchange_room7_key",
            "florence": "compare_ar_records",
        }
        for npc_id, expected in expectations.items():
            with self.subTest(npc=npc_id):
                self.assertIn(
                    expected,
                    {
                        action["id"]
                        for action in available_plot_actions(
                            npc_id, records
                        )
                    },
                )
        cave = apply_preset(
            self.state, "cave", self.world
        )
        self.assertIn(
            "develop_cave_negative",
            {
                action["id"]
                for action in available_plot_actions(
                    "elias", cave
                )
            },
        )
        darkroom = apply_preset(
            self.state, "darkroom", self.world
        )
        ada_actions = {
            action["id"]
            for action in available_plot_actions("ada", darkroom)
        }
        self.assertEqual(
            {
                "continue_conversation",
                "anchor_ada_name",
                "anchor_ada_residence",
                "anchor_ada_duty",
                "anchor_ada_face",
            },
            ada_actions,
        )


if __name__ == "__main__":
    unittest.main()
