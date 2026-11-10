import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import LoginAutomator, LOGIN_URL


class FakeBsk:
    def __init__(self, urls):
        self.urls = iter(urls)
        self.evals = []
        self.navs = []
        self.fills = []      # (selector, value)
        self.clicks = []     # selector
        self.tab = 7
        self.cfg = type("C", (), {"t_navigate": 40})()

    def ensure_session(self, **kw):
        return

    def run(self, args, timeout=None, session=True):
        if args and args[0] == "navigate":
            self.navs.append(args[1])
        return {}

    def navigate(self, url, **kw):
        self.navs.append(url)
        return url

    def eval(self, js, **kw):
        self.evals.append(js)
        if "location.href" in js:
            return next(self.urls)
        return True

    def fill_selector(self, selector, value):
        self.fills.append((selector, value))
        return {}

    def click_selector(self, selector, **kw):
        self.clicks.append(selector)
        return {}


def test_fill_and_submit_targets_fields():
    b = FakeBsk([])
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.navs == [LOGIN_URL]
    # Targeted selector ops only: the passport2 QR widget churn invalidates
    # whole-page strict observations, so untargeted evaluate must not be used
    # for filling/submitting (live-denied 5/5 on 2026-11-10).
    assert b.fills == [("#phone", "13800000000"), ("#pwd", "secret")]
    assert b.clicks == ["#loginBtn"]
    assert b.evals == []


def test_wait_until_logged_in_success():
    b = FakeBsk(["https://passport2.chaoxing.com/login", "https://i.mooc.chaoxing.com/space/index"])
    r = LoginAutomator(b).wait_until_logged_in(timeout=10, poll=0)
    assert r["ok"] is True
    assert r["url"].startswith("https://i.mooc.chaoxing.com")


def test_wait_until_logged_in_timeout():
    b = FakeBsk(["https://passport2.chaoxing.com/login"] * 50)
    r = LoginAutomator(b).wait_until_logged_in(timeout=0.05, poll=0.01)
    assert r["ok"] is False
    assert r["needs_slider"] is True


def test_fill_and_submit_retries_on_transient_sync_error(monkeypatch):
    from xuexitong_mcp import login as L
    from xuexitong_mcp.bsk import BskError
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    class FlakyBsk:
        def __init__(self):
            self.navs = []
            self.fills = []
            self.clicks = []
            self.phone_calls = 0
            self.tab = 7
            self.cfg = type("C", (), {"t_navigate": 40})()

        def ensure_session(self, **kw):
            return

        def run(self, args, timeout=None, session=True):
            if args and args[0] == "navigate":
                self.navs.append(args[1])
            return {}

        def fill_selector(self, selector, value):
            self.fills.append((selector, value))
            if selector == "#phone":
                self.phone_calls += 1
                if self.phone_calls == 1:
                    raise BskError("permission_denied", "requires the context returned by the latest cooperate sync")
            return {}

        def click_selector(self, selector, **kw):
            self.clicks.append(selector)
            return {}

    b = FlakyBsk()
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.navs == [LOGIN_URL]        # navigated once, not per retry
    assert b.phone_calls == 2           # first fill denied, retried
    assert b.clicks == ["#loginBtn"]    # submitted exactly once after success


def test_fill_and_submit_continues_when_bootstrap_parks_on_login_page(monkeypatch):
    # Cold start while logged out: ensure_session's homepage bootstrap is
    # bounced to passport2 and raises login_required with the owned tab parked
    # there. fill_and_submit must continue on that tab, not propagate the guard
    # (which previously deadlocked: login's own error hint said "call login").
    from xuexitong_mcp import login as L
    from xuexitong_mcp.bsk import BskError
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    class HandoffBsk(FakeBsk):
        def __init__(self):
            super().__init__([])
            self.ensure_calls = []

        def ensure_session(self, **kw):
            self.ensure_calls.append(kw)
            self.tab = 42  # bound before the bootstrap raise, as in bsk.py
            raise BskError("login_required", "配置指定的 Profile 已跳转到学习通登录页")

    b = HandoffBsk()
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.ensure_calls == [{"renew_idle_readonly": True}]
    # Handoff parks the tab ON the login page; a redundant raw re-navigation
    # would be denied by the extension's login-page protection, so it is
    # skipped entirely (observed 2026-11-10).
    assert b.navs == []
    assert b.fills == [("#phone", "13800000000"), ("#pwd", "secret")]
    assert b.clicks == ["#loginBtn"]


def test_fill_and_submit_navigates_when_tab_elsewhere(monkeypatch):
    # Alive session whose tab is NOT on the login page: navigate must run.
    from xuexitong_mcp import login as L
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    class AliveBsk(FakeBsk):
        def __init__(self):
            super().__init__([])
            self.url = "https://i.mooc.chaoxing.com/space/index"

        def ensure_session(self, **kw):
            return

    b = AliveBsk()
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.navs == [LOGIN_URL]
    assert b.clicks == ["#loginBtn"]


def test_fill_and_submit_skips_navigate_when_already_on_login_url(monkeypatch):
    # Alive session already sitting on the passport login page (e.g. previous
    # attempt timed out on the slider): no redundant protected navigation.
    from xuexitong_mcp import login as L
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    class OnLoginBsk(FakeBsk):
        def __init__(self):
            super().__init__([])
            self.url = "https://passport2.chaoxing.com/login?fid=12&refer=x"

        def ensure_session(self, **kw):
            return

    b = OnLoginBsk()
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.navs == []
    assert b.clicks == ["#loginBtn"]


def test_fill_and_submit_propagates_login_required_without_tab(monkeypatch):
    # If the guard fires with no owned tab there is nothing to continue on.
    from xuexitong_mcp import login as L
    from xuexitong_mcp.bsk import BskError
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    class NoTabBsk(FakeBsk):
        def __init__(self):
            super().__init__([])

        def ensure_session(self, **kw):
            self.tab = None
            raise BskError("login_required", "no tab")

    b = NoTabBsk()
    with pytest.raises(BskError) as ei:
        LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert ei.value.code == "login_required"
    assert b.fills == []


def test_fill_and_submit_propagates_other_bind_errors(monkeypatch):
    from xuexitong_mcp import login as L
    from xuexitong_mcp.bsk import BskError
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    class DeadBsk(FakeBsk):
        def __init__(self):
            super().__init__([])

        def ensure_session(self, **kw):
            raise BskError("not_found", "session_window_closed")

    b = DeadBsk()
    with pytest.raises(BskError) as ei:
        LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert ei.value.code == "not_found"
    assert b.fills == []
