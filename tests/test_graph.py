"""Course graph helpers and tool registration."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_graph import graph_outline  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


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
