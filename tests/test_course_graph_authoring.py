"""Regression tests for native graph authoring using only synthetic fixtures."""

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import ops_course_graph_authoring as graph
from xuexitong_mcp.xxt import XxtError


C = SimpleNamespace(id="5", cpi="7", clazz_id="8")
NODE = {"point_id": "11", "node_id": "12", "name": "示例"}
URL = "https://mooc1.chaoxing.com/edit/chapters/5/12?classId=8&microTopicId=11&cpi=7"
MEDIA = '<iframe module="insertdoc" data="{&quot;mid&quot;:&quot;31&quot;,&quot;objectid&quot;:&quot;doc&quot;}"></iframe>'


def named_tools(api):
    funcs = {}

    def add(kind, desc):
        def register(fn):
            funcs[fn.__name__] = fn
            return fn

        return register

    api.ctx.return_value = C
    graph.register_graph_authoring(
        add, lambda: api, lambda _: C, lambda c, a, bind, **k: {"bind": bind, **k}
    )
    return funcs


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("https", "http"),
        URL.replace("5/12", "51/12"),
        URL + "&cpi=7",
        URL.replace("mooc1.", "outside."),
        URL + "&returnUrl=elsewhere",
        URL.replace("cpi=7", "cpi=9"),
    ],
)
def test_editor_scope(url):
    with pytest.raises(XxtError):
        graph.check_editor(C, url)
    graph.check_editor(C, URL)


def test_fill_with_attachment_preserves_exact_metadata_and_no_duplicates(monkeypatch):
    api = Mock()
    card = {"nodeid": "12", "id": 19, "description": MEDIA, "title": "页面"}
    api._call.side_effect = lambda host, url, *args: card.update(
        description=args[1]["description"]
    )
    monkeypatch.setattr(graph, "native_nodes", lambda *args: [NODE])
    monkeypatch.setattr(graph, "get_cards", lambda *args: [copy.deepcopy(card)])
    tools = named_tools(api)
    fill = tools["fill_knowledge_bodies"]
    args = ("5", URL, {"11": "选择 & 核对"})
    preview = fill(*args)
    api._call.assert_not_called()
    assert (
        fill(*args, confirm=True, **preview["bind"])["points"][0]["status"]
        == "verified"
    )
    assert card["description"] == "<p>选择 &amp; 核对</p>" + MEDIA
    assert '"mid": "31"' in api._call.call_args.args[-1]["attachments"]
    next_preview = fill(*args)
    assert (
        fill(*args, confirm=True, **next_preview["bind"])["points"][0]["status"]
        == "preserved"
    )
    assert api._call.call_count == 1


def test_digest_mismatch_preserves_concurrent_edit(monkeypatch):
    api = Mock()
    card = {"nodeid": "12", "id": 19, "description": "", "title": "导引"}
    monkeypatch.setattr(graph, "native_nodes", lambda *args: [NODE])
    monkeypatch.setattr(graph, "get_cards", lambda *args: [copy.deepcopy(card)])
    fill = named_tools(api)["fill_knowledge_bodies"]
    args = ("5", URL, {"11": "内容"})
    preview = fill(*args)
    card["title"] = "已改名"
    result = fill(*args, confirm=True, **preview["bind"])
    assert (
        result["ok"] is False
        and result["points"][0]["status"] == "changed_since_preview"
    )
    api._call.assert_not_called()


def test_unknown_attachment_metadata_fails_closed():
    with pytest.raises(XxtError):
        graph.attachments(
            {"description": "<iframe module='insertdoc' data='{}'></iframe>"}
        )
    assert graph.attachments(
        {"description": "", "attachments": '[{"native":"keep"}]'}
    ) == [{"native": "keep"}]


def test_links_readback_scoped_to_course_and_endpoint():
    url = "https://mooc1.chaoxing.com" + graph._VISIT + "?courseId=5&amp;knowledgeId=77"
    foreign = url.replace("courseId=5", "courseId=55")
    wrong_host = url.replace("mooc1.", "other.")
    assert graph.chapter_links(
        "".join(f'<a href="{s}">查看</a>' for s in [url, foreign, wrong_host, url]), 5
    ) == ["77"]


def test_add_chapter_link_preserves_native_fields():
    api = Mock()
    api.knowledge_points.return_value = [{"point_id": "11"}]
    api.chapters.return_value = [{"chapter_id": "77", "title": "<验收>"}]
    p = {
        "status": True,
        "classify": 3,
        "topicDesc": "<p>概念</p>",
        "topiclabelList": [{"id": 23}],
        "cognize": 2,
        "teachTarget": "目标",
        "studyHours": "1",
    }
    api._get.side_effect = lambda path, fields: (
        p if path.endswith("edittopicproperty") else {"status": True, "data": p}
    )
    api._mp.return_value = {}
    api._post.side_effect = lambda path, fields: p.update(topicDesc=fields["topicDesc"])
    add = named_tools(api)["add_point_chapter_links"]
    args = ("5", "11", ["77"])
    preview = add(*args)
    assert add(*args, confirm=True, **preview["bind"]) == {
        "ok": True,
        "added": ["77"],
        "chapter_ids": ["77"],
    }
    form = api._post.call_args.args[1]
    assert (
        form["topicDesc"].startswith("<p>概念</p>")
        and "&lt;验收&gt;" in form["topicDesc"]
    )
    assert (form["topicLabelIds"], form["cognize"], form["teachTargert"]) == (
        "23",
        2,
        "目标",
    )


def test_resource_missing_from_card_rejects_read():
    api = Mock()
    api.chapter_cards.return_value = {
        "chapter_id": "7",
        "cards": [{"card_id": "8", "truncated": False, "content_html": MEDIA}],
    }
    with pytest.raises(XxtError):
        named_tools(api)["get_resource_point_links"]("5", "7", "8", "22")
    api._call.assert_not_called()


def test_ideology_removal_preserves_other_labels_and_fields():
    api = Mock()
    api.knowledge_points.return_value = [{"point_id": "11"}]
    api.knowledge_labels.return_value = [{"name": "课程思政", "label_id": "23"}]
    p = {
        "status": True,
        "classify": 1,
        "topicDesc": "保留",
        "topiclabelList": [{"id": 23}, {"id": 78}],
        "cognize": 3,
    }
    api._get.return_value = p
    api._post.side_effect = lambda path, fields: p.update(
        topiclabelList=[{"id": n} for n in fields["topicLabelIds"].split(",")]
    )
    api._graph_nodes.return_value = [{"id": 11, "tag": "78"}]
    f = named_tools(api)["set_point_ideology_membership"]
    preview = f("5", "11", False)
    result = f("5", "11", False, confirm=True, **preview["bind"])
    assert result == {"ok": True, "point_id": "11", "included": False}
    assert api._post.call_args.args[1]["cognize"] == 3


def test_card_display_already_enabled_does_not_click():
    api = Mock()
    api._get.return_value = {"status": True, "data": {"topicCard": 1, "teachTarget": 0}}
    f = named_tools(api)["set_graph_point_card_display"]
    preview = f("5", True)
    assert f("5", True, confirm=True, **preview["bind"])["ok"]
    api.here.assert_not_called()


def test_long_native_resource_id_and_large_card():
    api = Mock()
    mid = "12345678901234567890123456"
    api.chapter_cards.return_value = {
        "chapter_id": "7",
        "cards": [{"card_id": "8", "truncated": True, "content_html": "…"}],
    }
    api._read_card.return_value = {
        "nodeid": "7",
        "id": "8",
        "description": MEDIA.replace("31", mid),
    }
    assert graph.resource(api, C, "7", "8", mid)["mid"] == mid


def test_native_resource_read_write_union_and_exact_readback():
    api = Mock()
    api.chapter_cards.return_value = {
        "chapter_id": "7",
        "cards": [{"card_id": "8", "truncated": False, "content_html": MEDIA}],
    }
    api.knowledge_points.return_value = [{"point_id": "12"}]
    selected = ["11"]

    def request(host, path, *args):
        if args:
            assert args[1]["topicIds"] == "11,12,"
            selected.append("12")
            return {"http": 200, "json": {"status": True}}
        return {
            "http": 200,
            "json": {"status": True, "data": {"origin": ",".join(selected) + ","}},
        }

    api._call.side_effect = request
    add = named_tools(api)["add_resource_point_links"]
    args = ("5", "7", "8", "31", ["12"])
    preview = add(*args)
    assert add(*args, confirm=True, **preview["bind"]) == {
        "ok": True,
        "mid": "31",
        "point_ids": ["11", "12"],
    }


def test_placeholder_removed_without_reserializing_attachments_or_styles():
    text = '<p title="1">&#x31;</p>' + MEDIA + "<style>.a{color:red}</style>"
    assert not graph.has_prose({"description": text})
    assert (
        graph.placeholder_free_html(text)
        == '<p title="1"></p>' + MEDIA + "<style>.a{color:red}</style>"
    )
    assert graph.placeholder_free_html("<p>工艺1</p>") == "<p>工艺1</p>"


def test_rendered_links_pass_only_numeric_ids_to_python():
    api = Mock()
    api.knowledge_points.return_value = [{"point_id": "11"}]
    api.on.return_value = ["99"]
    result = named_tools(api)["get_rendered_point_chapter_links"]("5", ["11"], True)
    assert result["points"] == [{"point_id": "11", "chapter_ids": ["99"]}]
    source = api.on.call_args.args[1]
    assert "d.body.innerHTML" not in source and "return [...ids]" in source
