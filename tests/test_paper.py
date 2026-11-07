"""Parallel papers: structure parsing and add/remove planning."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_paper import check_title, parse_structure, plan_subs, show_structure  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

AB = (("单选题", 1, 5.0), ("判断题", 1, 5.0))


def test_parse_both_formats():
    assert parse_structure("单选题 1，题型分值：5.0，判断题 1，题型分值：5.0") == AB
    assert parse_structure("一、 单选题（共1题，5分） 二、 判断题（共1题，5分）") == AB
    assert parse_structure("") == ()
    assert show_structure(AB) == "单选题 1 题共 5 分，判断题 1 题共 5 分"


def sub(i, st=AB):
    return {"sub_id": str(i), "title": f"子卷{i}", "structure": st}


def lib(i, st=AB):
    return {"paper_id": str(i), "title": f"试卷{i}", "structure": st}


def test_plan_ok_and_counts():
    p = plan_subs([sub(1), sub(2)], [lib(9)], ["2"])
    assert p["after"] == 2 and p["keep"] == ["子卷1"]


@pytest.mark.parametrize("cur,add,rm", [
    ([sub(1)], [lib(9, (("判断题", 1, 5.0),))], []),           # different structure
    ([sub(1)], [], ["1"]),                                       # nothing left
    ([sub(i) for i in range(20)], [lib(99)], []),               # more than 20
    ([], [lib(1, ())], []),                                      # empty paper
])
def test_plan_refuses(cur, add, rm):
    with pytest.raises(XxtError):
        plan_subs(cur, add, rm)


@pytest.mark.parametrize("t", ["", " ", "x" * 51, "试卷😀"])
def test_title_refused(t):
    with pytest.raises(XxtError):
        check_title(t)


def test_tools_registered():
    from xuexitong_mcp import server as srv
    names = {n for n, *_ in srv.TOOLS}
    assert {"get_parallel_paper", "create_parallel_paper", "update_parallel_paper"} <= names
