"""Regression tests: personal-space digital-textbook (数字教材) CRUD.

Endpoints were captured live from the cv-p.chaoxing.com SPA (real UI requests):
checkWfwfid enc exchange, teachMaterialList, uploadFile, addTeachMaterial
(form-urlencoded), deleteTeachMaterial (delEnc). All data here is synthetic;
no browser or network is used.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_textbook import CV, COVER_CDN  # noqa: E402
from xuexitong_mcp.xxt import XxtError, make_client  # noqa: E402


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
    c.log_level = "WARNING"
    c.settle = 0
    yield c
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()


def _client(cfg, monkeypatch, enc="spaceenc000"):
    c = make_client(cfg)
    monkeypatch.setattr(c, "_tb_enc", lambda: enc)
    return c


LIST_RESP = {"code": 200, "data": [
    {"id": 11027, "courseId": 269234271, "courseName": "[MCP测试]数字教材", "courseAuthor": "林云",
     "courseUnitName": "湖南食品药品职业学院", "coursePic": COVER_CDN + "obj1", "fid": "7838", "type": 0,
     "delEnc": "delenc111", "detailEnc": "detailenc111"},
]}


def test_list_parses_items(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)
    seen = {}

    def fake_on(host, body, **kw):
        seen["host"] = host
        seen["body"] = body
        return LIST_RESP

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_list()
    assert seen["host"] == CV
    assert "teachMaterialList" in seen["body"] and "spaceenc000" in seen["body"]
    assert out[0]["id"] == 11027 and out[0]["courseId"] == 269234271
    assert out[0]["name"] == "[MCP测试]数字教材" and out[0]["author"] == "林云"


def test_list_non200_raises(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda *a, **k: {"status": False})
    with pytest.raises(XxtError):
        c.textbook_list()


def test_detail_flat_fields_consistent_with_list(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)

    def fake_on(host, body, **kw):
        if "teachMaterialList" in body:
            return LIST_RESP
        return {"status": False}  # getCourseDetail limitation path

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_detail("11027")
    # flat fields match textbook_list's shape
    assert out["name"] == "[MCP测试]数字教材" and out["author"] == "林云"
    assert out["id"] == 11027 and out["courseId"] == 269234271
    assert out["item"]["courseName"] == "[MCP测试]数字教材"
    assert "limitation" in out  # getCourseDetail status:false documented


def test_enc_exchange(cfg, monkeypatch):
    c = make_client(cfg)
    monkeypatch.setattr(c, "_tb_portal_enc", lambda: "portalenc999")
    seen = {}

    def fake_on(host, body, **kw):
        seen["body"] = body
        return {"enc": "spaceenc777", "status": True}

    monkeypatch.setattr(c, "on", fake_on)
    assert c._tb_enc() == "spaceenc777"
    assert "checkWfwfid" in seen["body"] and "portalenc999" in seen["body"]


def test_create_uses_form_encoded_and_cover_cdn(cfg, monkeypatch, tmp_path):
    c = _client(cfg, monkeypatch)
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    monkeypatch.setattr(c, "_tb_upload_cover", lambda p: COVER_CDN + "objNEW")
    seen = {}

    def fake_on(host, body, **kw):
        seen["body"] = body
        return {"code": 200, "message": "添加成功!"}

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_create("[MCP测试]教材", "林云", str(cover), desc="测试简介")
    assert out["ok"] is True
    assert "addTeachMaterial" in seen["body"]
    assert "POST(" in seen["body"]                     # form-urlencoded helper
    assert "courseName" in seen["body"] and "spaceenc000" in seen["body"]
    assert COVER_CDN + "objNEW" in seen["body"]


def test_create_requires_name_author(cfg, monkeypatch, tmp_path):
    c = _client(cfg, monkeypatch)
    cover = tmp_path / "c.png"
    cover.write_bytes(b"x")
    with pytest.raises(XxtError):
        c.textbook_create("", "林云", str(cover))


def test_delete_uses_delenc(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)
    seen = []

    def fake_on(host, body, **kw):
        seen.append(body)
        if "teachMaterialList" in body:
            return LIST_RESP
        return {"code": 200, "message": "删除成功"}

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_delete("11027")
    assert out["ok"] is True and out["name"] == "[MCP测试]数字教材"
    delcall = seen[-1]
    assert "deleteTeachMaterial" in delcall
    assert "courseId=" in delcall and "269234271" in delcall
    assert "delenc111" in delcall                      # delEnc, not the space enc


def test_delete_missing_id_raises(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda *a, **k: LIST_RESP)
    with pytest.raises(XxtError):
        c.textbook_delete("99999")


def test_cover_rejects_bad_type_and_size(cfg, monkeypatch, tmp_path):
    c = _client(cfg, monkeypatch)
    bad = tmp_path / "cover.bmp"
    bad.write_bytes(b"BM" + b"0" * 32)
    with pytest.raises(XxtError):
        c._tb_upload_cover(str(bad))
    big = tmp_path / "big.png"
    big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 1))
    with pytest.raises(XxtError):
        c._tb_upload_cover(str(big))


# ------------------------------------------------ knowledge graph (course-graph backend reuse)
CTX = {"courseid": "269231810", "clazzid": "0", "cpi": "14089768", "ut": "t", "_name": "[MCP测试]教材"}


def _gclient(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)
    monkeypatch.setattr(c, "_tb_graph_ctx", lambda id: dict(CTX))
    return c


def test_graph_reads_list_and_tabs(cfg, monkeypatch):
    c = _gclient(cfg, monkeypatch)
    seen = []

    def fake_gget(url, params):
        seen.append((url, params))
        if "gettopicwoodsdata" in url:
            return {"status": True, "data": {"totalCount": 1, "topicWoodsData": [
                {"topicId": 901, "name": "合成知识点", "topicLabelArray": [{"name": "标签A"}], "citeCount": 2, "topicDesc": "简介"}]}}
        if "gettopicsetting" in url:
            return {"status": True, "data": {"topicModelData": [{"name": "知识图谱"}, {"name": "知识列表"}]}}
        return {}

    monkeypatch.setattr(c, "_gget", fake_gget)
    out = c.textbook_graph("11026")
    assert out["total"] == 1 and out["items"][0]["point_id"] == "901"
    assert out["items"][0]["name"] == "合成知识点" and out["graph_tabs"] == ["知识图谱", "知识列表"]
    assert seen[0][1]["courseid"] == "269231810" and seen[0][1]["clazzid"] == "0"


def test_graph_add_point_success_and_failure(cfg, monkeypatch):
    c = _gclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "_gget", lambda url, p: {"status": True, "data": {"topicId": 902}})
    out = c.textbook_graph_add_point("11026", "新知识点", kind="概念性")
    assert out["ok"] is True and out["point_id"] == "902"
    monkeypatch.setattr(c, "_gget", lambda url, p: {"status": False, "msg": "无权限"})
    out2 = c.textbook_graph_add_point("11026", "x")
    assert out2["ok"] is False and out2["write_outcome"] == "not_written"
    with pytest.raises(XxtError):
        c.textbook_graph_add_point("11026", "x", kind="不存在的类型")


def test_graph_point_properties(cfg, monkeypatch):
    c = _gclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "_gget", lambda url, p: {"status": True, "topicName": "知识点", "classify": 2,
                                                   "topicDesc": "描述", "topiclabelList": [{"name": "L"}],
                                                   "teachTarget": "目标", "studyHours": "2"})
    out = c.textbook_graph_point("11026", "901")
    assert out["name"] == "知识点" and out["kind"] == "概念性" and out["labels"] == ["L"]


def test_graph_set_point_verifies_readback(cfg, monkeypatch):
    c = _gclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "_gget", lambda url, p: {"status": True, "topicName": "知识点", "classify": 3,
                                                   "topicDesc": "新描述", "topiclabelList": [], "teachTarget": "", "studyHours": ""})
    posted = {}
    monkeypatch.setattr(c, "_gpost", lambda url, p: posted.update(p) or {"status": True})
    out = c.textbook_graph_set_point("11026", "901", kind="程序性", description="新描述")
    assert out["ok"] is True and posted["classify"] == 3 and posted["topicIds"] == "901"


def test_graph_delete_point(cfg, monkeypatch):
    c = _gclient(cfg, monkeypatch)
    posted = {}
    monkeypatch.setattr(c, "_gpost", lambda url, p: posted.update({"url": url, **p}) or {"status": True})
    out = c.textbook_graph_delete_point("11026", "901")
    assert out["ok"] is True and "deleteTopic" in posted["url"] and posted["topicId"] == "901"
    monkeypatch.setattr(c, "_gpost", lambda url, p: {"status": False, "msg": "拒"})
    out2 = c.textbook_graph_delete_point("11026", "901")
    assert out2["ok"] is False and out2["write_outcome"] == "not_written"


# ------------------------------------------------ chapters / 目录 (course-chapter backend reuse)
def _chclient(cfg, monkeypatch):
    c = _client(cfg, monkeypatch)
    monkeypatch.setattr(c, "_tb_graph_ctx", lambda id: dict(CTX))
    return c


def _tree():
    return {"success": True, "data": [
        {"id": 100, "title": "第一章", "layer": 1, "children": [{"id": 101, "title": "第一节", "layer": 2, "children": None}]},
        {"id": 200, "title": "第二章", "layer": 1, "children": None}]}


def test_chapters_reads_tree(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: _tree() if "get-knowledge-list" in js else {})
    out = c.textbook_chapters("11026")
    assert out["count"] == 3
    assert out["chapters"][0]["number"] == "1" and out["chapters"][1]["number"] == "1.1"
    assert out["chapters"][1]["parent_id"] == "100"


def test_chapters_invalid_not_empty(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: {"success": False})
    with pytest.raises(XxtError):
        c.textbook_chapters("11026")


def test_create_chapter_verifies_readback(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    state = {"created": False}

    def fake_on(host, js, **kw):
        if "get-knowledge-list" in js:
            t = _tree()
            if state["created"]:
                t["data"].append({"id": 300, "title": "新章节", "layer": 1, "children": None})
            return t
        if "createchapter" in js:
            state["created"] = True
            return {"id": 300}
        return {}

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_create_chapter("11026", "新章节")
    assert out["ok"] is True and out["chapter"]["chapter_id"] == "300"
    with pytest.raises(XxtError):
        c.textbook_create_chapter("11026", "")


def test_rename_chapter_verifies_readback(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    state = {"renamed": False}

    def fake_on(host, js, **kw):
        if "get-knowledge-list" in js:
            t = _tree()
            if state["renamed"]:
                t["data"][0]["title"] = "改名后"
            return t
        if "changename" in js:
            state["renamed"] = True
            return {"status": True}
        return {}

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_rename_chapter("11026", "100", "改名后")
    assert out["ok"] is True and out["chapter"]["title"] == "改名后"
    with pytest.raises(XxtError):
        c.textbook_rename_chapter("11026", "100", "")


def test_delete_chapter_counts_children(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    state = {"deleted": False}

    def fake_on(host, js, **kw):
        if "get-knowledge-list" in js:
            if state["deleted"]:
                return {"success": True, "data": [_tree()["data"][1]]}
            return _tree()
        if "deletechapter" in js:
            state["deleted"] = True
            return {"status": True}
        return {}

    monkeypatch.setattr(c, "on", fake_on)
    out = c.textbook_delete_chapter("11026", "100")
    assert out["ok"] is True and out["also_deleted_children"] == 1
    with pytest.raises(XxtError):
        c.textbook_delete_chapter("11026", "99999")


# ------------------------------------------------ knowledge graph export (Excel / Xmind)
def test_graph_export_saves_valid_file(cfg, monkeypatch, tmp_path):
    import base64 as _b64
    c = _chclient(cfg, monkeypatch)
    cfg.download_dir = str(tmp_path)

    def fake_on(host, js, **kw):
        if "export-knowledge-points" in js or "exportcoursetopicxmind" in js:
            return {"status": True, "data": "https://mooc1.chaoxing.com/import-export-ans/export-knowledge-points?courseId=269231810"}
        return {}

    monkeypatch.setattr(c, "on", fake_on)
    fake_zip = b"PK\x03\x04" + b"0" * 100
    monkeypatch.setattr(c.b, "eval", lambda js, **kw: {"ok": True, "b64": _b64.b64encode(fake_zip).decode(), "size": len(fake_zip)})
    out = c.textbook_graph_export("11026", "Excel")
    assert out["ok"] is True and out["size"] == len(fake_zip) and out["file"].endswith(".xlsx")
    with pytest.raises(XxtError):
        c.textbook_graph_export("11026", "PDF")


def test_graph_export_empty_graph_raises(cfg, monkeypatch, tmp_path):
    import base64 as _b64
    c = _chclient(cfg, monkeypatch)
    cfg.download_dir = str(tmp_path)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: {"status": True, "data": "https://mooc1.chaoxing.com/x"} if "export" in js else {})
    msg = "该课程下暂无知识点".encode("utf8")
    monkeypatch.setattr(c.b, "eval", lambda js, **kw: {"ok": True, "b64": _b64.b64encode(msg).decode(), "size": len(msg)})
    with pytest.raises(XxtError):
        c.textbook_graph_export("11026", "Excel")


def test_graph_export_credential_failure(cfg, monkeypatch, tmp_path):
    c = _chclient(cfg, monkeypatch)
    cfg.download_dir = str(tmp_path)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: {"status": False, "msg": "非教师无查询权限"} if "export" in js else {})
    with pytest.raises(XxtError):
        c.textbook_graph_export("11026", "Excel")


# ------------------------------------------------ build graph from chapter tree
def test_graph_from_chapters_builds_hierarchy(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: _tree() if "get-knowledge-list" in js else {})
    state = {"names": [], "sort_called": False}

    def fake_gget(url, p):
        if "woodsaddtopic" in url:
            state["names"].append(p["topic"])
            return {"status": True, "data": {"topicId": 900 + len(state["names"])}}
        return {}

    def fake_gpost(url, p):
        if "updatetopicsort" in url:
            state["sort_called"] = True
        return {"status": True}

    monkeypatch.setattr(c, "_gget", fake_gget)
    monkeypatch.setattr(c, "_gpost", fake_gpost)
    out = c.textbook_graph_from_chapters("11026")
    assert out["ok"] is True and out["created"] == 3 and out["chapters"] == 3
    # flat + 目录编号, no nesting (new-version graph forbids nested knowledge points)
    assert state["names"] == ["1 第一章", "1.1 第一节", "2 第二章"]
    assert state["sort_called"] is False


def test_graph_from_chapters_partial_failure(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: _tree() if "get-knowledge-list" in js else {})
    state = {"n": 0}

    def fake_gget(url, p):
        if "woodsaddtopic" in url:
            state["n"] += 1
            if state["n"] == 2:
                return {"status": False, "msg": "限流"}
            return {"status": True, "data": {"topicId": 900 + state["n"]}}
        return {}

    monkeypatch.setattr(c, "_gget", fake_gget)
    monkeypatch.setattr(c, "_gpost", lambda url, p: {"status": True})
    out = c.textbook_graph_from_chapters("11026")
    assert out["ok"] is False and out["write_outcome"] == "partial" and out["created"] == 1


def test_graph_from_chapters_empty_raises(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: {"success": True, "data": []} if "get-knowledge-list" in js else {})
    with pytest.raises(XxtError):
        c.textbook_graph_from_chapters("11026")


# ------------------------------------------------ materials / question bank thin wrappers
def test_materials_reads_list(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    monkeypatch.setattr(c, "on", lambda host, js, **kw: [{"material_id": "m1", "title": "资料A", "type": "pdf", "info": []}] if "coursedata" in js else {})
    out = c.textbook_materials("11026")
    assert out["count"] == 1 and out["materials"][0]["title"] == "资料A"


def test_bank_questions_parses_folders_and_questions(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    resp = {"status": True, "total": 2, "questionBankRelationList": [
        {"type": 0, "id": 10, "dirName": "文件夹A", "questionCount": 3},
        {"type": 1, "questionId": 20, "questionBank": {"content": "<p>题干<b>内容</b></p>", "courseQuestionTypeName": "单选题", "difficulty": 2}}]}
    monkeypatch.setattr(c, "on", lambda host, js, **kw: resp if "qbank/search" in js else {})
    out = c.textbook_bank_questions("11026")
    assert out["total"] == 2 and len(out["items"]) == 2
    assert out["items"][0]["kind"] == "folder" and out["items"][0]["name"] == "文件夹A"
    assert out["items"][1]["kind"] == "question" and out["items"][1]["stem"] == "题干 内容"


def test_bank_questions_empty_bank(cfg, monkeypatch):
    c = _chclient(cfg, monkeypatch)
    # empty bank: no questionBankRelationList key, only total/pageInfo
    monkeypatch.setattr(c, "on", lambda host, js, **kw: {"total": 0, "courseIds": [269231810], "pageInfo": {}} if "qbank/search" in js else {})
    out = c.textbook_bank_questions("11026")
    assert out["total"] == 0 and out["items"] == []
