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
