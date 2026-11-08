"""New-version graph round 2: moving nodes, the outline save shape, list sorts, tools and the student policy."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_graph3 import KNOW_KINDS, LIST_SORTS, move_in_tree, nest_ids, tree_ids, tree_outline  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


def _n(tid, text, kind, kids=()):
    d = {"data": {"topicId": tid, "text": text, "nodeDataType": kind, "layerIndex": 0}}
    if kids:
        d["children"] = list(kids)
    return d


ROOT = {"data": {"text": "课"}, "children": [_n(1, "A", 1, [_n(2, "a1", 0), _n(3, "a2", 0)]), _n(4, "B", 1, [_n(5, "b1", 0)]), _n(6, "D", 0)]}


def test_move_between_parents_and_order():
    new = move_in_tree(ROOT, "6", "1", "2")
    assert tree_outline(new) == "A\n  D\n  a1\n  a2\nB\n  b1"
    assert new["children"][0]["children"][0]["data"]["layerIndex"] == 2
    assert tree_outline(ROOT) == "A\n  a1\n  a2\nB\n  b1\nD"          # the input is not changed
    assert tree_outline(move_in_tree(ROOT, "2", "")) == "A\n  a2\nB\n  b1\nD\na1"
    assert nest_ids(move_in_tree(ROOT, "5", "1")) == [{"id": 1, "children": [{"id": 2}, {"id": 3}, {"id": 5}]}, {"id": 4}, {"id": 6}]
    assert sorted(tree_ids(ROOT)) == ["1", "2", "3", "4", "5", "6"]


def test_move_refusals():
    with pytest.raises(XxtError, match="分类"):
        move_in_tree(ROOT, "2", "6")                      # D is a 知识点
    with pytest.raises(XxtError, match="自己的下级"):
        move_in_tree({"data": {}, "children": [_n(1, "A", 1, [_n(2, "a", 1)])]}, "1", "2")
    with pytest.raises(XxtError, match="不在目标上级"):
        move_in_tree(ROOT, "6", "1", "5")                 # b1 is not under A
    with pytest.raises(XxtError, match="不在图谱"):
        move_in_tree(ROOT, "99", "")


def test_list_constants_follow_the_page():
    assert LIST_SORTS == {"完成率": "completeWeightRate", "掌握率": "graspWeightRate", "使用量": "citecount", "创建时间": "id"}
    assert KNOW_KINDS["事实性"] == 1 and KNOW_KINDS["元认知"] == 4


def test_tools_and_student_policy():
    import inspect

    from xuexitong_mcp import server as srv
    from xuexitong_mcp.policy import STUDENT_BASE, STUDENT_ONLY, STUDENT_OPTIONAL
    kinds = {n: k for n, k, *_ in srv.TOOLS}
    fns = {n: f for n, _, _, f in srv.TOOLS}
    teacher = {"get_knowledge_list": "read", "add_knowledge_list_point": "write", "get_knowledge_properties": "read",
               "set_knowledge_properties": "write", "get_learning_map": "read", "move_knowledge_point": "write",
               "get_question_map_settings": "read", "set_question_map_explore": "write", "get_question_map_discussion": "read",
               "post_question_map_discussion": "write"}
    assert all(kinds.get(n) == k for n, k in teacher.items()) and not set(teacher) & STUDENT_ONLY
    assert {"list_my_question_explore", "save_my_question_explore"} <= STUDENT_BASE
    assert {"list_my_question_discussion", "post_my_question_discussion"} <= STUDENT_OPTIONAL
    for n in ("save_my_question_explore", "post_my_question_discussion"):
        assert kinds[n] == "write" and "confirm_text" in inspect.signature(fns[n]).parameters
