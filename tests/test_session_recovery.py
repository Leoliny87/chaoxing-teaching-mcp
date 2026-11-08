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