"""Interactive terminal laboratory for Time Echo's AI NPC contexts.

The tool imports the same OpenAI Responses API call used by server.py.
It intentionally rebuilds a per-NPC epistemic projection before every turn:
the editable test state is richer than the JSON sent to the model.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import ServerConfig, call_llm, load_dotenv  # noqa: E402


NPC_ORDER = [
    "arthur",
    "beatrice",
    "conrad",
    "dorothea",
    "elias",
    "florence",
    "ada",
]
CONTEXT_TEMPLATE_VERSION = "time-echo-terminal-context-v2"
MAX_CONTEXT_DIALOGUE = 8
MAX_CONTEXT_MEMORIES = 8
REPAIR_IDS = ("master", "chapel", "tide")
BOOLEAN_WORDS = {
    "1": True,
    "true": True,
    "on": True,
    "yes": True,
    "y": True,
    "是": True,
    "开": True,
    "0": False,
    "false": False,
    "off": False,
    "no": False,
    "n": False,
    "否": False,
    "关": False,
}
DEFAULT_STATE_FILE = ROOT / "tmp" / "npc-terminal-state.json"


PRESET_DESCRIPTIONS = {
    "initial": "SATURDAY 06:00；无维修、无证据、空背包",
    "three_clocks": "三座钟已修复，但尚未带着协议证据找居民",
    "records": "取得两份 A.R. 记录和三件待鉴定工具",
    "cave": "最低潮；持有手电与洞穴底片，可测试康拉德/埃利亚斯",
    "ada_identified": "肖像与两份记录已交叉核验，Ada 身份结论成立",
    "darkroom": "第二暗房开启，Ada 出现，四锚点尚未逐一确认",
    "identity_complete": "Ada 的姓名、住处、职责、面孔均已确认",
}


def load_world(path: Path = ROOT / "data" / "world.json") -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def npc_index(world: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {npc["id"]: npc for npc in world["npcs"]}


def default_state(world: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "version": 1,
        "dayLabel": "SATURDAY",
        "minute": 360,
        "loopCount": 0,
        "repairs": {repair_id: False for repair_id in REPAIR_IDS},
        "inventory": {},
        "evidence": {entry["id"]: False for entry in world["evidence"]},
        "knowledge": {},
        "flags": {},
        "photos": {},
        "npcs": {
            npc["id"]: {
                "mood": "专注",
                "status": "working",
                "regionId": npc.get("regionId", "town"),
                "placeId": npc.get("placeId", ""),
                "activity": npc.get("role", ""),
                "memories": [],
                "dialogue": [],
            }
            for npc in world["npcs"]
        },
    }


def has_item(state: Mapping[str, Any], item_id: str) -> bool:
    return int(state.get("inventory", {}).get(item_id, 0) or 0) > 0


def _context_entry_is_supported(npc_id: str, entry: Any) -> bool:
    """Drop known hallucinations from older saves before they reach the model."""

    try:
        rendered = json.dumps(entry, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(entry)
    compact = re.sub(r"\s+", "", rendered)
    if npc_id == "dorothea" and "旅店" in compact and any(
        fragment in compact
        for fragment in (
            "存在一扇一直没有编号的门",
            "确实有一扇一直没有编号的门",
            "旅店里那扇一直没有编号的门",
            "旅店内的无编号门",
        )
    ):
        return False
    if npc_id == "arthur" and any(
        fragment in compact
        for fragment in (
            "然后告诉我档案确认的操作",
            "怎样避免锁死主轮",
            "它断开哪一段机构，怎样避免锁死主轮",
            "并说明它如何在卸压状态下断开主擒纵",
        )
    ):
        return False
    if npc_id == "beatrice" and any(
        fragment in compact
        for fragment in (
            "宣告某个记录已经结束",
            "只在某项记录被宣告结束时落下",
        )
    ):
        return False
    if npc_id == "dorothea" and any(
        fragment in compact
        for fragment in (
            "要不要先喝点热的",
            "要不要我给你倒杯热水",
            "顺便把前台那三份委托单",
            "要是你是来办入住或者看委托单",
        )
    ):
        return False
    if npc_id == "florence" and any(
        fragment in compact
        for fragment in (
            "我知道你带着它们。可我还没看到原件",
            "我现在只能说“有这个可能”",
        )
    ):
        return False
    return True


def _set_many(target: MutableMapping[str, Any], values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        target[key] = value


def apply_preset(
    state: Mapping[str, Any],
    name: str,
    world: Mapping[str, Any],
    *,
    keep_memories: bool = True,
) -> Dict[str, Any]:
    if name not in PRESET_DESCRIPTIONS:
        raise ValueError(f"未知预设：{name}")
    conversation_state = {
        npc_id: {
            "memories": list(npc_state.get("memories", [])),
            "dialogue": list(npc_state.get("dialogue", [])),
        }
        for npc_id, npc_state in state.get("npcs", {}).items()
    }
    result = default_state(world)
    if name in {"three_clocks", "records", "ada_identified", "darkroom", "identity_complete"}:
        _set_many(result["repairs"], {"master": True, "chapel": True, "tide": True})
    if name in {"records", "ada_identified", "darkroom", "identity_complete"}:
        _set_many(result["evidence"], {
            "master_ar_record": True,
            "chapel_ar_log": True,
            "ledger_gap": True,
            "brake_interface": True,
        })
        _set_many(result["inventory"], {
            "installation_wrench": 1,
            "silver_tuning_fork": 1,
            "spare_lens": 1,
            "room7_tag": 1,
        })
        _set_many(result["flags"], {
            "wrench_identified": True,
            "fork_identified": True,
            "lens_identified": True,
        })
    if name == "cave":
        result["dayLabel"] = "SUNDAY"
        result["minute"] = 135
        result["repairs"]["tide"] = True
        _set_many(result["inventory"], {"flashlight": 1, "cave_negative": 1})
        result["flags"]["low_tide"] = True
    if name in {"ada_identified", "darkroom", "identity_complete"}:
        _set_many(result["inventory"], {
            "flashlight": 1,
            "cave_negative": 1,
            "unfinished_portrait": 1,
            "unnumbered_key": 1,
        })
        result["photos"]["unfinished_portrait"] = True
        _set_many(result["knowledge"], {
            "ada_identity": True,
            "ada_residence_anchor": True,
            "portrait_face_anchor": True,
            "return_exposure": True,
        })
        result["evidence"]["inn_roof_reflector"] = True
    if name in {"darkroom", "identity_complete"}:
        _set_many(result["flags"], {
            "counterweight_raised": True,
            "light_route_inn_studio": True,
            "hidden_darkroom_open": True,
        })
        result["npcs"]["ada"]["placeId"] = "hidden-darkroom"
        result["npcs"]["ada"]["status"] = "visible"
    if name == "identity_complete":
        _set_many(result["flags"], {
            "ada_name_anchored": True,
            "ada_residence_anchored": True,
            "ada_duty_anchored": True,
            "ada_face_anchored": True,
        })
    if keep_memories:
        for npc_id, entries in conversation_state.items():
            if npc_id in result["npcs"]:
                result["npcs"][npc_id]["memories"] = entries["memories"][:8]
                result["npcs"][npc_id]["dialogue"] = entries["dialogue"][-8:]
    return result


def visible_facts(npc: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    npc_id = str(npc["id"])
    facts = list(npc.get("knowledge", {}).get("public", []))
    repairs = state.get("repairs", {})
    evidence = state.get("evidence", {})
    flags = state.get("flags", {})
    photos = state.get("photos", {})
    knowledge = state.get("knowledge", {})

    if npc_id == "arthur":
        if repairs.get("master"):
            facts.append("主钟在本轮已经修复。")
        if evidence.get("master_ar_record"):
            facts.append("修复后的主钟留下 A.R. 签署的七次连续击发记录。")
        if evidence.get("brake_interface"):
            facts.append("玩家本轮检查过地下室紧急制动接口。")
        if flags.get("arthur_stops_clock"):
            facts.append("阿瑟本轮已经核验接口与扳手，并承诺亲手停钟。")
    elif npc_id == "beatrice":
        if repairs.get("chapel"):
            facts.append("礼拜堂六锤在本轮已经修复。")
        if evidence.get("chapel_ar_log"):
            facts.append("礼拜堂安装记录由 A.R. 签署，并记录独立第七锤。")
        if flags.get("beatrice_rings_seventh"):
            facts.append("贝娅特丽斯本轮已经核验证据，并承诺亲手完成第七声。")
    elif npc_id == "conrad":
        if repairs.get("tide"):
            facts.append("潮汐钟在本轮已经修复。")
        if flags.get("low_tide"):
            facts.append("现在正处于 SUNDAY 02:00–03:00 的最低潮窗口。")
        if flags.get("lens_identified"):
            facts.append("档案员已把玩家带来的双槽镜鉴定为灯塔备用镜。")
        if has_item(state, "flashlight"):
            facts.append("康拉德本轮已经把防水手电交给玩家。")
        if flags.get("light_route_inn_studio"):
            facts.append("康拉德本轮已经建立通往照相馆西墙的备用光路。")
    elif npc_id == "dorothea":
        facts.append(
            "旅店里没有无编号的门：二楼一号至六号之后，六号与八号之间"
            "只有一段没有门的空墙。"
        )
        facts.append(
            "多萝西娅不知道无编号钥匙如今能打开哪里；不得猜测旅店里另有一扇门，"
            "也不得命名任何尚未证实的钥匙用途、地点或门。"
        )
        if evidence.get("ledger_gap"):
            facts.append("玩家本轮亲眼看过旅店登记簿缺失的第七行。")
        if has_item(state, "room7_tag"):
            facts.append("玩家本轮带着七号房铜钥匙牌。")
        if flags.get("room7_key_verified"):
            facts.append("多萝西娅本轮已核验铜牌，并把无编号钥匙交给玩家。")
    elif npc_id == "elias":
        if has_item(state, "cave_negative"):
            facts.append("玩家本轮带来了退潮洞穴中的受潮底片。")
        if photos.get("unfinished_portrait"):
            facts.append("底片已按重影、反差、湖面反射三步显影成未完成肖像。")
    elif npc_id == "florence":
        if evidence.get("master_ar_record"):
            facts.append("玩家本轮带有主钟 A.R. 记录。")
        if evidence.get("chapel_ar_log"):
            facts.append("玩家本轮带有礼拜堂 A.R. 安装记录。")
        if photos.get("unfinished_portrait"):
            facts.append("玩家本轮带有已显影但身份未固定的肖像。")
        if flags.get("ar_records_compared"):
            facts.append("弗洛伦斯本轮已核验两份 A.R. 原件；它们仍缺影像证据才能补全姓名。")
        if knowledge.get("ada_identity"):
            facts.append("档案交叉核验已经恢复 Ada Rowan 的姓名与中央校准员职责。")
    elif npc_id == "ada":
        anchors = [
            ("ada_name_anchored", "姓名"),
            ("ada_residence_anchored", "住处"),
            ("ada_duty_anchored", "职责"),
            ("ada_face_anchored", "面孔"),
        ]
        known = "、".join(label for flag, label in anchors if flags.get(flag)) or "无"
        facts.append(f"当前已经共同核验的身份锚点：{known}。")
        if flags.get("ada_name_anchored"):
            facts.append("两份独立 A.R. 记录与残缺肖像已经共同确认她的姓名是 Ada Rowan。")
        elif knowledge.get("ada_identity"):
            facts.append(
                "玩家持有档案恢复的姓名结论和两份 A.R. 记录，但尚未当面与当前潜影共同核验；"
                "她不能据此自报姓名。"
            )
    return facts


CONTINUE_ACTION = {
    "id": "continue_conversation",
    "label": "只继续对话，不改变世界状态",
    "instruction": (
        "仅在本轮没有实际交付、核验、承诺或机关操作时选择。"
        "不要用它假装已经执行剧情动作。"
    ),
}


def _plot_action(action_id: str, label: str, instruction: str) -> Dict[str, str]:
    return {
        "id": action_id,
        "label": label,
        "instruction": instruction,
    }


def available_plot_actions(
    npc_id: str,
    state: Mapping[str, Any],
) -> list[Dict[str, str]]:
    """Return only actions whose fixed-script preconditions are true now."""

    actions = [copy.deepcopy(CONTINUE_ACTION)]
    repairs = state.get("repairs", {})
    evidence = state.get("evidence", {})
    flags = state.get("flags", {})
    photos = state.get("photos", {})
    knowledge = state.get("knowledge", {})

    if npc_id == "dorothea":
        if (
            has_item(state, "room7_tag")
            and evidence.get("ledger_gap")
            and not has_item(state, "unnumbered_key")
        ):
            actions.append(_plot_action(
                "exchange_room7_key",
                "核验七号房铜牌，并把柜台后的无编号钥匙交给玩家",
                "玩家把七号房铜牌实际放到柜台上时选择；仅说自己持有不能执行。",
            ))
    elif npc_id == "arthur":
        if repairs.get("master") and not evidence.get("master_ar_record"):
            actions.append(_plot_action(
                "ask_master_record",
                "读取并解释主钟七信号控制台的 A.R. 终止记录",
                "玩家请你检查已修复主钟的控制台或七信号记录时选择。",
            ))
        if (
            repairs.get("master")
            and evidence.get("brake_interface")
            and flags.get("wrench_identified")
            and has_item(state, "installation_wrench")
            and not flags.get("arthur_stops_clock")
        ):
            actions.append(_plot_action(
                "commit_stop_clock",
                "核验接口与扳手，并承诺由阿瑟亲手停钟",
                "玩家出示已鉴定扳手和制动接口证据并请求停钟时立即选择。",
            ))
    elif npc_id == "beatrice":
        if (
            repairs.get("chapel")
            and evidence.get("master_ar_record")
            and flags.get("fork_identified")
            and has_item(state, "silver_tuning_fork")
            and not flags.get("beatrice_rings_seventh")
        ):
            actions.append(_plot_action(
                "commit_seventh_bell",
                "核验终止记录与银音叉，并承诺亲手完成第七声",
                "玩家出示两项证据并请求完成第七声时立即选择。",
            ))
    elif npc_id == "conrad":
        if repairs.get("tide") and not has_item(state, "flashlight"):
            actions.append(_plot_action(
                "receive_flashlight",
                "说明最低潮维护洞，并把防水手电交给玩家",
                "玩家询问最低潮洞穴、照明或进入洞穴的方法时选择。",
            ))
        if (
            flags.get("lens_identified")
            and evidence.get("chapel_ar_log")
            and has_item(state, "spare_lens")
            and not flags.get("light_route_chapel_square")
        ):
            actions.append(_plot_action(
                "route_surface_light",
                "按安装记录建立灯塔到礼拜堂再到广场的主光路",
                "玩家出示安装记录并请求建立主光路时选择。",
            ))
        if (
            flags.get("lens_identified")
            and evidence.get("inn_roof_reflector")
            and has_item(state, "spare_lens")
            and not flags.get("light_route_inn_studio")
        ):
            actions.append(_plot_action(
                "route_darkroom_light",
                "用双路镜建立经旅店屋顶到照相馆西墙的备用光路",
                "玩家请求把备用光导向照相馆且证据齐全时选择。",
            ))
    elif npc_id == "elias":
        if has_item(state, "cave_negative") and not photos.get("unfinished_portrait"):
            actions.append(_plot_action(
                "develop_cave_negative",
                "接过洞穴底片并完成三步显影",
                "玩家出示、递交底片或明确请求显影时立即选择。",
            ))
    elif npc_id == "florence":
        tool_requirements = {
            "identify_wrench": (
                "installation_wrench",
                "wrench_identified",
                "把安装扳手放到索引卡旁鉴定",
            ),
            "identify_fork": (
                "silver_tuning_fork",
                "fork_identified",
                "把银色音叉放到索引卡旁鉴定",
            ),
            "identify_lens": (
                "spare_lens",
                "lens_identified",
                "把双槽备用镜放到索引卡旁鉴定",
            ),
            "identify_flashlight": (
                "flashlight",
                "flashlight_identified",
                "把防水手电放到索引卡旁鉴定",
            ),
        }
        for action_id, (item_id, flag_id, label) in tool_requirements.items():
            if has_item(state, item_id) and not flags.get(flag_id):
                actions.append(_plot_action(
                    action_id,
                    label,
                    "玩家当面出示这一件实物时选择；每次只鉴定实际出示的物品。",
                ))
        records_ready = bool(
            evidence.get("master_ar_record")
            and evidence.get("chapel_ar_log")
        )
        if (
            records_ready
            and not flags.get("ar_records_compared")
            and not knowledge.get("ada_identity")
        ):
            actions.append(_plot_action(
                "compare_ar_records",
                "接过并核验两份 A.R. 记录，确认共同签署者及尚缺的证据",
                "玩家出示、递交或请求核对两份 A.R. 记录时立即选择；"
                "不要再要求玩家重复出示。",
            ))
        if (
            records_ready
            and photos.get("unfinished_portrait")
            and not knowledge.get("ada_identity")
        ):
            actions.append(_plot_action(
                "cross_reference_ada",
                "把两份 A.R. 记录和残缺肖像交叉核验，恢复 Ada 身份",
                "玩家要求核验三项已经齐备的证据时立即选择。",
            ))
        if (
            not evidence.get("inn_roof_reflector")
            or not knowledge.get("return_exposure")
        ):
            actions.append(_plot_action(
                "research_return_exposure",
                "查阅回返曝光词条与旅店屋顶维护光路图",
                "玩家询问回返曝光或下一步光路时选择。",
            ))
    elif npc_id == "ada":
        records_ready = bool(
            knowledge.get("ada_identity")
            and evidence.get("master_ar_record")
            and evidence.get("chapel_ar_log")
        )
        residence_ready = bool(
            knowledge.get("ada_residence_anchor")
            and has_item(state, "unnumbered_key")
        )
        face_ready = bool(
            knowledge.get("portrait_face_anchor")
            and has_item(state, "unfinished_portrait")
        )
        if records_ready and not flags.get("ada_name_anchored"):
            actions.append(_plot_action(
                "anchor_ada_name",
                "与 Ada 共同确认两份记录上的完整姓名",
                "玩家提出用两份 A.R. 记录确认姓名时选择。",
            ))
        if residence_ready and not flags.get("ada_residence_anchored"):
            actions.append(_plot_action(
                "anchor_ada_residence",
                "与 Ada 共同确认七号房和无编号钥匙对应她的住处",
                "玩家出示钥匙并请求确认住处时选择。",
            ))
        if records_ready and not flags.get("ada_duty_anchored"):
            actions.append(_plot_action(
                "anchor_ada_duty",
                "与 Ada 共同确认中央校准员和第七见证职责",
                "玩家提出用记录确认职责时选择。",
            ))
        if face_ready and not flags.get("ada_face_anchored"):
            actions.append(_plot_action(
                "anchor_ada_face",
                "让 Ada 亲自认领未完成肖像中的面孔",
                "玩家出示肖像并请求确认面孔时选择。",
            ))
    return actions


def _conversation_parts(
    message: str,
    dialogue: Sequence[Mapping[str, Any]],
) -> tuple[list[str], str, str, str]:
    historic = [
        re.sub(r"\s+", "", str(entry.get("player", ""))).lower()
        for entry in dialogue
        if isinstance(entry, Mapping)
    ]
    current = re.sub(r"\s+", "", str(message)).lower()
    previous = historic[-1] if historic else ""
    turns = [*historic, current]
    return turns, current, previous, "".join(turns)


def _is_assertive_turn(turn: str) -> bool:
    """Questions can request an explanation, but cannot supply a proof relation."""

    return not any(
        marker in turn
        for marker in ("吗", "是不是", "是否", "难道", "为什么", "怎么会")
    )


def _was_presented(
    turns: Sequence[str],
    current: str,
    previous: str,
    object_words: Sequence[str],
) -> bool:
    presentation_words = (
        "给你看",
        "让你看",
        "给你",
        "递给",
        "交给",
        "拿去",
        "出示",
        "拿出",
        "放在你面前",
        "放在桌",
        "放柜台",
        "这是",
        "这把",
        "这枚",
        "这张",
        "这份",
        "这两份",
        "我把",
        "我带来",
        "我带了",
    )
    if any(
        any(word in turn for word in object_words)
        and any(verb in turn for verb in presentation_words)
        for turn in turns
    ):
        return True
    return (
        any(verb in current for verb in presentation_words)
        and any(word in previous for word in object_words)
    )


def _records_presented(
    turns: Sequence[str],
    current: str,
    previous: str,
) -> bool:
    both = _was_presented(
        turns,
        current,
        previous,
        ("两份a.r", "两份ar", "两份记录", "两份原件"),
    )
    master = _was_presented(
        turns,
        current,
        previous,
        ("主钟记录", "主钟a.r", "主钟ar", "终止记录"),
    )
    chapel = _was_presented(
        turns,
        current,
        previous,
        ("礼拜堂记录", "礼拜堂日志", "安装记录", "礼拜堂a.r", "礼拜堂ar"),
    )
    return both or (master and chapel)


def _conversation_action_triggered(
    action_id: str,
    state: Mapping[str, Any],
    message: str,
    dialogue: Sequence[Mapping[str, Any]],
) -> bool:
    turns, current, previous, corpus = _conversation_parts(message, dialogue)
    has_current = lambda words: any(word in current for word in words)
    asks_check = has_current((
        "帮我查",
        "帮我确认",
        "帮我核对",
        "核验",
        "对照",
        "比对",
        "看看",
        "检查",
        "鉴定",
        "认领",
    ))
    records_presented = _records_presented(turns, current, previous)

    if action_id == "exchange_room7_key":
        return _was_presented(
            turns,
            current,
            previous,
            ("七号房钥匙牌", "七号钥匙牌", "七号铜牌", "7号房钥匙牌", "7号铜牌"),
        )
    if action_id == "ask_master_record":
        return has_current(("控制台", "七信号", "主钟记录", "终止记录")) and has_current(
            ("查看", "检查", "解释", "读取", "是什么", "看看", "告诉我")
        )
    if action_id == "commit_stop_clock":
        wrench_presented = _was_presented(
            turns,
            current,
            previous,
            ("安装扳手", "制动扳手", "紧急制动扳手", "扳手"),
        )
        interface_explained = any(
            word in corpus for word in ("制动接口", "紧急制动接口", "地下室接口")
        )
        requested = has_current(("停钟", "停止母钟", "制动母钟")) and has_current(
            ("请你", "由你", "你来", "执行", "答应", "能不能", "可以")
        )
        return wrench_presented and interface_explained and requested
    if action_id == "commit_seventh_bell":
        status = beatrice_commit_status(state, message, dialogue)
        return status["ready"] and status["requested"]
    if action_id == "receive_flashlight":
        return has_current(("洞穴", "最低潮", "手电", "照明", "两点", "2点")) and has_current(
            ("怎么", "哪里", "什么时候", "进入", "进去", "给我", "借我", "需要", "带什么")
        )
    if action_id in {"route_surface_light", "route_darkroom_light"}:
        lens_presented = _was_presented(
            turns,
            current,
            previous,
            ("备用透镜", "双路透镜", "双路维修透镜", "双槽镜", "双路径维修透镜", "镜片"),
        )
        safe_split_explained = any(
            _is_assertive_turn(turn)
            and any(word in turn for word in ("副光", "双路", "维修光"))
            and any(
                phrase in turn
                for phrase in (
                    "主光不动",
                    "不关闭主光",
                    "不影响主航道",
                    "保留主航道",
                    "不会熄灭主光",
                    "不中断主光",
                )
            )
            for turn in turns
        )
        requested = has_current(("光路", "导向", "照到", "转向", "建立", "调整")) and has_current(
            ("请你", "帮我", "你来", "执行", "现在", "可以")
        )
        if action_id == "route_surface_light":
            log_presented = _was_presented(
                turns,
                current,
                previous,
                ("礼拜堂安装日志", "礼拜堂安装记录", "a.r.安装记录", "a.r安装记录"),
            )
            endpoints_explained = "礼拜堂" in corpus and "广场" in corpus
            return (
                lens_presented
                and log_presented
                and safe_split_explained
                and endpoints_explained
                and requested
            )
        route_evidence_presented = _was_presented(
            turns,
            current,
            previous,
            ("屋顶光路图", "旅店屋顶记录", "屋顶反射器记录", "回返曝光档案"),
        )
        endpoints_explained = (
            "旅店" in corpus
            and any(word in corpus for word in ("照相馆", "西墙"))
        )
        return (
            lens_presented
            and route_evidence_presented
            and safe_split_explained
            and endpoints_explained
            and requested
        )
    if action_id == "develop_cave_negative":
        negative_presented = _was_presented(
            turns,
            current,
            previous,
            ("洞穴底片", "受潮底片", "旧底片", "胶片", "底片"),
        )
        return negative_presented and has_current(("显影", "冲洗", "处理", "检查"))
    tool_words = {
        "identify_wrench": ("安装扳手", "制动扳手", "扳手"),
        "identify_fork": ("银色音叉", "银音叉", "音叉"),
        "identify_lens": ("备用透镜", "双槽镜", "镜片", "透镜"),
        "identify_flashlight": ("防水手电", "手电筒", "手电"),
    }
    if action_id in tool_words:
        return _was_presented(
            turns,
            current,
            previous,
            tool_words[action_id],
        ) and (asks_check or has_current(("这是什么", "什么用途", "做什么用")))
    if action_id == "compare_ar_records":
        return records_presented and (asks_check or _was_presented(
            turns,
            current,
            previous,
            ("两份a.r", "两份ar", "两份记录", "两份原件"),
        ))
    if action_id == "cross_reference_ada":
        portrait_presented = _was_presented(
            turns,
            current,
            previous,
            ("未完成肖像", "残缺肖像", "肖像", "照片", "影像"),
        )
        return records_presented and portrait_presented and asks_check
    if action_id == "research_return_exposure":
        return has_current(("回返曝光", "屋顶光路", "屋顶反射器")) and has_current(
            ("查", "找", "研究", "解封", "看看", "下一步")
        )
    if action_id in {"anchor_ada_name", "anchor_ada_duty"}:
        archive_link = any(word in corpus for word in ("档案", "名册", "交叉核验"))
        if action_id == "anchor_ada_name":
            requested = has_current(("艾达", "ada", "罗文", "姓名", "名字")) and has_current(
                ("你叫", "这是你的", "确认", "认领", "记起来")
            )
            return records_presented and archive_link and requested
        requested = has_current(("中央校准员", "第七见证人", "职责", "工作")) and has_current(
            ("你是", "确认", "认领", "记起来", "负责")
        )
        return records_presented and archive_link and requested
    if action_id == "anchor_ada_residence":
        key_presented = _was_presented(
            turns,
            current,
            previous,
            ("无编号钥匙", "七号钥匙", "七号房钥匙"),
        )
        residence_chain = (
            any(word in corpus for word in ("登记簿缺失", "登记簿第七行", "缺失行"))
            and any(word in corpus for word in ("七号房", "7号房"))
        )
        requested = has_current(("七号房", "7号房", "住处", "住过")) and has_current(
            ("你住", "你的房间", "确认", "认领", "记起来")
        )
        return key_presented and residence_chain and requested
    if action_id == "anchor_ada_face":
        portrait_presented = _was_presented(
            turns,
            current,
            previous,
            ("未完成肖像", "残缺肖像", "肖像", "照片", "面孔"),
        )
        requested = has_current(("肖像", "照片", "面孔", "脸")) and has_current(
            ("是你", "你的", "确认", "认领", "记起来")
        )
        return portrait_presented and requested
    return False


def infer_plot_action(
    npc_id: str,
    state: Mapping[str, Any],
    message: str,
    dialogue: Sequence[Mapping[str, Any]] = (),
) -> Optional[str]:
    """Resolve high-confidence player intent inside the offered action set."""

    actions = available_plot_actions(npc_id, state)
    actions.sort(
        key=lambda action: 0
        if action["id"] == "cross_reference_ada"
        else 1
    )
    for action in actions:
        action_id = action["id"]
        if action_id == "continue_conversation":
            continue
        if _conversation_action_triggered(
            action_id,
            state,
            message,
            dialogue,
        ):
            return action_id
    return None


def beatrice_commit_status(
    state: Mapping[str, Any],
    message: str,
    dialogue: Sequence[Mapping[str, Any]] = (),
) -> Dict[str, bool]:
    """Separate carried proof from proof actually presented to Beatrice."""

    player_turns, current, previous, _ = _conversation_parts(message, dialogue)
    record_presented = _was_presented(player_turns, current, previous, (
        "终止记录",
        "主钟记录",
        "a.r.记录",
        "a.r记录",
        "ar记录",
        "七次连续击发记录",
    ))
    fork_presented = _was_presented(
        player_turns,
        current,
        previous,
        ("银音叉", "银色音叉", "音叉", "校准器"),
    )
    protocol_explained = any(
        _is_assertive_turn(turn)
        and
        any(word in turn for word in ("连续七次", "七次机械钟声", "第七声"))
        and "终止" in turn
        and any(word in turn for word in ("确认", "信号", "机械", "协议", "程序"))
        for turn in player_turns
    )
    requested = (
        any(word in current for word in ("第七声", "第七锤", "七声"))
        and any(
            word in current
            for word in ("能不能", "请你", "由你", "你来", "敲", "完成", "执行", "答应")
        )
    )
    world_ready = (
        bool(state.get("repairs", {}).get("chapel"))
        and bool(state.get("evidence", {}).get("master_ar_record"))
        and bool(state.get("flags", {}).get("fork_identified"))
        and has_item(state, "silver_tuning_fork")
    )
    return {
        "record_presented": record_presented,
        "fork_presented": fork_presented,
        "protocol_explained": protocol_explained,
        "requested": requested,
        "ready": (
            world_ready
            and record_presented
            and fork_presented
            and protocol_explained
        ),
    }


def authored_continue_reply(
    npc_id: str,
    state: Mapping[str, Any],
    message: str,
    dialogue: Sequence[Mapping[str, Any]] = (),
) -> Optional[str]:
    _, current, _, _ = _conversation_parts(message, dialogue)
    flags = state.get("flags", {})
    request_words = ("能不能", "请你", "帮我", "给我", "由你", "你来", "执行", "答应")
    possession_words = ("我有", "我带着", "我带了", "我这里有", "在我背包", "我拿到了")

    if any(word in current for word in possession_words):
        if npc_id == "dorothea" and any(
            word in current for word in ("七号房钥匙牌", "七号钥匙牌", "七号铜牌")
        ):
            return "让我看看。把铜牌放到柜台上，我会拿它和无编号钥匙的磨损、登记簿缺行一起核对。"
        if npc_id == "arthur" and "扳手" in current:
            return (
                "把扳手放到地下室制动接口旁。我会核对型号、接口和档案说明；"
                "若三者吻合，停钟由我执行。"
            )
        if npc_id == "beatrice" and any(word in current for word in ("终止记录", "音叉", "校准器")):
            return (
                "把记录和音叉都放到钟锤底座旁。我会核对，但你还必须说明"
                "连续七次机械钟声为什么代表终止确认。"
            )
        if npc_id == "conrad" and any(word in current for word in ("透镜", "镜片", "安装日志", "光路图")):
            return (
                "把镜片和对应路线记录摊开。我要看到接收点、最终落点，"
                "还要确认维修副光不会熄灭主航道。"
            )
        if npc_id == "elias" and any(word in current for word in ("底片", "胶片")):
            return "把底片放到工作台上。我先看乳剂是否受潮、有没有重影，再决定怎么显影。"
        if npc_id == "florence" and any(
            word in current for word in ("工具", "扳手", "音叉", "透镜", "镜片", "手电")
        ):
            return "把你要鉴定的那一件放到索引卡旁。我只记录实际看到的实物，不读取整个背包。"
        if npc_id == "florence" and any(
            word in current for word in ("a.r", "ar", "主钟记录", "礼拜堂记录", "两份记录")
        ):
            return "把两份原件放到桌上并指出各自来源；我会先核对签名，再告诉你还缺什么。"

    if (
        npc_id == "dorothea"
        and not has_item(state, "unnumbered_key")
        and any(word in current for word in ("无编号钥匙", "没有编号的钥匙", "柜台钥匙"))
        and any(word in current for word in ("给我", "拿走", "交给我", "借我", "能不能"))
    ):
        return (
            "抱歉，我不能只凭一句请求把旅店钥匙交出去。"
            "如果你真找到了属于七号房的铜牌，把实物放到柜台上；我会和钥匙、登记簿一起核对。"
        )
    if (
        npc_id == "arthur"
        and not flags.get("arthur_stops_clock")
        and any(word in current for word in ("停钟", "停止母钟", "制动母钟"))
        and any(word in current for word in request_words)
    ):
        return (
            "不行。先把档案确认过的制动扳手放到地下室接口旁，让我核对实物与接口；"
            "安全操作由我负责。"
        )
    if npc_id == "beatrice" and not flags.get("beatrice_rings_seventh"):
        status = beatrice_commit_status(state, message, dialogue)
        if status["requested"] and not status["ready"]:
            if status["record_presented"] and status["fork_presented"]:
                return (
                    "东西我看过了，但你还没说明最重要的一点：为什么连续七次机械钟声"
                    "代表终止确认？在这之前，我不会碰第七锤。"
                )
            return (
                "我不能答应。第七声不属于日常报时，也不在礼拜堂现行仪式中。"
                "先让我看过 A.R. 终止记录和鉴定过的银音叉，再说明为什么那一声"
                "是机械终止确认，而不是送终仪式。"
            )
    if npc_id == "conrad":
        asks_route = (
            any(word in current for word in ("光路", "导向", "照到", "转向", "调整灯塔"))
            and any(word in current for word in request_words)
        )
        if asks_route:
            if any(word in current for word in ("照相馆", "西墙", "旅店", "备用光")):
                if not flags.get("light_route_inn_studio"):
                    return (
                        "不行。把双路维修镜和旅店屋顶光路图拿给我，再把接收点、"
                        "西墙落点以及主航道光如何保留说清楚。"
                    )
            elif not flags.get("light_route_chapel_square"):
                return (
                    "不行。我要亲眼核对双路维修镜和礼拜堂安装日志，还要确认副光"
                    "不会熄灭主航道，并能从礼拜堂返回广场。"
                )
    if (
        npc_id == "elias"
        and not state.get("photos", {}).get("unfinished_portrait")
        and any(word in current for word in ("显影", "冲洗", "处理底片"))
        and any(word in current for word in request_words)
    ):
        return (
            "可以处理，但我得先看到那张底片本身。把它放到工作台上；"
            "我会先查受潮和重影，再决定显影步骤。"
        )
    if npc_id == "florence":
        asks_tool = (
            any(word in current for word in ("工具", "扳手", "音叉", "镜片", "透镜", "手电"))
            and any(word in current for word in ("鉴定", "什么用途", "做什么用", "看看", "检查"))
        )
        if asks_tool:
            return (
                "描述不能代替实物。把要鉴定的那一件放到索引卡旁；"
                "我每次只对你实际出示的物品下结论。"
            )
        asks_records = (
            any(word in current for word in ("a.r", "ar", "两份记录", "主钟记录", "礼拜堂记录"))
            and any(word in current for word in ("核验", "对照", "比对", "帮我查", "确认"))
        )
        if asks_records and not state.get("knowledge", {}).get("ada_identity"):
            return (
                "我可以核验，但持有记录不等于我已经看过原件。"
                "把主钟记录和礼拜堂记录都放到桌上；若要补全姓名，还要把未完成肖像一并出示。"
            )
    if npc_id == "ada":
        if (
            not flags.get("ada_name_anchored")
            and any(word in current for word in ("你是谁", "你叫什么", "介绍自己"))
        ):
            return (
                "我不知道。有人叫过我，可名字到这里就断了。"
                "不要替我补上；让我看能留下来的证据。"
            )
        if (
            not flags.get("ada_name_anchored")
            and any(word in current for word in ("艾达", "ada", "罗文", "你的名字", "姓名"))
        ):
            return (
                "这个名字听起来熟悉，但熟悉不是证据。把档案恢复的姓名和两份 A.R. 原件"
                "放在我面前，让我确认那是我的签名。"
            )
        if (
            not flags.get("ada_residence_anchored")
            and any(word in current for word in ("七号房", "7号房", "你的住处", "你住"))
        ):
            return (
                "房间不是靠数字存在的。给我看钥匙、登记簿缺失行，以及七号房确实存在的证据。"
            )
        if (
            not flags.get("ada_duty_anchored")
            and any(word in current for word in ("中央校准员", "第七见证人", "你的职责", "你的工作"))
        ):
            return (
                "第七只是一个空位，不是我的职责。把两份记录和档案里的第七席结论放在一起，"
                "再告诉我为什么那个位置属于我。"
            )
        if (
            not flags.get("ada_face_anchored")
            and any(word in current for word in ("你的脸", "你的面孔", "肖像里是你", "照片里是你"))
        ):
            return (
                "你说的是一个轮廓。把未完成肖像拿给我，让它和这里留下的潜影彼此核对。"
            )
    return None


def _beatrice_dialogue_has_supported_commit(
    state: Mapping[str, Any],
    dialogue: Sequence[Mapping[str, Any]],
) -> tuple[bool, bool]:
    history: list[Mapping[str, Any]] = []
    saw_commit = False
    for entry in dialogue:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("action") == "commit_seventh_bell":
            saw_commit = True
            status = beatrice_commit_status(
                state,
                str(entry.get("player", "")),
                history,
            )
            if status["ready"] and status["requested"]:
                return True, True
        history.append(entry)
    return saw_commit, False


def apply_terminal_action(
    npc_id: str,
    action_id: str,
    state: MutableMapping[str, Any],
) -> Optional[str]:
    """Apply one offered action with authored fixed-script consequences."""

    offered = {
        action["id"] for action in available_plot_actions(npc_id, state)
    }
    if action_id == "continue_conversation":
        return None
    if action_id not in offered:
        raise ValueError(f"动作 {action_id} 的剧情条件当前并不成立")

    if action_id == "exchange_room7_key":
        state["inventory"]["unnumbered_key"] = 1
        state["flags"]["room7_key_verified"] = True
        state["knowledge"]["ada_residence_anchor"] = True
        return (
            "这块铜牌的磨损……我记得每天擦过它。"
            "柜台后的钥匙不是“没有房间”，是我们把号码忘了。你拿去吧。"
        )
    if action_id == "ask_master_record":
        state["evidence"]["master_ar_record"] = True
        return (
            "记录写的是“A.R.：七次连续击发确认终止”。"
            "它能证明七声是机械终止信号；A.R. 是谁、七路接口对应什么，"
            "这份记录本身不能确认。"
        )
    if action_id == "commit_stop_clock":
        state["flags"]["arthur_stops_clock"] = True
        state["flags"]["counterweight_raised"] = True
        return (
            "接口、档案型号和扳手都对得上。它会断开主擒纵，不是锁死主轮；"
            "安全操作由我负责。到时候由我停钟。"
            "西侧配重现在会保持升起。"
        )
    if action_id == "commit_seventh_bell":
        state["flags"]["beatrice_rings_seventh"] = True
        return (
            "终止记录与校准器相符。我不喜欢这个答案，"
            "但第七声会由我亲手完成。"
        )
    if action_id == "receive_flashlight":
        state["inventory"]["flashlight"] = 1
        state["knowledge"]["low_tide_cave_known"] = True
        return (
            "潮汐盘现在可信了。星期日两点到三点，灯塔脚下会露出旧维护洞。"
            "带上这支手电，潮回来前别在入口磨蹭。"
        )
    if action_id == "route_surface_light":
        state["flags"]["light_route_chapel_square"] = True
        state["flags"]["light_route_inn_studio"] = False
        state["flags"]["conrad_routes_light"] = True
        return (
            "记录、镜片和视线都吻合。"
            "主航道光保持不变；维修副光会经过礼拜堂反射器，再落到广场。"
        )
    if action_id == "route_darkroom_light":
        state["flags"]["light_route_inn_studio"] = True
        state["flags"]["light_route_chapel_square"] = False
        state["flags"]["conrad_routes_light"] = False
        return (
            "备用光会经过旅店屋顶落到照相馆西墙。"
            "两边都保留回程，我现在把镜片锁进副槽。"
        )
    if action_id == "develop_cave_negative":
        state["photos"]["unfinished_portrait"] = True
        state["inventory"]["unfinished_portrait"] = 1
        state["knowledge"]["portrait_face_anchor"] = True
        return (
            "先查重影，再拉反差，最后确认湖面反射。"
            "好了——乳剂里留下了一张未完成肖像，脸和 A.R. 已经能看清。"
        )
    tool_actions = {
        "identify_wrench": (
            "installation_wrench",
            (
                "wrench_identified",
                "安装扳手是母钟原设计的紧急制动扳手；"
                "它用于安全断开主擒纵机构，而不是锁死主轮。",
            ),
        ),
        "identify_fork": (
            "silver_tuning_fork",
            (
                "fork_identified",
                "银色音叉是第七锤的专用校准器。",
            ),
        ),
        "identify_lens": (
            "spare_lens",
            (
                "lens_identified",
                "双槽备用镜片属于灯塔双路维护系统。",
            ),
        ),
        "identify_flashlight": (
            "flashlight",
            (
                "flashlight_identified",
                "防水手电只是洞穴照明工具，没有协议用途。",
            ),
        ),
    }
    if action_id in tool_actions:
        item_id, (flag_id, sentence) = tool_actions[action_id]
        if not has_item(state, item_id) or state["flags"].get(flag_id):
            raise ValueError(f"动作 {action_id} 缺少待鉴定实物")
        state["flags"][flag_id] = True
        state["knowledge"][flag_id] = True
        return sentence
    if action_id == "compare_ar_records":
        state["flags"]["ar_records_compared"] = True
        return (
            "两份都是本轮原件，纸张来源和登记位置彼此独立，签名栏却都是 A.R.。"
            "这足以确认同一个人参与了主钟和礼拜堂安装，"
            "但还不足以补全姓名；交叉核验台还缺一件影像证据。"
        )
    if action_id == "cross_reference_ada":
        state["flags"]["ar_records_compared"] = True
        state["knowledge"]["ada_identity"] = True
        return (
            "两个独立地点都由 A.R. 签字，肖像背面的字母位置也一致。"
            "旧雇员索引补全为 Ada Rowan——中央校准员，第七席。"
            "现在这是结论，不是猜测。"
        )
    if action_id == "research_return_exposure":
        state["evidence"]["inn_roof_reflector"] = True
        state["knowledge"]["return_exposure"] = True
        return (
            "档案把那种白光称为“回返曝光”：它会重新投射最后一次有效记录。"
            "这里没有说明“记录”指钟表读数、人员名单，还是整个镇子的状态。"
            "附图还标出了旅店屋顶通往照相馆西墙的维护反射器。"
        )
    ada_lines = {
        "anchor_ada_name": (
            "ada_name_anchored",
            "Ada Rowan。不是缩写，也不是档案员补出的猜测。"
            "那是我在两份独立维修记录上写下的名字。",
        ),
        "anchor_ada_residence": (
            "ada_residence_anchored",
            "七号房。窗框朝湖，夜里主钟的影子会落到床尾。"
            "钥匙磨损的位置，是我每天握住它留下的。",
        ),
        "anchor_ada_duty": (
            "ada_duty_anchored",
            "中央校准员，第七见证人。"
            "我不负责让时间倒退；我负责确认七个人都能一起继续。",
        ),
        "anchor_ada_face": (
            "ada_face_anchored",
            "底片里站在主钟前的人是我。请保留重影——"
            "那不是瑕疵，是每一次被删除后仍留下的边缘。",
        ),
    }
    if action_id in ada_lines:
        flag_id, reply = ada_lines[action_id]
        state["flags"][flag_id] = True
        return reply
    raise ValueError(f"动作 {action_id} 没有终端执行器")


def _entry_is_current_loop(entry: Any, current_loop: int) -> bool:
    if not isinstance(entry, Mapping):
        return False
    try:
        return int(entry.get("loop", current_loop)) == current_loop
    except (TypeError, ValueError):
        return False


def _terminal_scene_mode(
    npc_id: str, state: Mapping[str, Any]
) -> Dict[str, Any]:
    flags = state.get("flags", {})
    flags = flags if isinstance(flags, Mapping) else {}
    if int(state.get("minute", 360)) >= 1435:
        return {
            "id": "reset_imminent",
            "trigger": "reset_warning",
            "energy": "urgent",
            "behavior_rules": ["短句", "只说此刻已知事实", "不剧透结局"],
        }
    if npc_id == "ada" and not bool(flags.get("ada_duty_anchored")):
        return {
            "id": "identity_fragment",
            "trigger": "identity_not_anchored",
            "energy": "fading",
            "behavior_rules": [
                "只使用已锚定身份片段",
                "句子可有停顿",
                "玩家说出答案不能代替证据",
            ],
        }
    return {
        "id": "working_resident",
        "trigger": "default",
        "energy": "grounded",
        "behavior_rules": [
            "先回答实际问题",
            "使用职业词汇但不口号化",
            "不在每句结尾追加建议",
        ],
    }


def _terminal_director_intent(
    allowed_actions: Sequence[Mapping[str, Any]], state: Mapping[str, Any]
) -> Dict[str, Any]:
    urgency = "foreshadow"
    priority = 20
    goal = "回应当前话题；不知道时明确不知道，不主动重复线索。"
    if int(state.get("minute", 360)) >= 1435:
        urgency = "emergency"
        priority = 100
        goal = "承认白光临近带来的当下变化，但不替玩家选择结局。"
    elif len(allowed_actions) > 1:
        urgency = "guidance"
        priority = 50
        goal = "玩家明确请求已开放动作时才提出动作；否则继续对话。"
    return {
        "goal": goal,
        "urgency": urgency,
        "priority": priority,
        "preconditions": ["npc_present", "current_loop"],
        "forbidden_moves": [
            "泄露未获得线索",
            "替玩家决定结局",
            "把持有说成已经出示",
        ],
        "ttl_turns": 1,
        "max_mentions": 1,
        "cooldown_turns": 2,
    }


def _estimate_context_tokens(value: Any) -> int:
    return max(1, (len(json.dumps(value, ensure_ascii=False)) + 2) // 3)


def compile_context(
    world: Mapping[str, Any],
    npc: Mapping[str, Any],
    state: Mapping[str, Any],
    player_message: str,
) -> Dict[str, Any]:
    """Compile the runtime-shaped request plus a local-only replay trace."""

    npc_id = str(npc["id"])
    npc_state = state.get("npcs", {}).get(npc_id, {})
    current_loop = int(state.get("loopCount", 0)) + 1
    raw_dialogue = list(npc_state.get("dialogue", []))
    recent_dialogue = [
        {
            "event_id": str(
                entry.get("event_id", f"dialogue:{npc_id}:{index}")
            )[:120],
            "player": str(entry.get("player", ""))[:400],
            "reply": str(entry.get("reply", ""))[:600],
            "action": str(
                entry.get("action", "continue_conversation")
            )[:120],
        }
        for index, entry in enumerate(raw_dialogue)
        if isinstance(entry, Mapping)
        and _entry_is_current_loop(entry, current_loop)
        if _context_entry_is_supported(npc_id, entry)
    ][-MAX_CONTEXT_DIALOGUE:]
    raw_memories = list(npc_state.get("memories", []))
    memories = [
        {
            "memory_id": str(
                entry.get("memory_id", f"memory:{npc_id}:{index}")
            )[:120],
            "subjective_text": str(
                entry.get("subjective_text", entry.get("text", ""))
            )[:500],
            "event_ref": str(entry.get("event_ref", ""))[:120],
            "salience": min(1.0, max(0.0, float(entry.get("salience", 1.0)))),
            "valence": str(entry.get("valence", "neutral"))[:30],
            "tier": "current_loop",
            "truth_status": "subjective_recollection",
            "source": "dialogue_event",
        }
        for index, entry in enumerate(raw_memories)
        if isinstance(entry, Mapping)
        and _entry_is_current_loop(entry, current_loop)
        and _context_entry_is_supported(npc_id, entry)
        and str(entry.get("subjective_text", entry.get("text", ""))).strip()
    ][:MAX_CONTEXT_MEMORIES]
    triggered_action = infer_plot_action(
        npc_id,
        state,
        player_message,
        recent_dialogue,
    )
    allowed_actions = [
        action
        for action in available_plot_actions(npc_id, state)
        if action["id"] == "continue_conversation"
        or action["id"] == triggered_action
    ]
    relationship = 50
    profile_id = npc.get("id")
    profile_name = npc.get("name")
    profile_role = npc.get("role")
    profile_goal = npc.get("goal")
    profile_concern = npc.get("concern")
    state_flags = state.get("flags", {})
    if npc_id == "ada" and not state_flags.get("ada_name_anchored"):
        profile_id = "hidden_figure"
        profile_name = "暗房中的潜影"
        profile_role = "身份尚未固定的人形潜影"
    elif npc_id == "ada" and not state_flags.get("ada_duty_anchored"):
        profile_id = "hidden_figure"
        profile_role = "身份仍在恢复的暗房潜影"
    if npc_id == "ada" and not state_flags.get("ada_duty_anchored"):
        profile_goal = "弄清自己缺失的姓名、住处、职责和面孔，并让外部证据逐项固定这些记忆"
        profile_concern = "害怕所有人最终接受一个从未有过她的世界，但无法说明自己为何被删除"
    public_facts = visible_facts(npc, state)
    known_beliefs = [
        {
            "belief_id": f"npc:{npc_id}:visible:{index}",
            "content": str(fact)[:300],
            "truth_status": "known",
            "confidence": 1.0,
            "source": "npc_visible_projection",
        }
        for index, fact in enumerate(public_facts[:24])
    ]
    scene_mode = _terminal_scene_mode(npc_id, state)
    relationship_state = {
        "level": str(npc_state.get("relationshipLevel", "stranger")),
        "trust": relationship,
        "fear": 20,
        "debt": 0,
        "source": "authoritative_relationship_projection",
    }
    profile = {
        "id": profile_id,
        "name": profile_name,
        "role": profile_role,
        "traits": copy.deepcopy(npc.get("traits", [])),
        "goal": profile_goal,
        "voice": npc.get("voice"),
        "concern": profile_concern,
        "persona_core": {
            "identity": f"{profile_name} · {profile_role}",
            "long_term_goal": profile_goal,
            "default_strategy": profile_concern,
            "voice": npc.get("voice"),
            "stable_boundaries": [
                "不把玩家跨轮记忆当作本轮证据",
                "不读取其他 NPC 的记忆",
                "不从物品名称推断隐藏地点",
            ],
        },
        "active_scene_mode": scene_mode,
        "knowledge": {
            "public": public_facts,
            "residual": copy.deepcopy(
                npc.get("knowledge", {}).get("suggestive", [])
            ),
            "known_beliefs": known_beliefs,
        },
        "relationship_state": relationship_state,
        "allowed_actions": allowed_actions,
        "secretTrust": 65,
        "relationship": relationship,
        "conversation_intent": "custom",
        "may_reveal_secret": False,
        "current_state": {
            "mood": npc_state.get("mood"),
            "status": npc_state.get("status"),
            "region_id": npc_state.get("regionId"),
            "place_id": npc_state.get("placeId"),
            "activity": (
                "试图辨认残缺记忆"
                if npc_id == "ada" and not state_flags.get("ada_duty_anchored")
                else npc_state.get("activity")
            ),
            "action_id": npc_state.get("actionId"),
        },
    }
    director_intent = _terminal_director_intent(allowed_actions, state)
    place_id = str(npc_state.get("placeId", ""))
    world_state = {
        "day": state.get("dayLabel", "SATURDAY"),
        "minute": int(state.get("minute", 360)),
        "loop": current_loop,
        "snapshot_version": int(state.get("loopCount", 0)) * 1440
        + int(state.get("minute", 360)),
        "current_scene": {
            "place_id": place_id,
            "place_name": place_id,
            "npc_present": True,
            "world_time": (
                f"{state.get('dayLabel', 'SATURDAY')} "
                f"{int(state.get('minute', 360)) // 60:02d}:"
                f"{int(state.get('minute', 360)) % 60:02d}"
            ),
        },
        "story_context": {
            "public": copy.deepcopy(
                world.get("storyContext", {}).get("publicFacts", [])
            )
        },
        "repairs": {
            repair_id: bool(state.get("repairs", {}).get(repair_id))
            for repair_id in REPAIR_IDS
        },
        # Private engine flags are converted to explicit NPC-visible facts above.
        "flags": {},
        "conversation_context": {
            "intent": "custom",
            "relationship": relationship,
            "lowest_metric": None,
            "active_flags": [],
            "epistemic_mode": None,
            "shared_current_loop_evidence": [],
            "player_remembered_only": False,
        },
        "recent_dialogue": copy.deepcopy(recent_dialogue),
        "director_intent": director_intent,
    }
    request = {
        "npc_profile": profile,
        "world_state": world_state,
        "player_message": str(player_message)[:2000],
        "memories": copy.deepcopy(memories),
    }
    included_ids = [item["belief_id"] for item in known_beliefs]
    included_ids.extend(item["memory_id"] for item in memories)
    dropped = []
    old_dialogue_count = max(0, len(raw_dialogue) - len(recent_dialogue))
    old_memory_count = max(0, len(raw_memories) - len(memories))
    if old_dialogue_count:
        dropped.append(
            {
                "partition": "recent_dialogue",
                "reason": "old_loop_unsupported_or_quota",
                "count": old_dialogue_count,
            }
        )
    if old_memory_count:
        dropped.append(
            {
                "partition": "memories",
                "reason": "old_loop_unsupported_or_quota",
                "count": old_memory_count,
            }
        )
    trace = {
        "trace_id": (
            f"loop:{current_loop}:npc:{npc_id}:turn:{len(recent_dialogue) + 1}"
        ),
        "template_version": CONTEXT_TEMPLATE_VERSION,
        "snapshot_version": world_state["snapshot_version"],
        "included_ids": included_ids,
        "dropped": dropped,
        "partition_token_estimates": {
            "persona": _estimate_context_tokens(profile["persona_core"]),
            "scene": _estimate_context_tokens(world_state["current_scene"]),
            "beliefs": _estimate_context_tokens(known_beliefs),
            "memories": _estimate_context_tokens(memories),
            "recent_dialogue": _estimate_context_tokens(recent_dialogue),
            "director_intent": _estimate_context_tokens(director_intent),
        },
        "hard_filters": [
            "npc_id",
            "current_loop",
            "npc_visible_facts",
            "hard_action_prerequisites",
        ],
    }
    return {"request": request, "trace": trace}


def build_request(
    world: Mapping[str, Any],
    npc: Mapping[str, Any],
    state: Mapping[str, Any],
    player_message: str,
) -> Dict[str, Any]:
    """Compatibility wrapper returning only the model-visible request."""

    return compile_context(world, npc, state, player_message)["request"]


def format_clock(state: Mapping[str, Any]) -> str:
    minute = int(state.get("minute", 0)) % 1440
    return f"{state.get('dayLabel', 'SATURDAY')} {minute // 60:02d}:{minute % 60:02d}"


def parse_boolean(value: str) -> bool:
    try:
        return BOOLEAN_WORDS[value.strip().lower()]
    except KeyError as exc:
        raise ValueError("布尔值请使用 on/off、true/false 或 是/否") from exc


def normalize_state(raw: Any, world: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("状态文件的根必须是 JSON 对象")
    result = default_state(world)
    day = str(raw.get("dayLabel", result["dayLabel"])).upper()
    if day not in {"SATURDAY", "SUNDAY"}:
        raise ValueError("dayLabel 只能是 SATURDAY 或 SUNDAY")
    result["dayLabel"] = day
    result["minute"] = max(0, min(1439, int(raw.get("minute", 360))))
    result["loopCount"] = max(0, int(raw.get("loopCount", 0)))
    for bucket in ("repairs", "inventory", "evidence", "knowledge", "flags", "photos"):
        value = raw.get(bucket, {})
        if not isinstance(value, Mapping):
            raise ValueError(f"{bucket} 必须是 JSON 对象")
        if bucket == "inventory":
            result[bucket].update(
                {str(key): max(0, int(count)) for key, count in value.items()}
            )
        else:
            result[bucket].update(
                {str(key): bool(enabled) for key, enabled in value.items()}
            )
    raw_npcs = raw.get("npcs", {})
    if not isinstance(raw_npcs, Mapping):
        raise ValueError("npcs 必须是 JSON 对象")
    for npc_id, base_npc_state in result["npcs"].items():
        loaded = raw_npcs.get(npc_id, {})
        if not isinstance(loaded, Mapping):
            continue
        for key in ("mood", "status", "regionId", "placeId", "activity", "actionId"):
            if key in loaded:
                base_npc_state[key] = loaded[key]
        memories = loaded.get("memories", [])
        if isinstance(memories, list):
            base_npc_state["memories"] = copy.deepcopy([
                entry
                for entry in memories
                if _context_entry_is_supported(npc_id, entry)
            ][:8])
        dialogue = loaded.get("dialogue", [])
        if isinstance(dialogue, list):
            base_npc_state["dialogue"] = copy.deepcopy([
                entry
                for entry in dialogue
                if _context_entry_is_supported(npc_id, entry)
            ][-8:])
    beatrice_state = result["npcs"]["beatrice"]
    saw_commit, supported_commit = _beatrice_dialogue_has_supported_commit(
        result,
        beatrice_state["dialogue"],
    )
    if (
        result["flags"].get("beatrice_rings_seventh")
        and saw_commit
        and not supported_commit
    ):
        result["flags"]["beatrice_rings_seventh"] = False
        beatrice_state["memories"] = [
            entry
            for entry in beatrice_state["memories"]
            if "commit_seventh_bell" not in json.dumps(entry, ensure_ascii=False)
        ]
        beatrice_state["dialogue"] = [
            entry
            for entry in beatrice_state["dialogue"]
            if not (
                isinstance(entry, Mapping)
                and entry.get("action") == "commit_seventh_bell"
            )
        ]
    return result


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_state(path: Path, world: Mapping[str, Any]) -> Dict[str, Any]:
    return normalize_state(json.loads(path.read_text(encoding="utf-8")), world)


def _enabled_ids(bucket: Mapping[str, Any]) -> list[str]:
    return [str(key) for key, value in bucket.items() if value]


class NpcTerminal:
    def __init__(
        self,
        world: Mapping[str, Any],
        state: Dict[str, Any],
        config: ServerConfig,
        *,
        npc_id: str = "arthur",
        dry_run: bool = False,
        state_file: Path = DEFAULT_STATE_FILE,
    ) -> None:
        self.world = world
        self.npcs = npc_index(world)
        self.state = state
        self.config = config
        self.current_npc_id = npc_id
        self.dry_run = dry_run
        self.state_file = state_file
        self.last_message = "请按当前状态介绍你知道的情况。"
        self.last_context_trace: Dict[str, Any] = {}
        self.items = {entry["id"]: entry for entry in world["items"]}
        self.evidence = {entry["id"]: entry for entry in world["evidence"]}

    @property
    def current_npc(self) -> Dict[str, Any]:
        return self.npcs[self.current_npc_id]

    def banner(self) -> None:
        mode = "DRY-RUN（不调用 API）" if self.dry_run else (
            f"OpenAI {self.config.llm_model}"
            if self.config.llm_configured
            else "未配置 API Key（仍可检查上下文）"
        )
        print("\nTIME ECHO · AI NPC 状态实验台")
        print(f"模式：{mode}")
        print("输入 /help 查看命令；直接输入文字即可与当前 NPC 对话。")
        self.print_npcs()
        self.print_state(compact=True)

    def print_npcs(self) -> None:
        hidden_ada = not self.state.get("flags", {}).get("hidden_darkroom_open")
        print("\nNPC：")
        for number, npc_id in enumerate(NPC_ORDER, start=1):
            npc = self.npcs[npc_id]
            marker = ">" if npc_id == self.current_npc_id else " "
            availability = (
                " [剧情中尚不可见，测试仍允许]"
                if npc_id == "ada" and hidden_ada
                else ""
            )
            print(
                f" {marker} {number}. {npc_id:<9} {npc['name']} · "
                f"{npc['role']}{availability}"
            )

    def print_state(self, *, compact: bool = False) -> None:
        inventory = [
            f"{self.items.get(item_id, {}).get('name', item_id)}×{count}"
            for item_id, count in self.state["inventory"].items()
            if int(count or 0) > 0
        ]
        repairs = _enabled_ids(self.state["repairs"])
        print(
            f"\n状态：{format_clock(self.state)} · "
            f"第 {self.state['loopCount'] + 1} 轮"
        )
        print(f"  维修：{', '.join(repairs) or '无'}")
        print(f"  背包：{', '.join(inventory) or '空'}")
        if not compact:
            for label, bucket in (
                ("证据", "evidence"),
                ("知识", "knowledge"),
                ("旗标", "flags"),
                ("照片", "photos"),
            ):
                print(
                    f"  {label}："
                    f"{', '.join(_enabled_ids(self.state[bucket])) or '无'}"
                )
        facts = visible_facts(self.current_npc, self.state)
        print(f"  当前 NPC 可知事实（{len(facts)}）：")
        for fact in facts:
            print(f"    - {fact}")
        actions = available_plot_actions(
            self.current_npc_id, self.state
        )[1:]
        print("  世界条件已满足的候选动作（仍需在对话中实际出示/说明）：")
        if actions:
            for action in actions:
                print(f"    - {action['id']}：{action['label']}")
        else:
            print("    - 无（只能继续对话）")

    def print_context(self, message: Optional[str] = None) -> None:
        compilation = compile_context(
            self.world,
            self.current_npc,
            self.state,
            message or self.last_message,
        )
        request = compilation["request"]
        self.last_context_trace = compilation["trace"]
        print(json.dumps(request, ensure_ascii=False, indent=2))
        print("\n[LOCAL TRACE · 不发送给模型]")
        print(json.dumps(self.last_context_trace, ensure_ascii=False, indent=2))

    def print_facts(self) -> None:
        print("\n各 NPC 当前认知投影：")
        for npc_id in NPC_ORDER:
            npc = self.npcs[npc_id]
            print(f"\n[{npc_id}] {npc['name']}")
            for fact in visible_facts(npc, self.state):
                print(f"  - {fact}")

    def _fact_snapshot(self) -> Dict[str, list[str]]:
        return {
            npc_id: visible_facts(self.npcs[npc_id], self.state)
            for npc_id in NPC_ORDER
        }

    def _report_fact_changes(
        self, before: Mapping[str, Sequence[str]]
    ) -> None:
        changes = []
        for npc_id in NPC_ORDER:
            old = set(before.get(npc_id, []))
            new = set(visible_facts(self.npcs[npc_id], self.state))
            changes.extend(("+", npc_id, fact) for fact in new - old)
            changes.extend(("-", npc_id, fact) for fact in old - new)
        if not changes:
            print("  NPC 认知投影未改变（该状态可能只影响机关或后续流程）。")
            return
        print("  NPC 认知投影变化：")
        for sign, npc_id, fact in changes:
            print(f"    {sign} [{npc_id}] {fact}")

    def _select_npc(self, selector: str) -> None:
        value = selector.strip().lower()
        if value.isdigit() and 1 <= int(value) <= len(NPC_ORDER):
            value = NPC_ORDER[int(value) - 1]
        if value not in self.npcs:
            raise ValueError("NPC 不存在；使用 /npc 查看列表")
        self.current_npc_id = value
        npc = self.current_npc
        print(f"当前 NPC：{npc['name']}（{npc['role']}）")
        if (
            value == "ada"
            and not self.state["flags"].get("hidden_darkroom_open")
        ):
            print("提示：当前剧情状态中 Ada 尚不可见；这是越阶段的上下文测试。")
        for fact in visible_facts(npc, self.state):
            print(f"  - {fact}")
        actions = available_plot_actions(value, self.state)[1:]
        if actions:
            print("  世界条件已满足的候选动作（仍需在对话中实际出示/说明）：")
            for action in actions:
                print(f"    - {action['id']}：{action['label']}")

    def _list_named(
        self,
        source: Mapping[str, Mapping[str, Any]],
        bucket: str,
    ) -> None:
        for entry_id, entry in source.items():
            default = 0 if bucket == "inventory" else False
            current = self.state[bucket].get(entry_id, default)
            print(f"  {entry_id:<24} {entry.get('name', '')} [{current}]")

    def _set_time(self, day: str, value: str) -> None:
        normalized_day = day.upper()
        aliases = {
            "SAT": "SATURDAY",
            "星期六": "SATURDAY",
            "SUN": "SUNDAY",
            "星期日": "SUNDAY",
        }
        normalized_day = aliases.get(normalized_day, normalized_day)
        if normalized_day not in {"SATURDAY", "SUNDAY"}:
            raise ValueError("日期只能是 SATURDAY/SUNDAY（也接受 SAT/SUN）")
        try:
            hour_text, minute_text = value.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (ValueError, TypeError) as exc:
            raise ValueError("时间格式应为 HH:MM") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("时间超出 00:00–23:59")
        self.state["dayLabel"] = normalized_day
        self.state["minute"] = hour * 60 + minute
        self.state["flags"]["low_tide"] = (
            normalized_day == "SUNDAY" and hour == 2
        )

    def print_help(self) -> None:
        print(
            """
命令：
  /npc [编号|id]                 查看/选择 NPC
  /state                         查看完整测试状态与当前 NPC 可知事实
  /facts                         比较所有 NPC 的认知投影
  /context [可选消息]            查看下一次实际发送给 OpenAI 的 JSON
  /preset [名称]                 查看/应用剧情阶段预设
  /item [id count]               查看/修改背包数量，0 表示移除
  /evidence [id on|off]          查看/修改证据
  /repair [master|chapel|tide on|off]
  /flag <id> <on|off>            修改剧情旗标
  /knowledge <id> <on|off>       修改跨步骤结论
  /photo <id> <on|off>           修改照片处理状态
  /time <SATURDAY|SUNDAY> <HH:MM>
  /memory [clear]                查看/清空当前 NPC 的最近记忆
  /save [路径]                   保存状态
  /load [路径]                   载入状态
  /reset [all]                   重置世界；all 同时清空 NPC 记忆
  /quit                          退出

直接输入普通文字会重新计算当前 NPC 上下文后再对话。
""".strip()
        )

    def _handle_mutation(self, command: str, args: list[str]) -> None:
        before = self._fact_snapshot()
        if command == "preset":
            if len(args) != 1 or args[0] not in PRESET_DESCRIPTIONS:
                raise ValueError("使用 /preset 查看有效名称")
            self.state = apply_preset(
                self.state, args[0], self.world, keep_memories=True
            )
            print(
                f"已应用预设 {args[0]}："
                f"{PRESET_DESCRIPTIONS[args[0]]}"
            )
        elif command == "item":
            if len(args) != 2 or args[0] not in self.items:
                raise ValueError("用法：/item <有效物品 id> <非负数量>")
            count = int(args[1])
            if count < 0:
                raise ValueError("物品数量不能为负")
            if count:
                self.state["inventory"][args[0]] = count
            else:
                self.state["inventory"].pop(args[0], None)
            print(f"背包：{self.items[args[0]]['name']} = {count}")
        elif command == "evidence":
            if len(args) != 2 or args[0] not in self.evidence:
                raise ValueError("用法：/evidence <有效证据 id> <on|off>")
            self.state["evidence"][args[0]] = parse_boolean(args[1])
            print(
                f"证据：{self.evidence[args[0]]['name']} = "
                f"{self.state['evidence'][args[0]]}"
            )
        elif command == "repair":
            if len(args) != 2 or args[0] not in REPAIR_IDS:
                raise ValueError(
                    "用法：/repair <master|chapel|tide> <on|off>"
                )
            self.state["repairs"][args[0]] = parse_boolean(args[1])
            print(f"维修：{args[0]} = {self.state['repairs'][args[0]]}")
        elif command in {"flag", "knowledge", "photo"}:
            if len(args) != 2:
                raise ValueError(f"用法：/{command} <id> <on|off>")
            bucket = "photos" if command == "photo" else command
            self.state[bucket][args[0]] = parse_boolean(args[1])
            print(f"{bucket}：{args[0]} = {self.state[bucket][args[0]]}")
        elif command == "time":
            if len(args) != 2:
                raise ValueError(
                    "用法：/time <SATURDAY|SUNDAY> <HH:MM>"
                )
            self._set_time(args[0], args[1])
            print(f"时间：{format_clock(self.state)}")
        elif command == "reset":
            if len(args) > 1 or (
                args and args[0].lower() != "all"
            ):
                raise ValueError("用法：/reset 或 /reset all")
            clear_memories = bool(args)
            self.state = apply_preset(
                self.state,
                "initial",
                self.world,
                keep_memories=not clear_memories,
            )
            print(
                "世界已重置；NPC 记忆也已清空。"
                if clear_memories
                else "世界已重置；NPC 记忆保留。"
            )
        self._report_fact_changes(before)

    def handle_command(self, line: str) -> bool:
        try:
            parts = shlex.split(line[1:])
        except ValueError as exc:
            print(f"命令解析失败：{exc}")
            return True
        if not parts:
            return True
        command, args = parts[0].lower(), parts[1:]
        try:
            if command in {"quit", "exit", "q"}:
                return False
            if command in {"help", "h", "?"}:
                self.print_help()
            elif command == "npc":
                self._select_npc(args[0]) if args else self.print_npcs()
            elif command == "state":
                self.print_state()
            elif command == "facts":
                self.print_facts()
            elif command == "context":
                self.print_context(" ".join(args) if args else None)
            elif command == "preset" and not args:
                for name, description in PRESET_DESCRIPTIONS.items():
                    print(f"  {name:<18} {description}")
            elif command == "item" and not args:
                self._list_named(self.items, "inventory")
            elif command == "evidence" and not args:
                self._list_named(self.evidence, "evidence")
            elif command == "repair" and not args:
                for repair_id in REPAIR_IDS:
                    print(
                        f"  {repair_id:<8} "
                        f"{self.state['repairs'][repair_id]}"
                    )
            elif command == "memory":
                npc_state = self.state["npcs"][self.current_npc_id]
                entries = npc_state["memories"]
                if args and args[0].lower() == "clear":
                    entries.clear()
                    npc_state["dialogue"].clear()
                    print("当前 NPC 记忆和连续对话历史已清空。")
                elif args:
                    raise ValueError("用法：/memory 或 /memory clear")
                elif entries:
                    for index, entry in enumerate(entries, start=1):
                        print(f"  {index}. {entry}")
                    if npc_state["dialogue"]:
                        print("  最近连续对话：")
                        for turn in npc_state["dialogue"]:
                            print(
                                f"    你：{turn.get('player', '')}\n"
                                f"    NPC：{turn.get('reply', '')}"
                            )
                else:
                    print("当前 NPC 没有终端会话记忆。")
            elif command == "save":
                path = Path(args[0]) if args else self.state_file
                save_state(path, self.state)
                print(f"已保存：{path.resolve()}")
            elif command == "load":
                path = Path(args[0]) if args else self.state_file
                self.state = load_state(path, self.world)
                print(f"已载入：{path.resolve()}")
                self.print_state(compact=True)
            elif command in {
                "preset",
                "item",
                "evidence",
                "repair",
                "flag",
                "knowledge",
                "photo",
                "time",
                "reset",
            }:
                self._handle_mutation(command, args)
            else:
                print("未知命令。输入 /help 查看帮助。")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"操作失败：{exc}")
        return True

    def chat(self, message: str) -> None:
        cleaned = message.strip()
        if not cleaned:
            return
        self.last_message = cleaned
        compilation = compile_context(
            self.world, self.current_npc, self.state, cleaned
        )
        request = compilation["request"]
        self.last_context_trace = compilation["trace"]
        if self.dry_run:
            print("\n[DRY-RUN] 将发送以下上下文；未调用 API：")
            print(json.dumps(request, ensure_ascii=False, indent=2))
            print("\n[LOCAL TRACE · 不发送给模型]")
            print(json.dumps(self.last_context_trace, ensure_ascii=False, indent=2))
            return
        if not self.config.llm_configured:
            print(
                "尚未配置 OPENAI_API_KEY；"
                "可先使用 /context 或以 --dry-run 启动。"
            )
            print(
                "配置方法：复制 .env.example 为 .env，"
                "并只在服务器/本机填写 Key。"
            )
            return
        print(f"\n{self.current_npc['name']} 正在思考……")
        try:
            decision = call_llm(self.config, request)
        except Exception as exc:
            print(
                f"调用失败（{type(exc).__name__}）。"
                "未写入 NPC 记忆，请检查网络和 OpenAI 配置。"
            )
            return
        npc_state = self.state["npcs"][self.current_npc_id]
        inferred_action = infer_plot_action(
            self.current_npc_id,
            self.state,
            cleaned,
            npc_state["dialogue"],
        )
        resolved_action = inferred_action or "continue_conversation"
        before = self._fact_snapshot()
        try:
            authored_reply = apply_terminal_action(
                self.current_npc_id,
                resolved_action,
                self.state,
            )
        except ValueError as exc:
            print(f"动作被剧情规则拒绝：{exc}")
            return
        fixed_continue_reply = authored_continue_reply(
            self.current_npc_id,
            self.state,
            cleaned,
            npc_state["dialogue"],
        )
        final_reply = authored_reply or fixed_continue_reply or decision["reply"]
        action_reason = (
            "剧情前置条件和本轮对话触发均已由本地规则验证。"
            if authored_reply
            else "本轮没有通过剧情动作的对话触发门槛。"
            if fixed_continue_reply
            else decision["reason"]
        )
        print(f"{self.current_npc['name']}：{final_reply}")
        print(
            f"[action={resolved_action}; "
            f"reason={action_reason}]"
        )
        if authored_reply:
            self._report_fact_changes(before)
        memory = {
            "text": (
                f"本轮已经执行 {resolved_action}：{final_reply}"
                if authored_reply
                else decision["memory"]
            ),
            "importance": 1,
            "loop": self.state["loopCount"] + 1,
        }
        entries = npc_state["memories"]
        entries.insert(0, memory)
        del entries[8:]
        npc_state["dialogue"].append({
            "player": cleaned,
            "reply": final_reply,
            "action": resolved_action,
            "loop": self.state["loopCount"] + 1,
        })
        del npc_state["dialogue"][:-8]
        try:
            save_state(self.state_file, self.state)
            print(
                f"[已写入该 NPC 记忆并自动保存至 "
                f"{self.state_file}]"
            )
        except OSError:
            print(
                "[已写入该 NPC 记忆，但自动保存失败；"
                "可稍后使用 /save]"
            )

    def run(self) -> None:
        self.banner()
        while True:
            try:
                prompt = (
                    f"\n[{format_clock(self.state)} | "
                    f"{self.current_npc_id}] > "
                )
                line = input(prompt)
            except (EOFError, KeyboardInterrupt):
                print("\n退出状态实验台。")
                break
            if line.lstrip().startswith("/"):
                if not self.handle_command(line.lstrip()):
                    print("退出状态实验台。")
                    break
            else:
                self.chat(line)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Select Time Echo NPCs and test state-aware OpenAI contexts"
        )
    )
    parser.add_argument("--npc", choices=NPC_ORDER, default="arthur")
    parser.add_argument(
        "--preset",
        choices=PRESET_DESCRIPTIONS,
        default="initial",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
    )
    parser.add_argument(
        "--load-state",
        action="store_true",
        help="load --state-file on startup",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print context and never call OpenAI",
    )
    parser.add_argument(
        "--once",
        metavar="MESSAGE",
        help="send one message and exit",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except OSError:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        world = load_world()
        load_dotenv(ROOT / ".env")
        config = ServerConfig.from_env(static_root=ROOT)
        if args.load_state:
            state = load_state(args.state_file, world)
        else:
            state = apply_preset(
                default_state(world), args.preset, world
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    terminal = NpcTerminal(
        world,
        state,
        config,
        npc_id=args.npc,
        dry_run=args.dry_run,
        state_file=args.state_file,
    )
    if args.once is not None:
        terminal.chat(args.once)
    else:
        terminal.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
