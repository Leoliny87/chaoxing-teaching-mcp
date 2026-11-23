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


@pytest.mark.parametrize("folder_args,folder_id", [({}, "0"), ({"material_folder_id": "42"}, "42")])
def test_insert_course_material_uses_folder_and_binds_selected_id(client, monkeypatch, folder_args, folder_id):
    from xuexitong_mcp import server as srv

    course = client.ctx("1")
    client.cfg.write_allow_courses = [course.id]
    monkeypatch.setattr(srv, "client", lambda: client)
    monkeypatch.setattr(srv, "_state", dict(srv._state, client=client, cfg=client.cfg, allowed=None, budget=None))
    monkeypatch.setattr(client, "find_chapter", lambda *a: {"chapter_id": "10", "title": "章节", "number": "1.1", "layer": 2})
    seen = []
    item = {"dataId": 8, "dataName": "工单.pdf", "cataid": 100000019,
            "content": {"objectId": "a" * 32, "suffix": "pdf", "size": 13}}
    rows = [item]

    def get_resources(host, js, **kwargs):
        assert f"rootId={folder_id}'" in js
        seen.append(host)
        return {"valid": True, "items": rows}

    inserted = []
    monkeypatch.setattr(client, "on", get_resources)
    monkeypatch.setattr(client, "_insert_object", lambda *a: inserted.append(a) or {"ok": True})
    insert = srv._wrap(srv.insert_chapter_material, "write")
    args = dict(course=course.id, chapter="章节", card_id="5", material="工单.pdf", **folder_args)
    draft = insert(**args)
    assert draft["ok"] and draft["details"]["material_folder_id"] == folder_id
    assert draft["details"]["material_id"] == "8" and len(seen) == 1 and not inserted

    refused = insert(**{**args, "material_folder_id": "99"}, confirm=True, plan_id=draft["plan_id"])
    assert refused["ok"] is False and len(seen) == 1 and not inserted

    draft = insert(**args)
    rows.append({**item, "dataId": 9, "content": {**item["content"], "objectId": "b" * 32}})
    result = insert(**args, confirm=True, plan_id=draft["plan_id"])
    assert result["ok"] and len(seen) == 3
    assert inserted == [(course.id, "10", "5", "downloadfile", "a" * 32, 13, "工单.pdf", ".pdf")]


def test_upload_tools_are_executable():
    from xuexitong_mcp import server as srv
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    for n in ("upload_material", "insert_chapter_file"):
        assert kinds[n] == "write" and n not in srv._PREVIEW_ONLY_TOOLS


def test_upload_preview_shows_final_safe_name(tmp_path, monkeypatch):
    # Regression (live 2026-11-23): the platform sanitizes the material name via
    # safe_name (brackets -> dashes). The preview must show BOTH the local filename
    # and the final material name the snapshot/upload will use, reusing safe_name.
    from xuexitong_mcp import server as srv
    cfg = Config()
    cfg.log_dir = tmp_path / "logs"
    cfg.upload_allow_dirs = [str(tmp_path)]
    cfg.write_allow_courses = ["合成课程"]
    c = make_client(cfg)
    course = Course(id="1", name="合成课程", cpi="3", clazz_id="2", enc="E", t="9",
                    classes=[{"clazz_id": "2", "name": "测试"}])
    monkeypatch.setattr(c, "ctx", lambda q, refresh=False: course)
    monkeypatch.setattr(c, "course", lambda q: course)
    monkeypatch.setattr(c, "courses", lambda refresh=False: [course])
    monkeypatch.setattr(srv, "client", lambda: c)
    monkeypatch.setattr(srv, "_state", dict(srv._state, client=c, cfg=cfg, allowed=None,
                                            budget=None, profile="teacher"))
    name = "[MCP测试]合成资料.txt"
    p = tmp_path / name
    p.write_bytes(b"synthetic")
    up = srv._wrap({n: f for n, k, d, f in srv.TOOLS}["upload_material"], "write")
    pv = up("合成课程", str(p), confirm=False)
    assert pv["details"]["file"] == name
    assert pv["details"]["material_name"] == safe_name(name) == "-MCP测试-合成资料.txt"
    # consistency: the snapshot the upload actually uses carries the same final name
    tmp, snap, meta = c._snapshot(str(p), pv["details"]["sha256"])
    assert snap.name == pv["details"]["material_name"]
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)  # clean the test snapshot
