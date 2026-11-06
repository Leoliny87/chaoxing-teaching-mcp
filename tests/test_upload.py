"""Upload layer: hash-bound snapshots and the module data built for chapter files."""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_upload import hsize, safe_name  # noqa: E402
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
    monkeypatch.setattr(c.b, "navigate", lambda *a, **k: "")
    monkeypatch.setattr(c.b, "upload_selector", lambda sel, f: {"file_names": [Path(f).name]})
    return c


def _file(tmp_path, name="课件.pdf", data=b"%PDF-1.4 test"):
    p = tmp_path / name
    p.write_bytes(data)
    return p, hashlib.sha256(data).hexdigest()


def test_hsize_and_names():
    assert hsize(592) == "592 B" and hsize(43151) == "42.14 KB" and hsize(64044) == "62.54 KB" and hsize(3 * 1024 ** 2) == "3.00 MB"
    assert safe_name('a:b?"c.pdf') == "a-b--c.pdf"


def test_snapshot_refuses_changed_content(client, tmp_path):
    p, digest = _file(tmp_path)
    with pytest.raises(XxtError):
        client._snapshot(str(p), "0" * 64)
    with pytest.raises(XxtError):
        client._snapshot(str(p), "")
    tmp, snap, meta = client._snapshot(str(p), digest)
    assert snap.read_bytes() == p.read_bytes() and meta["sha256"] == digest and tmp.exists()


def test_stage_refuses_mismatched_page_bytes(client, tmp_path, monkeypatch):
    p, digest = _file(tmp_path)
    tmp, snap, meta = client._snapshot(str(p), digest)
    answers = iter([True, {"name": snap.name, "size": meta["size"], "sha256": "f" * 64}])
    monkeypatch.setattr(client, "here", lambda js, **k: next(answers))
    with pytest.raises(XxtError):
        client._stage(snap, meta)


def _wire(client, monkeypatch, meta_size, digest, chain):
    seq = iter([True, None, chain])

    def here(js, **k):
        v = next(seq)
        return {"name": "x", "size": meta_size, "sha256": digest} if v is None else v
    monkeypatch.setattr(client, "here", here)
    monkeypatch.setattr(client, "on", lambda *a, **k: True)
    seen = {}
    monkeypatch.setattr(client, "insert_chapter_module", lambda *a, **k: seen.update(args=a, kw=k) or {"ok": True, "mid": "m"})
    return seen


def test_chapter_doc_gets_pagenum_and_task_point(client, tmp_path, monkeypatch):
    p, digest = _file(tmp_path)
    seen = _wire(client, monkeypatch, p.stat().st_size, digest, {"stage": "done", "objectid": "a" * 32, "size": 13, "suffix": "pdf"})
    monkeypatch.setattr(client, "_call", lambda host, path, *a, **k: {"http": 200, "json": {"status": "success", "pagenum": 3}})
    r = client.insert_chapter_file("1", "10", "5", str(p), "文档", digest)
    course, ch, card, module, data = seen["args"]
    assert module == "insertdoc" and data["pagenum"] == "3" and data["jobid"] == data["_jobid"] and data["type"] == ".pdf"
    assert data["name"] == "课件.pdf" and data["hsize"] == "13 B" and r["object_id"] == "a" * 32


def test_chapter_image_is_inline_with_attachment(client, tmp_path, monkeypatch):
    p, digest = _file(tmp_path, "图.png", b"\x89PNG")
    seen = _wire(client, monkeypatch, p.stat().st_size, digest, {"stage": "done", "objectid": "b" * 32, "size": 4, "suffix": "png"})
    client.insert_chapter_file("1", "10", "5", str(p), "图片", digest)
    html, att = seen["kw"]["inline_html"], seen["kw"]["inline_attachment"]
    assert f"star4/{'b' * 32}/origin.png" in html and att["module"] == "insertimage" and att["mid"] in html
    assert len(att["_jobid"]) == 19 and att["_jobid"].isdigit()


def test_chapter_file_checks_kind_and_suffix(client, tmp_path):
    p, digest = _file(tmp_path, "a.exe", b"MZ")
    with pytest.raises(XxtError):
        client.insert_chapter_file("1", "10", "5", str(p), "文档", digest)
    with pytest.raises(XxtError):
        client.insert_chapter_file("1", "10", "5", str(p), "压缩包", digest)


def test_upload_tools_are_executable():
    from xuexitong_mcp import server as srv
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    for n in ("upload_material", "insert_chapter_file"):
        assert kinds[n] == "write" and n not in srv._PREVIEW_ONLY_TOOLS
