"""Policy layer: profiles, call budget, content notice, tutoring, advisory reviews."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import policy as P  # noqa: E402
from xuexitong_mcp import server as srv  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

TOOLS = [(n, k) for n, k, _, _ in srv.TOOLS]


def test_environment_can_only_narrow():
    assert P.effective_profile("teacher", "student") == "student"
    assert P.effective_profile("student", "teacher") == "student"
    assert P.effective_profile("reviewer", "teacher") == "reviewer"
    assert P.effective_profile("bogus", None) == "teacher"


def test_student_profile_is_minimal_and_cannot_be_widened():
    a = P.allowed_tools("student", TOOLS, ["delete_material", "publish_notice", "read_page", "reply_my_discussion"], [])
    assert a == set(P.STUDENT_BASE) | {"reply_my_discussion"}
    kinds = dict(TOOLS)
    assert not any(kinds[n] == "destructive" for n in a)
    assert not any(n.startswith(("create_", "publish_", "delete_", "insert_")) for n in a)
    assert "read_page" not in a and "list_bank_questions" not in a


def test_reviewer_is_read_only_plus_review_records():
    a = P.allowed_tools("reviewer", TOOLS, ["publish_notice"], [])
    kinds = dict(TOOLS)
    assert {"record_review_suggestion", "list_review_suggestions", "assignment_submissions", "health_check"} <= a
    assert all(kinds[n] == "read" for n in a - P.REVIEW_TOOLS) and "read_page" not in a
    assert not (a & P.STUDENT_ONLY)


def test_teacher_has_teacher_tools_not_student_ones():
    a = P.allowed_tools("teacher", TOOLS, [], ["delete_chapter"])
    assert "publish_notice" in a and "health_check" in a and "record_review_suggestion" in a
    assert not (a & P.STUDENT_ONLY) and "delete_chapter" not in a


def test_build_server_registers_only_profile_tools_and_refuses_others(tmp_path, monkeypatch):
    cfg = Config()
    cfg.profile, cfg.log_dir = "student", tmp_path
    monkeypatch.delenv("XUEXITONG_MCP_PROFILE", raising=False)
    try:
        srv.build_server(cfg)
        assert srv._state["profile"] == "student" and srv._state["allowed"] == set(P.STUDENT_BASE)
        assert cfg.min_nav_interval == 2.0 and srv._state["budget"].limit == 300
        r = srv._wrap(dict((n, f) for n, _, _, f in srv.TOOLS)["publish_notice"], "write")(course="x", title="t", content="c")
        assert r["ok"] is False and "不允许" in r["error"]
    finally:
        srv._state.update(allowed=None, budget=None, profile=None, cfg=None)


def test_budget_counts_per_day(tmp_path):
    b = P.Budget(tmp_path / "usage.json", 2)
    assert b.take() == 1 and b.take() == 2
    with pytest.raises(XxtError):
        b.take()
    assert P.Budget(tmp_path / "usage.json", 0).take() == 0


def test_read_results_carry_content_notice():
    r = srv._wrap(lambda: {"ok": True, "x": 1}, "read")()
    assert r["content_policy"] == P.CONTENT_NOTICE
    def w(confirm: bool = False):
        return {"ok": True, "dry_run": False}
    assert "content_policy" not in srv._wrap(w, "write")()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_tutor_call_and_url_rules():
    assert P.tutor_url_ok("https://tutor.example.edu/api") and P.tutor_url_ok("http://127.0.0.1:9000/x")
    assert not P.tutor_url_ok("http://tutor.example.edu/api") and not P.tutor_url_ok("https://mooc1.chaoxing.com/x")
    seen = {}

    def opener(req, timeout):
        seen.update(auth=req.get_header("Authorization"), body=json.loads(req.data.decode()))
        return _Resp(json.dumps({"reply": "先回忆定义", "mastery": 0.6, "secret": "x"}).encode())
    r = P.ask_tutor("https://tutor.example.edu/api", "tok", {"question": "q"}, opener=opener)
    assert r == {"reply": "先回忆定义", "mastery": 0.6} and seen["auth"] == "Bearer tok" and seen["body"]["question"] == "q"
    with pytest.raises(XxtError):
        P.ask_tutor("", "", {"question": "q"})

    def bad(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "x", {}, None)
    with pytest.raises(XxtError):
        P.ask_tutor("https://tutor.example.edu/api", "", {"question": "q"}, opener=bad)


def test_review_records_are_advisory(tmp_path):
    r = P.record_review(tmp_path, {"course": "助手", "assignment": "作业1", "student": "张三", "verdict": "拿不准", "reason": "看不清"}, 0.0)
    assert r["needs_human"] is True and r["why_human"]
    r2 = P.record_review(tmp_path, {"course": "助手", "assignment": "作业1", "student": "李四", "verdict": "通过", "reason": "完整"}, 0.5, rng=lambda: 0.1)
    assert r2["needs_human"] is True and r2["why_human"] == "随机抽查"
    r3 = P.record_review(tmp_path, {"course": "助手", "assignment": "作业1", "student": "王五", "verdict": "通过", "reason": "完整"}, 0.5, rng=lambda: 0.9)
    assert r3["needs_human"] is False
    assert [x["student"] for x in P.list_reviews(tmp_path, only_human=True)] == ["张三", "李四"]
    with pytest.raises(XxtError):
        P.record_review(tmp_path, {"course": "助手", "assignment": "作业1", "student": "x", "verdict": "满分", "reason": "r"}, 0)
