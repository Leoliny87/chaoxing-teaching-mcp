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
        self.url = ""

    def href(self):
        return self.url

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

def test_collect_credentials_form_roundtrip(monkeypatch):
    # First-run experience: the form URL must be discoverable on stderr even
    # when no browser can be opened, and the token-protected POST must land
    # the credentials in the store (school-wide rollout: headless installs).
    import io
    import re as _re
    import threading
    import time as _time
    import urllib.parse
    import urllib.request

    class Store:
        def __init__(self):
            self.creds = {}

        def get_password(self, a):
            return self.creds.get(a)

        def set_password(self, a, p):
            self.creds[a] = p

        def delete_password(self, a):
            self.creds.pop(a, None)

    store = Store()
    err = io.StringIO()
    monkeypatch.setattr(L.sys, "stderr", err)
    out = {}

    def run():
        try:
            out["account"] = L.collect_credentials(store, open_browser=False, timeout=15)
        except Exception as e:  # pragma: no cover - failure path
            out["error"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    url = None
    for _ in range(200):
        m = _re.search(r"http://127\.0\.0\.1:\d+/", err.getvalue())
        if m:
            url = m.group(0)
            break
        _time.sleep(0.05)
    assert url, f"form URL not printed to stderr: {err.getvalue()!r}"
    page = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
    tok = _re.search(r'name="token" value="([^"]+)"', page).group(1)
    body = urllib.parse.urlencode(
        {"token": tok, "account": "13800000000", "password": "secret"}).encode()
    resp = urllib.request.urlopen(url.rstrip("/") + "/submit", data=body, timeout=5).read().decode("utf-8")
    assert "已保存凭据" in resp
    th.join(timeout=5)
    assert out.get("account") == "13800000000"
    assert store.creds == {"13800000000": "secret"}


def test_collect_credentials_rejects_bad_token(monkeypatch):
    import io
    import re as _re
    import threading
    import time as _time
    import urllib.parse
    import urllib.request

    class Store:
        def __init__(self):
            self.creds = {}

        def get_password(self, a):
            return self.creds.get(a)

        def set_password(self, a, p):
            self.creds[a] = p

    store = Store()
    err = io.StringIO()
    monkeypatch.setattr(L.sys, "stderr", err)
    out = {}

    def run():
        try:
            out["account"] = L.collect_credentials(store, open_browser=False, timeout=2)
        except Exception as e:
            out["error"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    url = None
    for _ in range(200):
        m = _re.search(r"http://127\.0\.0\.1:\d+/", err.getvalue())
        if m:
            url = m.group(0)
            break
        _time.sleep(0.05)
    assert url
    body = urllib.parse.urlencode(
        {"token": "wrong-token", "account": "13800000000", "password": "secret"}).encode()
    resp = urllib.request.urlopen(url.rstrip("/") + "/submit", data=body, timeout=5).read().decode("utf-8")
    assert "令牌无效" in resp
    th.join(timeout=6)
    assert isinstance(out.get("error"), L.LoginError)  # timed out, nothing stored
    assert store.creds == {}
