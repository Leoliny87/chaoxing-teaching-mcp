import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import login as L
from xuexitong_mcp.config import Config


class FakeBsk:
    def __init__(self):
        self.tab = 7
        self.cfg = type("C", (), {"t_navigate": 40})()
        self.fills = []
        self.clicks = []

    def ensure_session(self, **kw):
        return

    def run(self, args, timeout=None, session=True):
        return {}

    def navigate(self, url, **kw):
        return url

    def eval(self, js, **kw):
        if "location.href" in js:
            return "https://i.mooc.chaoxing.com/space/index"
        return True

    def fill_selector(self, selector, value):
        self.fills.append((selector, value))
        return {}

    def click_selector(self, selector, **kw):
        self.clicks.append(selector)
        return {}


def test_run_login_with_stored_credentials(monkeypatch):
    cfg = Config()
    cfg.login_account = "13800000000"

    class Store:
        def get_password(self, a):
            return "secret"

        def set_password(self, a, p):
            pass

        def delete_password(self, a):
            pass

    monkeypatch.setattr(L, "collect_credentials", lambda *a, **k: pytest.fail("should not open form"))
    r = L.run_login(cfg, FakeBsk(), store=Store(), open_browser=False)
    assert r["ok"] is True and r["account"] == "13800000000"
    assert "secret" not in str(r)


def test_run_login_collects_when_no_credentials(monkeypatch):
    cfg = Config()
    cfg.login_account = ""

    class Store:
        def __init__(self):
            self.pwd = None

        def get_password(self, a):
            return self.pwd

        def set_password(self, a, p):
            self.pwd = p

        def delete_password(self, a):
            pass

    store = Store()

    def fake_collect(s, **k):
        s.set_password("13900000000", "secret")
        return "13900000000"

    monkeypatch.setattr(L, "collect_credentials", fake_collect)
    r = L.run_login(cfg, FakeBsk(), store=store, open_browser=False)
    assert r["account"] == "13900000000"


def test_run_logout_deletes():
    cfg = Config()
    cfg.login_account = "13800000000"

    class Store:
        def delete_password(self, a):
            self.deleted = a

    store = Store()
    r = L.run_logout(cfg, store=store)
    assert r["ok"] is True and store.deleted == "13800000000"


def test_remember_account_persists_and_reloads(tmp_path):
    from xuexitong_mcp.config import load
    p = tmp_path / "config.toml"
    p.write_text('profile = "teacher"\n', encoding="utf-8")
    cfg = Config()
    cfg.path = p
    cfg.login_account = ""
    L._remember_account(cfg, "13800000000")
    assert cfg.login_account == "13800000000"
    assert 'login_account = "13800000000"' in p.read_text(encoding="utf-8")
    assert load(p).login_account == "13800000000"