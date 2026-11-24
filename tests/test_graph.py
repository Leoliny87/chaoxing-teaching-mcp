"""Course graph helpers and tool registration."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_graph import graph_outline  # noqa: E402
from xuexitong_mcp.ops_graph2 import NewGraphOps  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


@pytest.mark.parametrize("repeated", [False, True])
def test_course_targets_reads_all_pages(monkeypatch, repeated):
    client = object.__new__(NewGraphOps)
    ctx = SimpleNamespace(id=1, clazz_id=2, cpi=3)
    pages = []

    def get(url, params):
        if url.endswith("/targetList"):
            page = params["pageNo"]
            pages.append(page)
            indices = range(100) if page == 1 or repeated else range(100, 166)
            return {"data": {"count": 166, "data": [{"targetId": i, "name": str(i)} for i in indices]}}
        if url.endswith("/knowledgeMap"):
            return {"data": {"list": [{"id": 165, "nodes": [{"name": "核对交接记录", "level": 2}]}]}}
        return {"data": []}

    monkeypatch.setattr(client, "_get", get)
    if repeated:
        with pytest.raises(XxtError, match="重复"):
            client.course_targets("1", c=ctx)
    else:
        targets = client.course_targets("1", c=ctx)["targets"]
        assert len(targets) == 166
        assert targets[-1]["knowledge_points"] == ["核对交接记录"]
    assert pages == [1, 2]


def test_outline_levels_from_one():
    assert graph_outline("A\n  a1\n    a11\n  a2\nB") == [(1, "A"), (2, "a1"), (3, "a11"), (2, "a2"), (1, "B")]


@pytest.mark.parametrize("bad", ["A\n    a1", "", "x" * 101, "A\x01"])
def test_outline_refused(bad):
    with pytest.raises(XxtError):
        graph_outline(bad)


def test_graph_tools_and_policy():
    from xuexitong_mcp import server as srv
    from xuexitong_mcp.policy import STUDENT_BASE
    names = {n for n, *_ in srv.TOOLS}
    assert {"get_course_graph", "add_knowledge_points", "set_knowledge_relations", "set_knowledge_visibility", "delete_knowledge_points",
            "restore_knowledge_points", "link_questions_to_knowledge", "insert_chapter_graph", "list_my_course_graph"} <= names
    assert "list_my_course_graph" in STUDENT_BASE and "get_course_graph" not in STUDENT_BASE


def test_new_graph_tools_and_policy():
    from xuexitong_mcp import server as srv
    from xuexitong_mcp.ops_graph2 import SWITCHES, para, plain
    from xuexitong_mcp.policy import STUDENT_BASE
    names = {n for n, *_ in srv.TOOLS}
    assert {"get_graph_types", "upgrade_course_graph", "set_graph_type", "set_knowledge_labels", "create_knowledge_label", "get_ideology_graph",
            "get_question_map", "save_question_map_question", "link_question_map_children", "delete_question_map_questions",
            "restore_question_map_questions", "update_question_map_level", "get_course_targets", "save_course_target",
            "delete_course_target", "create_target_label", "list_my_graph"} <= names
    assert "list_my_graph" in STUDENT_BASE and "get_question_map" not in STUDENT_BASE
    assert set(SWITCHES) == {"问题图谱", "能力图谱", "课程思政图谱"}
    assert para("a<b\nc") == "<p>a&lt;b</p><p>c</p>" and plain("<p>x&amp;y</p> <p>z</p>") == "x&y z"


def test_delete_knowledge_points_resolves_names_on_confirm(monkeypatch):
    # Regression (live 2026-11-23): the confirm path passed raw names to the client,
    # which only accepts point_id, so deleting by name falsely reported "已不在图谱".
    # The tool must resolve names -> IDs on confirm just like the preview path.
    from xuexitong_mcp import server as srv
    pts = [{"point_id": "111", "name": "甲", "parent_id": "0"},
           {"point_id": "222", "name": "乙", "parent_id": "0"}]
    got = {}

    class Fake:
        def knowledge_points(self, course, query=""):
            return pts
        def find_point(self, course, point, pts=None):
            for p in (pts if pts is not None else self.knowledge_points(course)):
                if p["name"] == point or p["point_id"] == str(point):
                    return p
            raise ValueError(point)
        def delete_knowledge_points(self, course, ids):
            got["ids"] = ids
            return {"ok": True, "deleted": ids}

    monkeypatch.setattr(srv, "client", lambda: Fake())
    monkeypatch.setattr(srv, "_check_write", lambda c: type("C", (), {"id": "1", "name": "课"})())
    out = srv.delete_knowledge_points("课", ["甲", "乙"], confirm=True)
    assert out["ok"] and got["ids"] == ["111", "222"]
