"""Course material pagination and complete post-write inventories."""
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.xxt import Course, M2, XxtError, make_client  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    instance = make_client(Config(log_dir=tmp_path))
    course = Course(id="1", name="课程", cpi="3", clazz_id="2")
    monkeypatch.setattr(instance, "ctx", lambda _: course)
    return instance


def _item(number, *, typ="pdf"):
    return {"id": str(number), "title": f"资料 {number}", "type": typ,
            "info": ["10 KB"], "download": True, "open": "0"}


def _page(folder, page, total, items):
    return {"course_id": "1", "folder_id": folder, "page": page, "pages": total,
            "size": len(items), "items": items}


def _mock_listing(monkeypatch, client, pages):
    calls = []

    def on(host, body, **_kwargs):
        assert host == M2
        url = re.search(r'''(?:fetch|F)\((["'])(.*?)\1''', body)[2]
        query = parse_qs(urlsplit(url).query)
        folder = query.get("dataId", ["0"])[0]
        page = int(query.get("pages", ["1"])[0])
        calls.append((folder, page))
        reply = pages[(folder, page)]
        if "currentPageNo" in body or reply is None:
            return reply
        # The pre-fix listing parsed the first page directly and had no metadata.
        return [{**row, "folder": row["type"] == "afolder", "material_id": row["id"]}
                for row in reply["items"]]

    monkeypatch.setattr(client, "on", on)
    return calls


def test_folder_lists_all_36_files_in_site_order(monkeypatch, client):
    folder = _item(100, typ="afolder")
    first = [_item(n) for n in range(200, 230)]
    second = [_item(n) for n in range(230, 236)]
    second[0].update(title="网页岗位仿真.html", type="html")
    calls = _mock_listing(monkeypatch, client, {
        ("0", 1): _page("0", 1, 1, [folder]),
        ("100", 1): _page("100", 1, 2, first),
        ("100", 2): _page("100", 2, 2, second),
    })

    found = client.folder_materials("1", folder["title"])

    assert [r["id"] for r in found] == [str(n) for n in range(200, 236)]
    assert found[30] == {"id": "230", "title": "网页岗位仿真.html", "folder": False, "download": True, "open": "0"}
    assert calls == [("0", 1), ("100", 1), ("100", 2)]


def test_root_inventories_and_folder_lookup_read_past_first_page(monkeypatch, client):
    folder = _item(100, typ="afolder")
    calls = _mock_listing(monkeypatch, client, {
        ("0", 1): _page("0", 1, 2, [_item(n) for n in range(200, 230)]),
        ("0", 2): _page("0", 2, 2, [folder]),
        ("100", 1): _page("100", 1, 1, [_item(500)]),
    })

    root = client.materials("1")
    found = client.folder_materials("1", folder["title"])

    assert len(root) == 31
    assert root[-1] == {"material_id": "100", "title": folder["title"], "type": "afolder", "info": ["10 KB"]}
    assert found == [{"id": "500", "title": "资料 500", "folder": False, "download": True, "open": "0"}]
    assert calls == [("0", 1), ("0", 2), ("0", 1), ("0", 2), ("100", 1)]


@pytest.mark.parametrize("total", [0, 1])
def test_verified_empty_folder(monkeypatch, client, total):
    calls = _mock_listing(monkeypatch, client, {("0", 1): _page("0", 1, total, [])})
    assert client.folder_materials("1") == []
    assert calls == [("0", 1)]


def test_verified_subfolder_accepts_official_zero_page_tuple(monkeypatch, client):
    folder = _item(100, typ="afolder")
    calls = _mock_listing(monkeypatch, client, {
        ("0", 1): _page("0", 1, 1, [folder]),
        ("100", 1): _page("100", 0, 0, []),
    })

    assert client.folder_materials("1", "100") == []
    assert calls == [("0", 1), ("100", 1)]


@pytest.mark.parametrize("overrides", [
    {"course_id": "999"},
    {"folder_id": "999"},
    {"course_id": None},
    {"folder_id": None},
    {"page": None},
    {"page": False},
    {"pages": 1},
    {"size": None},
    {"size": 1},
    {"items": [_item(7)], "size": 1},
])
def test_zero_page_tuple_rejects_unverified_identity_or_contradictory_fields(monkeypatch, client, overrides):
    calls = _mock_listing(monkeypatch, client, {("0", 1): {**_page("0", 0, 0, []), **overrides}})
    with pytest.raises(XxtError, match="未返回不完整列表"):
        client.folder_materials("1")
    assert calls == [("0", 1)]


@pytest.mark.parametrize("second", [
    None,  # HTTP failure or unsigned page
    _page("0", 1, 2, [_item(11)]),  # server ignored the page number
    _page("0", 2, 2, [_item(10)]),  # overlapping IDs from a changing listing
    _page("0", 2, 2, []),
    _page("0", 0, 0, []),  # never an empty first page when requested page 2
    _page("999", 2, 2, [_item(11)]),
    {**_page("0", 2, 2, [_item(11)]), "course_id": "999"},
    {**_page("0", 2, 2, [_item(11)]), "size": 30},
    _page("0", 2, 3, [_item(11)]),
])
def test_second_page_failure_is_not_a_partial_success(monkeypatch, client, second):
    calls = _mock_listing(monkeypatch, client, {
        ("0", 1): _page("0", 1, 2, [_item(10)]),
        ("0", 2): second,
    })
    with pytest.raises(XxtError, match="未返回不完整列表"):
        client.folder_materials("1")
    assert calls == [("0", 1), ("0", 2)]
