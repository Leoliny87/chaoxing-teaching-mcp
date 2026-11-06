"""Task engine: time conversion and request guards (live chain verified 2026-11-07)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_task import epoch_ms  # noqa: E402
from xuexitong_mcp.xxt import Course, XxtError, make_client  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    cfg = Config()
    cfg.log_dir = tmp_path / "logs"
    c = make_client(cfg)
    course = Course(id="1", name="合成课程", cpi="3", clazz_id="2", enc="E", t="9", classes=[{"clazz_id": "2", "name": "测试"}])
    monkeypatch.setattr(c, "ctx", lambda q, refresh=False: course)
    monkeypatch.setattr(c, "course", lambda q: course)
    return c


def test_epoch_ms_is_beijing_time():
    assert epoch_ms("2026-11-07 08:00") == 1794009600000 == epoch_ms("2026-11-07 08:00:00")
    with pytest.raises(XxtError):
        epoch_ms("next week")


def test_create_task_validates_before_any_request(client, monkeypatch):
    monkeypatch.setattr(client, "on", lambda *a, **k: pytest.fail("no request expected"))
    with pytest.raises(XxtError):
        client.create_task("1", "t", "", "2026-11-08 08:00", "2026-11-07 08:00", [])
    with pytest.raises(XxtError):
        client.create_task("1", "", "", "2026-11-07 08:00", "2026-11-08 08:00", [])
    with pytest.raises(XxtError):
        client.create_task("1", "t", "", "2026-11-07 08:00", "2026-11-08 08:00", ["bad id'"])


def test_publish_task_rejects_foreign_plugin_url_and_missing_class(client, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "on", lambda host, js, **k: calls.append(host) or {"stage": "ok", "url": "https://evil.example/x"})
    with pytest.raises(XxtError):
        client.publish_task("1", "BEDCabc@0123456789abcdef", ["2"])
    seq = iter([{"stage": "ok", "url": "https://mooc2-ans.chaoxing.com/mooc2-ans/exam/test/publish-plugin?courseid=1&cpi=3"},
                [{"classId": "9", "className": "别的", "token": "a" * 32}]])
    monkeypatch.setattr(client, "on", lambda host, js, **k: next(seq))
    with pytest.raises(XxtError):
        client.publish_task("1", "BEDCabc@0123456789abcdef", ["2"])


def test_task_tools_registered():
    from xuexitong_mcp import server as srv
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    assert kinds["create_teaching_task"] == "write" and kinds["publish_teaching_task"] == "write"
