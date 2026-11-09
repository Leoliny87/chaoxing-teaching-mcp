import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import LoginAutomator, LOGIN_URL


class FakeBsk:
    def __init__(self, urls):
        self.urls = iter(urls)
        self.evals = []
        self.navs = []

    def navigate(self, url, **kw):
        self.navs.append(url)
        return url

    def eval(self, js, **kw):
        self.evals.append(js)
        if "location.href" in js:
            return next(self.urls)
        return True


def test_fill_and_submit_targets_fields():
    b = FakeBsk([])
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.navs == [LOGIN_URL]
    joined = "\n".join(b.evals)
    assert "getElementById('phone')" in joined
    assert "getElementById('pwd')" in joined
    assert "getElementById('loginBtn')" in joined
    assert "13800000000" in joined


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