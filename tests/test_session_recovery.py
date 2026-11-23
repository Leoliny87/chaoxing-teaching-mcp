"""Regression tests for dead-session recovery in Bsk.ensure_session.

A session that idled out or whose window was closed is definitively gone: the
owned tab no longer exists, so there is nothing left to preserve. Recovery must
proceed even when preserve_tab was set by an earlier error. Live-tab errors
(permission/transport/unknown) must still be protected by preserve_tab.

All data is synthetic; the bsk CLI is replaced by a fake `run`.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.bsk import Bsk, BskError  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402

NEW_SESSION = "sessNEW123"


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


def _fake_run(dead_reason):
    """First `tab list` probe reports a dead session; later calls behave normally."""
    state = {"probed": False}

    def run(args, timeout=None, session=True):
        if args[:2] == ["tab", "list"] and not state["probed"]:
            state["probed"] = True
            raise BskError("not_found", "synthetic", {"reason": dead_reason}, origin="cli")
        if args[0] == "browsers":
            return {"value": [{"instance_id": "inst0001", "unresponsive": False}]}
        if args[:2] == ["session", "start"]:
            return {"session_id": NEW_SESSION, "browser_instance_id": "inst0001"}
        if args[:2] == ["tab", "list"]:
            return {"tabs": [{"tab_id": 77, "scope": "agent", "url": "about:blank"}]}
        if args[0] == "navigate":
            return {"tab_id": 77, "reached": "load", "final_url": bsk_mod.FIXED_HOMEPAGE}
        raise AssertionError(f"unexpected bsk call {args}")

    return run


@pytest.mark.parametrize("dead_reason", ["session_idle_timeout", "session_window_closed"])
def test_recovers_dead_session_even_when_preserve_tab(cfg, monkeypatch, dead_reason):
    monkeypatch.setattr(Bsk, "wait_readiness", lambda self, *a, **k: None)
    b = Bsk(cfg)
    b.session = "sessOLD"
    b.tab = 5
    b.preserve_tab = True
    b.run = _fake_run(dead_reason)

    b.ensure_session(renew_idle_readonly=True)

    assert b.session == NEW_SESSION
    assert b.preserve_tab is False


@pytest.mark.parametrize("code,reason", [
    ("permission_denied", "observation_changed"),
    ("not_found", "target_closed"),
    ("timeout", None),
])
def test_live_tab_error_still_protected_by_preserve_tab(cfg, monkeypatch, code, reason):
    b = Bsk(cfg)
    b.session = "sessOLD"
    b.tab = 5
    b.preserve_tab = True

    def run(args, timeout=None, session=True):
        if args[:2] == ["tab", "list"]:
            raise BskError(code, "synthetic", {"reason": reason} if reason else {}, origin="cli")
        raise AssertionError(f"recovery must not run for a live-tab error: {args}")

    b.run = run
    with pytest.raises(BskError):
        b.ensure_session(renew_idle_readonly=True)
    assert b.session == "sessOLD"
    assert b.preserve_tab is True


def test_stop_closes_tab_and_stops_session(cfg, monkeypatch):
    b = Bsk(cfg)
    b.session = "sessOLD1"
    b.tab = 42
    calls = []

    def run(args, timeout=None, session=True):
        calls.append(args)
        if args[:2] == ["tab", "list"]:
            return {"tabs": [{"tab_id": 42, "scope": "agent"}]}
        if args[:2] == ["cooperate", "sync"]:
            return {"tab_id": 42, "state": {"mode": "ready"}, "context_id": "c1", "observation_id": "o1"}
        if args[:2] == ["tab", "close"]:
            return {"tab_id": 42}
        if args[:2] == ["session", "stop"]:
            return {"stopped": ["sessOLD1"]}
        return {}

    monkeypatch.setattr(b, "run", run)
    b.stop()
    assert ["tab", "close", "42", "--context", "c1", "--observation", "o1"] in calls
    assert ["session", "stop", "sessOLD1"] in calls  # session must not linger
    assert b.session is None and b.tab is None


def test_stop_preserve_tab_keeps_session(cfg, monkeypatch):
    b = Bsk(cfg)
    b.session = "sessOLD2"
    b.tab = 43
    b.preserve_tab = True
    calls = []
    monkeypatch.setattr(b, "run", lambda args, timeout=None, session=True: calls.append(args) or {})
    b.stop()
    assert not any(a[:2] == ["session", "stop"] for a in calls)
    assert b.session == "sessOLD2"  # preserved for reconciliation


def test_start_session_auto_opens_chrome_when_offline(cfg, monkeypatch):
    # Chrome fully closed -> instance offline -> MCP calls the official launcher to
    # open the profile, waits for the extension to attach, then starts the session.
    import subprocess as sp
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "c41e7649")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "/fake/opener")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER_ROLE", "teacher")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER_WAIT", 5)
    b = Bsk(cfg)
    state = {"opener": [], "browsers": 0}

    def fake_run(args, timeout=None, session=True):
        if args[0] == "browsers":
            state["browsers"] += 1
            if state["browsers"] >= 2:  # online after the opener ran
                return {"value": [{"instance_id": "c41e7649", "unresponsive": False}]}
            return {"value": []}
        if args[:2] == ["session", "start"]:
            return {"session_id": "s1", "browser_instance_id": "c41e7649"}
        return {}

    monkeypatch.setattr(b, "run", fake_run)
    monkeypatch.setattr(b, "_initialize_owned_tab", lambda: None)
    monkeypatch.setattr(bsk_mod.subprocess, "run",
                        lambda *a, **k: state["opener"].append(a[0]) or sp.CompletedProcess(a[0], 0))
    b.start_session()
    assert state["opener"] and state["opener"][0] == ["/fake/opener", "teacher"]
    assert b.session == "s1"


def test_start_session_offline_no_opener_raises(cfg, monkeypatch):
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "c41e7649")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "")  # auto-open disabled
    b = Bsk(cfg)
    monkeypatch.setattr(b, "run", lambda args, timeout=None, session=True: {"value": []})
    with pytest.raises(BskError) as ei:
        b.start_session()
    assert ei.value.code == "browser_profile_unavailable"


def test_auto_open_role_from_per_user_config(cfg, monkeypatch):
    # The opener role is recorded per-user in config ([browser] opener_role), not
    # hardcoded per instance. cfg.browser_opener_role drives the launcher role.
    import subprocess as sp
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "instUSER99")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER_ROLE", "")
    cfg.browser_opener = "/fake/opener"
    cfg.browser_opener_role = "student"
    cfg.browser_opener_wait = 5
    b = Bsk(cfg)
    state = {"opener": [], "browsers": 0}

    def fake_run(args, timeout=None, session=True):
        if args[0] == "browsers":
            state["browsers"] += 1
            if state["browsers"] >= 2:
                return {"value": [{"instance_id": "instUSER99", "unresponsive": False}]}
            return {"value": []}
        if args[:2] == ["session", "start"]:
            return {"session_id": "s2", "browser_instance_id": "instUSER99"}
        return {}

    monkeypatch.setattr(b, "run", fake_run)
    monkeypatch.setattr(b, "_initialize_owned_tab", lambda: None)
    monkeypatch.setattr(bsk_mod.subprocess, "run",
                        lambda *a, **k: state["opener"].append(a[0]) or sp.CompletedProcess(a[0], 0))
    b.start_session()
    assert state["opener"] and state["opener"][0] == ["/fake/opener", "student"]
    assert b.session == "s2"