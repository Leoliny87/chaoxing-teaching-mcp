import base64
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.config import Config
from xuexitong_mcp.xxt import Course, M2, XxtError, make_client


@pytest.fixture()
def client(tmp_path):
    cfg = Config()
    cfg.log_dir = tmp_path / "logs"
    cfg.download_dir = tmp_path / "downloads"
    c = make_client(cfg)
    monkeypatch_course = Course(id="1", name="合成课程", cpi="3")
    c.ctx = lambda q, refresh=False: monkeypatch_course
    return c


def _wire(client, raw):
    def fake_on(host, body, **kw):
        if host == M2:
            return {"status": True, "data": "https://mooc1.chaoxing.com/import-export-ans/export?enc=x"}
        return True
    client.on = fake_on
    client.b.eval = lambda js, **kw: {"ok": True, "b64": base64.b64encode(raw).decode(), "size": len(raw)}


def test_export_excel_saves_valid_file(client):
    raw = b"PK\x03\x04" + b"xlsx-bytes"
    _wire(client, raw)
    r = client.export_course_graph("1", "Excel")
    assert r["ok"] is True
    assert r["file"].endswith(".xlsx")
    assert Path(r["file"]).read_bytes() == raw


def test_export_xmind_extension(client):
    raw = b"PK\x03\x04" + b"xmind-bytes"
    _wire(client, raw)
    r = client.export_course_graph("1", "Xmind")
    assert r["ok"] is True and r["file"].endswith(".xmind")


def test_export_bad_magic_not_ok(client):
    _wire(client, b"<html>error</html>")
    r = client.export_course_graph("1", "Excel")
    assert r["ok"] is False


def test_export_bad_format_raises(client):
    with pytest.raises(XxtError):
        client.export_course_graph("1", "PDF")


def test_export_no_credential_raises(client):
    client.on = lambda host, body, **kw: {"status": False, "msg": "非教师"}
    with pytest.raises(XxtError):
        client.export_course_graph("1", "Excel")