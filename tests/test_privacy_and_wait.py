"""Regression tests for the four defects listed in the handoff README.

All data here is synthetic. No browser, network or real account is used:
the bsk CLI is replaced by a fake `subprocess.run`.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp import server as srv  # noqa: E402
from xuexitong_mcp.bsk import Bsk, BskError, JsError  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.privacy import safe_error_text, safe_exception_log  # noqa: E402

SECRET_SESSION = "sessSYNTH9f3a"
SECRET_PERSON = "测试学生甲"
SECRET_URL = "https://mooc1.chaoxing.com/x?enc=SYNTHENC&personid=424242"


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "inst0001")
    c = Config()
    c.log_dir = tmp_path / "logs"
    c.log_level = "DEBUG"
    c.settle = 0
    yield c
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()


def _log_text(cfg) -> str:
    for h in logging.getLogger("xuexitong_mcp.bsk").handlers:
        h.flush()
    p = cfg.log_dir / "bsk.log"
    return p.read_text(encoding="utf-8") if p.exists() else ""


class FakeCli:
    """Maps the bsk sub-command to a canned (returncode, payload)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kw):
        args = cmd[1:]
        self.calls.append(args)
        key = " ".join(a for a in args[:2] if not a.startswith("-"))
        for prefix, (rc, payload) in self.routes.items():
            if key.startswith(prefix):
                out = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
                return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")
        raise AssertionError(f"unexpected bsk call {args}")


# ---------------------------------------------------------------- defect 1: session id in logs
def test_session_identifier_never_logged(cfg, monkeypatch):
    fake = FakeCli({
        "browsers": (0, [{"instance_id": "inst0001", "unresponsive": False}]),
        "session start": (0, {"session_id": SECRET_SESSION, "browser_instance_id": "inst0001"}),
        "tab list": (0, {"tabs": [{"tab_id": 77, "scope": "agent", "url": "about:blank"}]}),
        "navigate": (0, {"tab_id": 77, "reached": "load", "final_url": bsk_mod.FIXED_HOMEPAGE}),
    })
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(Bsk, "wait_readiness", lambda self, *a, **k: None)
    b = Bsk(cfg)
    b.start_session()
    assert b.session == SECRET_SESSION
    b.recover_tab = lambda: None  # not exercised
    b.log.warning("recover_session: restarting session")
    text = _log_text(cfg)
    assert "started session" in text
    assert SECRET_SESSION not in text


def test_reused_session_identifier_never_logged(cfg, monkeypatch):
    bsk_mod.STATE_FILE.write_text(json.dumps({"session": SECRET_SESSION, "tab": 5}))
    fake = FakeCli({
        "session list": (0, [{"session_id": SECRET_SESSION, "browser_instance_id": "inst0001"}]),
        "tab select": (0, {"tab_id": 5}),
    })
    monkeypatch.setattr(subprocess, "run", fake)
    b = Bsk(cfg)
    b.ensure_session()
    assert b.session == SECRET_SESSION
    assert SECRET_SESSION not in _log_text(cfg)


# ---------------------------------------------------------------- defects 2+3: exception text in logs / results
def test_cli_error_text_not_in_tool_result(cfg):
    e = BskError("cdp_failed", f"page said {SECRET_PERSON} at {SECRET_URL}",
                 {"reason": "target_closed", "effect_state": "none"}, raw=SECRET_PERSON, origin="cli")
    r = srv._err(e)
    blob = json.dumps(r, ensure_ascii=False)
    assert SECRET_PERSON not in blob and "SYNTHENC" not in blob and "424242" not in blob
    assert r["browser_error"]["code"] == "cdp_failed"
    assert r["browser_error"]["reason"] == "target_closed"


def test_local_error_message_kept(cfg):
    e = BskError("login_required", "配置指定的 Profile 已跳转到学习通登录页；请本人手动登录后再继续。")
    r = srv._err(e)
    assert "登录页" in r["error"] and r["needs_human"] is True


def test_js_error_only_keeps_own_chinese_messages():
    assert "班级列表不完整" in safe_error_text(JsError("班级列表不完整或不唯一，停止发放"))
    hidden = safe_error_text(JsError(f"TypeError: cannot read {SECRET_URL}"))
    assert "SYNTHENC" not in hidden and "TypeError" not in hidden
    # Chinese text carrying a long number (student number / person id) is dropped
    assert "2023123456" not in safe_error_text(JsError("学号 2023123456 不存在"))


def test_unexpected_exception_message_not_in_result_or_log(cfg, monkeypatch):
    fake = FakeCli({})
    monkeypatch.setattr(subprocess, "run", fake)

    class Client:
        b = Bsk(cfg)

    monkeypatch.setitem(srv._state, "client", Client())
    try:
        raise KeyError(f"{SECRET_PERSON} {SECRET_URL}")
    except KeyError as exc:
        r = srv._err(exc)
    assert r == {"ok": False, "error": "内部错误：KeyError"}
    text = _log_text(cfg)
    assert "KeyError at" in text
    assert SECRET_PERSON not in text and "SYNTHENC" not in text


def test_safe_exception_log_has_no_message():
    try:
        raise RuntimeError(SECRET_PERSON)
    except RuntimeError as exc:
        s = safe_exception_log(exc)
    assert s.startswith("RuntimeError at test_privacy_and_wait.py:")
    assert SECRET_PERSON not in s


def test_dialog_text_not_in_error(cfg, monkeypatch):
    fake = FakeCli({"dialog status": (0, {"dialogs": [
        {"type": "confirm", "url": "https://mooc1.chaoxing.com/a", "message": f"确定删除{SECRET_PERSON}的作业？"}]})})
    monkeypatch.setattr(subprocess, "run", fake)
    b = Bsk(cfg)
    with pytest.raises(BskError) as ei:
        b._resolve_leave_dialog(allow_leave=False)
    assert SECRET_PERSON not in str(ei.value)
    assert SECRET_PERSON not in json.dumps(srv._err(ei.value), ensure_ascii=False)


# ---------------------------------------------------------------- defect 4: waits swallowing errors
def _client(cfg):
    from xuexitong_mcp.xxt import make_client
    return make_client(cfg)


@pytest.mark.parametrize("code", ["timeout", "control_not_ready", "sync_incomplete", "not_found"])
def test_wait_for_propagates_browser_errors_without_polling(cfg, monkeypatch, code):
    c = _client(cfg)
    calls = []

    def boom(js, **kw):
        calls.append(js)
        raise BskError(code, "synthetic")
    monkeypatch.setattr(c.b, "eval", boom)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(BskError):
        c.wait_for("return false", timeout=30)
    assert len(calls) == 1


def test_wait_for_keeps_polling_on_page_script_error(cfg, monkeypatch):
    c = _client(cfg)
    seq = iter([JsError("x"), JsError("y"), {"done": True}])

    def step(js, **kw):
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(c.b, "eval", step)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert c.wait_for("return 1", timeout=30) == {"done": True}


def test_href_does_not_return_stale_url_on_browser_error(cfg, monkeypatch):
    b = Bsk(cfg)
    b.url = "https://mooc1.chaoxing.com/stale?clazzId=1"
    monkeypatch.setattr(b, "eval", lambda js, **kw: (_ for _ in ()).throw(BskError("timeout", "t")))
    with pytest.raises(BskError):
        b.href()


def test_ctx_does_not_guess_classes_after_browser_error(cfg, monkeypatch):
    from xuexitong_mcp.xxt import Course
    c = _client(cfg)
    course = Course(id="100", name="合成课程", cpi="9")
    monkeypatch.setattr(c, "course", lambda q: course)
    monkeypatch.setattr(c.b, "navigate", lambda url, **kw: "https://mooc1.chaoxing.com/c?clazzId=5&enc=E&t=1&cpi=9")
    monkeypatch.setattr(c, "on", lambda *a, **k: (_ for _ in ()).throw(BskError("timeout", "t")))
    with pytest.raises(BskError):
        c.ctx("100", refresh=True)
    assert course.classes == [] and course.enc == "" and course.ctx_time == 0.0


def test_on_moves_to_static_base_page_before_fetch(cfg, monkeypatch):
    from xuexitong_mcp.xxt import BASE_PAGE, M2
    c = _client(cfg)
    c.b.url = "https://mooc2-ans.chaoxing.com/mooc2-ans-vue/fanyav3/tch?courseId=1"
    navs = []

    def nav(url, **kw):
        navs.append(url)
        c.b.url = url
        return url
    monkeypatch.setattr(c.b, "navigate", nav)
    monkeypatch.setattr(c.b, "eval", lambda js, **kw: {"v": 1})
    assert c.on(M2, "return 1") == {"v": 1}
    assert navs == [BASE_PAGE[M2]]
    c.on(M2, "return 2")
    assert navs == [BASE_PAGE[M2]]  # already on the base page: no extra navigation


# ---------------------------------------------------------------- health result
def test_health_result_has_no_session_handle(cfg, monkeypatch):
    c = _client(cfg)
    monkeypatch.setattr(c.b, "doctor", lambda: [{"name": "x", "ok": True}])
    def ensure(**kw):
        c.b.session, c.b.tab = SECRET_SESSION, 9
    monkeypatch.setattr(c.b, "ensure_session", ensure)
    monkeypatch.setattr(c, "on", lambda *a, **k: (_ for _ in ()).throw(BskError("control_not_ready", "synthetic", origin="cli")))
    r = c.health()
    assert SECRET_SESSION not in json.dumps(r, ensure_ascii=False)
    assert r["session"] == {"bound": True}
    assert r["ok"] is False


# ---------------------------------------------------------------- Windows portability
def test_bsk_output_decoded_as_utf8(cfg, monkeypatch):
    seen = {}

    def fake(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps([{"instance_id": "inst0001", "label": "主力笔记本"}], ensure_ascii=False), stderr="")
    monkeypatch.setattr(subprocess, "run", fake)
    Bsk(cfg).run(["browsers"], session=False)
    assert seen.get("encoding") == "utf-8"



def test_upload_preview_digest_runs_on_this_platform(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"synthetic")
    d = srv._upload_preview_digest(p)
    assert d["size"] == 9 and len(d["sha256"]) == 64


@pytest.mark.parametrize("result", [[], [{"clazz_id": "", "name": "x"}]])
def test_ctx_refuses_to_guess_a_class_on_empty_list(cfg, monkeypatch, result):
    from xuexitong_mcp.xxt import Course, XxtError
    c = _client(cfg)
    course = Course(id="100", name="合成课程", cpi="9")
    monkeypatch.setattr(c, "course", lambda q: course)
    monkeypatch.setattr(c.b, "navigate", lambda url, **kw: "https://mooc1.chaoxing.com/c?clazzId=5&enc=E&t=1&cpi=9")
    monkeypatch.setattr(c, "on", lambda *a, **k: result)
    with pytest.raises(XxtError):
        c.ctx("100", refresh=True)
    assert course.enc == "" and course.ctx_time == 0.0


def test_ctx_refuses_to_guess_a_class_on_page_script_error(cfg, monkeypatch):
    from xuexitong_mcp.xxt import Course, XxtError
    c = _client(cfg)
    course = Course(id="100", name="合成课程", cpi="9")
    monkeypatch.setattr(c, "course", lambda q: course)
    monkeypatch.setattr(c.b, "navigate", lambda url, **kw: "https://mooc1.chaoxing.com/c?clazzId=5&enc=E&t=1&cpi=9")
    monkeypatch.setattr(c, "on", lambda *a, **k: (_ for _ in ()).throw(JsError("x")))
    with pytest.raises(XxtError):
        c.ctx("100", refresh=True)
    assert course.classes == []
