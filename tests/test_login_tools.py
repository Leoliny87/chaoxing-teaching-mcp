import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import server as srv


def test_login_logout_registered():
    names = {n for n, _, _, _ in srv.TOOLS}
    assert "login" in names and "logout" in names
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    assert kinds["login"] == "local_write" and kinds["logout"] == "local_write"


def test_login_tool_returns_status_without_password(monkeypatch):
    from xuexitong_mcp import login as L
    from xuexitong_mcp.config import Config
    monkeypatch.setattr(L, "run_login", lambda cfg, bsk, **k: {
        "ok": True, "account": "138", "url": "https://i.mooc.chaoxing.com/space/index",
        "needs_slider": False, "stage": "logged_in"})

    class C:
        b = object()
    monkeypatch.setattr(srv, "client", lambda: C())
    monkeypatch.setitem(srv._state, "cfg", Config())
    raw = dict((n, f) for n, _, _, f in srv.TOOLS)["login"]
    r = raw()
    assert r["ok"] is True and "password" not in r