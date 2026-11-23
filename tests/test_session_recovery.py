"""Regression tests for dead-session recovery in Bsk.ensure_session.

A session that idled out or whose window was closed is definitively gone: the
owned tab no longer exists, so there is nothing left to preserve. Recovery must
proceed even when preserve_tab was set by an earlier error. Live-tab errors
(permission/transport/unknown) must still be protected by preserve_tab.

All data is synthetic; the bsk CLI is replaced by a fake `run`.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.bsk import Bsk, BskError  # noqa: E402
from xuexitong_mcp.config import Config, load  # noqa: E402
from xuexitong_mcp.xxt import NOTICE, make_client  # noqa: E402

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
            return {"session_id": NEW_SESSION, "browser_instance_id": "inst0001", "agent_window_id": 88}
        if args[:2] == ["tab", "list"]:
            return {"tabs": [{"tab_id": 77, "window_id": 88, "scope": "agent", "url": "about:blank"}]}
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


def test_health_recovers_disconnected_owned_session_on_same_reconnected_browser(cfg, monkeypatch):
    client = make_client(cfg)
    b = client.b
    b.session, b.tab = "sessOLD", 5
    b.preserve_tab = b._login_handoff = True
    b.obs_text = "previous observation"
    b.doctor = lambda: [{"name": "extension connected", "ok": True}]
    b.wait_readiness = lambda *args: None
    b.navigate = lambda *args, **kwargs: ""
    client.on = lambda host, *args: {"ok": True} if host == NOTICE else {"zh": True}
    client.courses = lambda **kwargs: [object()]
    client.here = lambda *args: {"guard": True, "lang": "zh-CN"}
    calls = []
    fake = _fake_run("browser_disconnected")

    def run(args, timeout=None, session=True):
        calls.append(args)
        return fake(args, timeout=timeout, session=session)

    monkeypatch.setattr(b, "run", run)
    result = client.health()
    assert result["ok"] is True and result["session"] == {"bound": True}
    assert b.session == NEW_SESSION and b.tab == 77
    assert not b.preserve_tab and not b._login_handoff and not b.obs_text
    assert all(NEW_SESSION not in str(value) for value in result.values())
    assert calls[:3] == [["tab", "list", "--scope", "agent"], ["browsers"],
                         ["session", "start", "--browser", "inst0001"]]
    assert not any(args[:2] == ["session", "stop"] for args in calls)


@pytest.mark.parametrize("browsers", [
    [],
    [{"instance_id": "different", "unresponsive": False}],
    [{"instance_id": "inst0001", "unresponsive": True}],
    [{"instance_id": "inst0001"}],
    [{"instance_id": "inst0001", "unresponsive": False}] * 2,
])
def test_disconnected_health_keeps_state_when_fixed_profile_is_unavailable(cfg, monkeypatch, browsers):
    b = Bsk(cfg)
    b.session, b.tab, b.preserve_tab = "sessOLD", 5, True
    b._save_state()
    saved = bsk_mod.STATE_FILE.read_text()

    def run(args, timeout=None, session=True):
        if args == ["tab", "list", "--scope", "agent"]:
            raise BskError("not_found", "synthetic", {"reason": "browser_disconnected"})
        assert args == ["browsers"] and session is False
        return {"value": browsers}

    monkeypatch.setattr(b, "run", run)
    monkeypatch.setattr(b, "_auto_open_browser", lambda: pytest.fail("offline Chrome must stay untouched"))
    with pytest.raises(BskError) as caught:
        b.ensure_session(renew_disconnected_readonly=True)
    assert caught.value.code == "browser_profile_unavailable"
    assert (b.session, b.tab, b.preserve_tab) == ("sessOLD", 5, True)
    assert bsk_mod.STATE_FILE.read_text() == saved


@pytest.mark.parametrize(("code", "health"), [("not_found", False), ("permission_denied", True)])
def test_disconnected_recovery_requires_health_and_exact_tombstone(cfg, monkeypatch, code, health):
    b = Bsk(cfg)
    b.session, b.tab = "sessOLD", 5
    failure = BskError(code, "synthetic", {"reason": "browser_disconnected"})

    def run(args, timeout=None, session=True):
        assert args == ["tab", "list", "--scope", "agent"]
        raise failure

    monkeypatch.setattr(b, "run", run)
    with pytest.raises(BskError) as caught:
        b.ensure_session(renew_idle_readonly=True, renew_disconnected_readonly=health)
    assert caught.value is failure
    assert (b.session, b.tab) == ("sessOLD", 5)


def test_disconnected_health_does_not_replace_state_on_wrong_session_browser(cfg, monkeypatch):
    b = Bsk(cfg)
    b.session, b.tab = "sessOLD", 5
    fake = _fake_run("browser_disconnected")

    def run(args, timeout=None, session=True):
        if args[:2] == ["session", "start"]:
            return {"session_id": NEW_SESSION, "browser_instance_id": "different"}
        return fake(args, timeout=timeout, session=session)

    monkeypatch.setattr(b, "run", run)
    with pytest.raises(BskError) as caught:
        b.ensure_session(renew_disconnected_readonly=True)
    assert caught.value.code == "browser_profile_mismatch"
    assert (b.session, b.tab) == ("sessOLD", 5)


def _startup_tab(**fields):
    return {"tab_id": 77, "window_id": 88, "scope": "agent", "active": True, **fields}


def _startup_probe(cfg, monkeypatch, snapshots):
    b = Bsk(cfg)
    calls = []
    snapshots = iter(snapshots)

    def run(args, timeout=None, session=True):
        calls.append((args, timeout))
        if args == ["tab", "list", "--scope", "agent"]:
            snapshot = next(snapshots)
            if isinstance(snapshot, BskError):
                raise snapshot
            return snapshot
        assert args[:3] == ["navigate", bsk_mod.FIXED_HOMEPAGE, "--tab-id"]
        assert args[3] == "77"
        return {"tab_id": 77, "reached": "load", "final_url": bsk_mod.FIXED_HOMEPAGE}

    monkeypatch.setattr(b, "run", run)
    monkeypatch.setattr(b, "wait_readiness", lambda *args: None)
    monkeypatch.setattr(bsk_mod.time, "sleep", lambda seconds: None)
    return b, calls


@pytest.mark.parametrize("fields", [{}, {"url": "", "title": ""}])
def test_initial_tab_waits_for_only_same_owned_blank_to_commit(cfg, monkeypatch, fields):
    b, calls = _startup_probe(cfg, monkeypatch, [
        {"tabs": [_startup_tab(**fields)]},
        {"tabs": [_startup_tab(url="about:blank", title="about:blank")]},
    ])
    b._initialize_owned_tab(88)
    assert [args[0] for args, _ in calls] == ["tab", "tab", "navigate"]
    assert 0 < calls[1][1] <= 1.0
    assert b.tab == 77


def test_already_committed_blank_accepts_legacy_numeric_like_id(cfg, monkeypatch):
    b, calls = _startup_probe(cfg, monkeypatch, [{"tabs": [_startup_tab(url="about:blank", tab_id="77")]}])
    b._initialize_owned_tab()
    assert [args[0] for args, _ in calls] == ["tab", "navigate"]


@pytest.mark.parametrize("snapshot", [
    [],
    {"tabs": [_startup_tab(tab_id="77")]},
    {"tabs": [_startup_tab(title="Unexpected")]},
    {"tabs": [_startup_tab(url="chrome://newtab/")]},
    {"tabs": [_startup_tab(active=False)]},
    {"tabs": [_startup_tab(scope="user")]},
    {"tabs": [_startup_tab(borrowed=True)]},
    {"tabs": [_startup_tab(window_id=89)]},
    {"tabs": [_startup_tab(), _startup_tab(tab_id=78)]},
])
def test_initial_tab_unexpected_first_snapshot_is_not_retried(cfg, monkeypatch, snapshot):
    b, calls = _startup_probe(cfg, monkeypatch, [snapshot])
    with pytest.raises(BskError, match="initial_tab_unexpected"):
        b._initialize_owned_tab(88)
    assert len(calls) == 1 and b.tab is None


@pytest.mark.parametrize("snapshot", [
    {"tabs": [_startup_tab(tab_id=78, url="about:blank")]},
    {"tabs": [_startup_tab(url="chrome://newtab/")]},
    {"tabs": [_startup_tab(url="about:blank"), _startup_tab(tab_id=78)]},
])
def test_initial_tab_stops_when_snapshot_changes_during_wait(cfg, monkeypatch, snapshot):
    b, calls = _startup_probe(cfg, monkeypatch, [{"tabs": [_startup_tab()]}, snapshot])
    with pytest.raises(BskError, match="initial_tab_unexpected"):
        b._initialize_owned_tab(88)
    assert [args[0] for args, _ in calls] == ["tab", "tab"] and b.tab is None


def test_initial_tab_rejects_permission_denial_immediately(cfg, monkeypatch):
    refused = BskError("permission_denied", "synthetic")
    b, calls = _startup_probe(cfg, monkeypatch, [{"tabs": [_startup_tab()]}, refused])
    with pytest.raises(BskError) as caught:
        b._initialize_owned_tab(88)
    assert caught.value is refused and len(calls) == 2 and b.tab is None


def test_initial_tab_pending_state_has_bounded_polling(cfg, monkeypatch):
    b, calls = _startup_probe(cfg, monkeypatch, [{"tabs": [_startup_tab()]}] * 6)
    with pytest.raises(BskError, match="initial_tab_unexpected"):
        b._initialize_owned_tab(88)
    assert len(calls) == 6 and b.tab is None
    assert all(args == ["tab", "list", "--scope", "agent"] and 0 < timeout <= 1.0 for args, timeout in calls[1:])


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
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "fakeb001")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "/fake/opener")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER_ROLE", "teacher")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER_WAIT", 5)
    b = Bsk(cfg)
    state = {"opener": [], "browsers": 0}

    def fake_run(args, timeout=None, session=True):
        if args[0] == "browsers":
            state["browsers"] += 1
            if state["browsers"] >= 2:  # online after the opener ran
                return {"value": [{"instance_id": "fakeb001", "unresponsive": False}]}
            return {"value": []}
        if args[:2] == ["session", "start"]:
            return {"session_id": "s1", "browser_instance_id": "fakeb001"}
        return {}

    monkeypatch.setattr(b, "run", fake_run)
    monkeypatch.setattr(b, "_initialize_owned_tab", lambda: None)
    monkeypatch.setattr(bsk_mod.subprocess, "run",
                        lambda *a, **k: state["opener"].append(a[0]) or sp.CompletedProcess(a[0], 0))
    b.start_session()
    assert state["opener"] and state["opener"][0] == ["/fake/opener", "teacher"]
    assert b.session == "s1"


def test_display_preflight_configuration_is_opt_in(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[browser]\nopener_role = "teacher"\n')
    assert load(p).browser_display_preflight == ""
    p.write_text('[browser]\ndisplay_preflight = "/trusted/display helper"\n')
    assert load(p).browser_display_preflight == "/trusted/display helper"


@pytest.mark.parametrize("replacing", [False, True])
def test_display_preflight_precedes_agent_window_creation_with_online_browser(cfg, monkeypatch, tmp_path, replacing):
    helper = str(tmp_path / "display helper")
    cfg.browser_display_preflight = helper
    b = Bsk(cfg)
    calls = []
    if replacing:
        b.session, b.tab, b.preserve_tab = "sessOLD", 5, True

    def run(args, timeout=None, session=True):
        calls.append(args)
        if args == ["tab", "list", "--scope", "agent"]:
            raise BskError("not_found", "synthetic", {"reason": "browser_disconnected"})
        if args == ["browsers"]:
            return {"value": [{"instance_id": "inst0001", "unresponsive": False}]}
        assert args == ["session", "start", "--browser", "inst0001"] and session is False
        return {"session_id": NEW_SESSION, "browser_instance_id": "inst0001"}

    def preflight(args, *, stdout, stderr, timeout):
        calls.append(args)
        assert args == [helper, "--ensure"]
        assert stdout == stderr == subprocess.DEVNULL and timeout == 32
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(b, "run", run)
    monkeypatch.setattr(b, "_initialize_owned_tab", lambda: None)
    monkeypatch.setattr(bsk_mod.subprocess, "run", preflight)
    b.ensure_session(renew_disconnected_readonly=replacing)
    expected = [["browsers"], [helper, "--ensure"], ["session", "start", "--browser", "inst0001"]]
    assert calls == ([["tab", "list", "--scope", "agent"]] + expected if replacing else expected)
    assert b.session == NEW_SESSION


@pytest.mark.parametrize(("outcome", "code"), [
    (subprocess.CompletedProcess([], 7, stdout="private-display-output", stderr="private-display-output"),
     "display_preflight_failed"),
    (subprocess.TimeoutExpired(["private-display-output"], 32), "display_preflight_timeout"),
    (FileNotFoundError("private-display-output"), "display_preflight_unavailable"),
])
def test_display_preflight_failure_stops_before_new_session(cfg, monkeypatch, tmp_path, outcome, code):
    cfg.browser_display_preflight = str(tmp_path / "display-helper")
    b = Bsk(cfg)
    b.session, b.tab, b.preserve_tab = "sessOLD", 5, True

    def run(args, timeout=None, session=True):
        assert args == ["browsers"] and session is False
        return {"value": [{"instance_id": "inst0001", "unresponsive": False}]}

    def preflight(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(b, "run", run)
    monkeypatch.setattr(bsk_mod.subprocess, "run", preflight)
    with pytest.raises(BskError) as caught:
        b.start_session(replacing_disconnected=True)
    assert caught.value.code == code
    assert "private-display-output" not in str(caught.value) + caught.value.raw
    assert caught.value.__suppress_context__ or caught.value.__context__ is None
    assert (b.session, b.tab, b.preserve_tab) == ("sessOLD", 5, True)


@pytest.mark.parametrize(("outcome", "error_code"), [
    (subprocess.CompletedProcess([], 7, stdout="private-launcher-output", stderr="private-launcher-output"),
     "browser_opener_failed"),
    (subprocess.TimeoutExpired(["private-launcher-output"], 90, stderr="private-launcher-output"),
     "browser_opener_timeout"),
    (FileNotFoundError("private-launcher-output"), "browser_opener_unavailable"),
])
def test_opener_failure_reports_sanitized_cause_without_polling(cfg, monkeypatch, outcome, error_code):
    cfg.browser_opener = "/fake/opener"
    cfg.browser_opener_role = "teacher"
    b = Bsk(cfg)
    checks = []

    def run(args, timeout=None, session=True):
        assert args == ["browsers"] and session is False
        checks.append(args)
        return {"value": [{"instance_id": "other-profile", "unresponsive": False}]}

    def launch(args, *, stdout, stderr, timeout):
        assert args == ["/fake/opener", "teacher"] and timeout == 90
        assert stdout == stderr == subprocess.DEVNULL
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(b, "run", run)
    monkeypatch.setattr(bsk_mod.subprocess, "run", launch)
    monkeypatch.setattr(bsk_mod.time, "sleep", lambda _: pytest.fail("a failed launcher must not enter the polling loop"))

    with pytest.raises(BskError) as caught:
        b.start_session()
    assert caught.value.code == error_code
    assert "private-launcher-output" not in str(caught.value) + caught.value.raw
    assert "private-launcher-output" not in (cfg.log_dir / "bsk.log").read_text()
    assert checks == [["browsers"], ["browsers"]] and b.session is None


def test_opener_failure_allows_same_profile_that_connected_concurrently(cfg, monkeypatch):
    cfg.browser_opener = "/fake/opener"
    cfg.browser_opener_role = "student"
    b = Bsk(cfg)
    calls = []

    def run(args, timeout=None, session=True):
        calls.append(args)
        if args == ["browsers"]:
            return {"value": [] if len(calls) == 1 else [{"instance_id": "inst0001", "unresponsive": False}]}
        assert args == ["session", "start", "--browser", "inst0001"] and session is False
        return {"session_id": NEW_SESSION, "browser_instance_id": "inst0001"}

    monkeypatch.setattr(b, "run", run)
    monkeypatch.setattr(b, "_initialize_owned_tab", lambda: None)
    monkeypatch.setattr(bsk_mod.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 1))
    monkeypatch.setattr(bsk_mod.time, "sleep", lambda _: pytest.fail("a connected profile must not need polling"))

    b.start_session()
    assert calls == [["browsers"], ["browsers"], ["browsers"], ["session", "start", "--browser", "inst0001"]]
    assert b.session == NEW_SESSION


def test_start_session_offline_no_opener_raises(cfg, monkeypatch):
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "fakeb001")
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

def test_start_session_clears_half_initialized_on_init_failure(cfg, monkeypatch):
    # Regression (live 2026-11-23): start_session set self.session before
    # _initialize_owned_tab(); a failed init left a half-initialized session so
    # ensure_session() returned early and later attempts observed about:blank.
    # Non-login init failure must clear the session (and stop its own window);
    # login_required is a valid handoff and keeps the session for the login flow.
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "fakeb001")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "")
    b = Bsk(cfg)
    monkeypatch.setattr(b, "_browser_online", lambda: True)
    stops = []

    def fake_run(args, timeout=None, session=True):
        if args[:2] == ["session", "start"]:
            return {"session_id": "sX", "browser_instance_id": "fakeb001"}
        if args[:2] == ["session", "stop"]:
            stops.append(args[2])
            return {}
        return {}

    monkeypatch.setattr(b, "run", fake_run)
    monkeypatch.setattr(b, "_initialize_owned_tab",
                        lambda: (_ for _ in ()).throw(BskError("initial_tab_unexpected", "x")))
    with pytest.raises(BskError):
        b.start_session()
    assert b.session is None and b.tab is None and stops == ["sX"]


def test_start_session_keeps_session_on_login_required(cfg, monkeypatch):
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "fakeb001")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "")
    b = Bsk(cfg)
    monkeypatch.setattr(b, "_browser_online", lambda: True)
    monkeypatch.setattr(b, "run", lambda args, timeout=None, session=True:
                        {"session_id": "sL", "browser_instance_id": "fakeb001"} if args[:2] == ["session", "start"] else {})
    monkeypatch.setattr(b, "_initialize_owned_tab",
                        lambda: (_ for _ in ()).throw(BskError("login_required", "x")))
    with pytest.raises(BskError):
        b.start_session()
    assert b.session == "sL"  # kept for the login flow (tab parked on passport)


def test_start_session_purges_state_when_stop_fails(cfg, tmp_path, monkeypatch):
    # _initialize_owned_tab may _save_state() before failing; if stopping the failed
    # session also fails, the persisted state must still be purged so a restart will
    # not reuse the failed session. login_required handoff state is untouched.
    import json as _json
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "fakeb001")
    monkeypatch.setattr(bsk_mod, "BROWSER_OPENER", "")
    sf = tmp_path / "state.json"
    monkeypatch.setattr(bsk_mod, "STATE_FILE", sf)
    b = Bsk(cfg)
    monkeypatch.setattr(b, "_browser_online", lambda: True)

    def fake_run(args, timeout=None, session=True):
        if args[:2] == ["session", "start"]:
            return {"session_id": "sFail", "browser_instance_id": "fakeb001"}
        if args[:2] == ["session", "stop"]:
            raise BskError("permission_denied", "stop refused")
        return {}

    monkeypatch.setattr(b, "run", fake_run)

    def bad_init():
        sf.write_text(_json.dumps({"session": "sFail", "tab": 9}))
        raise BskError("initial_load_incomplete", "x")

    monkeypatch.setattr(b, "_initialize_owned_tab", bad_init)
    with pytest.raises(BskError):
        b.start_session()
    assert b.session is None and b.tab is None and not sf.exists()

@pytest.mark.parametrize("editing", [False, True])
def test_sync_settles_new_document_and_checks_its_control_state(cfg, monkeypatch, editing):
    browser = Bsk(cfg)
    browser.tab = 17
    monkeypatch.setattr(browser, "ensure_session", lambda: None)

    def run(args):
        assert args[:2] == ["cooperate", "sync"]
        assert "--settle" in args and args[args.index("--tab-id") + 1] == "17"
        return {"tab_id": 17, "context_id": "ctx", "observation_id": "obs",
                "state": {"mode": "ready", "editing": editing}}

    monkeypatch.setattr(browser, "run", run)
    if editing:
        with pytest.raises(BskError) as error:
            browser.sync()
        assert error.value.code == "control_not_ready"
    else:
        assert browser.sync() == ("ctx", "obs")
