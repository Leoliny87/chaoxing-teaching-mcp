import base64
import copy
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.ops_course_patches import patch_card, replace_visible_text
from xuexitong_mcp.ops_exhibit import hall_id, apply_fields, summarise, valid_patch
from xuexitong_mcp.ops_exhibit_form import verified, validate_edits
from xuexitong_mcp.ops_teaching_model import ModelLinks, change_model
from xuexitong_mcp.ops_portal_authoring import public_portal
from xuexitong_mcp.xxt import XxtError


def test_hall_route():
    key = base64.b64encode(b"32").decode()
    assert hall_id("https://vr.chaoxing.com/#/showEditSpace?id=" + key) == "32"
    for route in [
        "https://elsewhere.test/#/showEditSpace?id=" + key,
        "https://vr.chaoxing.com/#/showEditSpace?id=YWJj",
        "https://vr.chaoxing.com/#/newForm?id=" + key,
    ]:
        with pytest.raises(XxtError):
            hall_id(route)


def test_hall_fields_roundtrip_and_preservation():
    rec = {
        "id": 12,
        "propType": 4,
        "hallPropAttr": {
            "content": "title",
            "textCfg": json.dumps(
                {"htmlContent": "title", "unrelated": 42, "ktxFileId": "cached"}
            ),
        },
    }
    fields = {
        "text": "heading",
        "hotspotPos": {"x": 1.0, "y": 2.5, "z": 0},
        "imgFileId": "f" * 32,
        "fontSize": 62,
        "textWidth": 290,
        "textAlign": "center",
    }
    valid_patch("prop", fields)
    apply_fields(rec, "prop", fields)
    out = summarise(rec, "prop")["fields"]
    assert all(out[k] == v for k, v in fields.items())
    cfg = json.loads(rec["hallPropAttr"]["textCfg"])
    assert (
        cfg["htmlContent"] == "heading"
        and cfg["unrelated"] == 42
        and cfg["ktxFileId"] == ""
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"scaleX": 0},
        {"fontSize": True},
        {"text": "<b>hello</b>"},
        {"imgFileId": "https://other.com/1"},
        {"hotspotPos": {"x": 1}},
        {"textAlign": "inherit"},
    ],
)
def test_invalid_prop(patch):
    with pytest.raises(XxtError):
        valid_patch("prop", patch)


def test_form_patch_detects_collateral_changes():
    a = {
        "spaceTemplate": 2,
        "autoSendData": 1,
        "courseVideo": "a",
        "title": "Course",
        "highlights": [
            {"title": str(i), "content": "old", "image": i} for i in range(3)
        ],
    }
    edits = {"highlights": [{"title": str(i), "content": "new"} for i in range(3)]}
    validate_edits(edits)
    b = copy.deepcopy(a)
    b.update(spaceTemplate=3, autoSendData=0, courseVideo="b")
    for item in b["highlights"]:
        item["content"] = "new"
    assert verified(a, b, edits, "3", "courseVideo")
    b["highlights"][0]["image"] = 12
    assert not verified(a, b, edits, "3", "courseVideo")
    with pytest.raises(XxtError):
        validate_edits({"highlights": []})


def test_portal_and_model_boundaries():
    links = ModelLinks()
    links.feed(
        '<a href="https://vrmodel.sslibweb.com/preview/3?mode=1">ok</a><img src="https://vrmodel.sslibweb.com/preview/5"/><a href="https://elsewhere.test/preview/4">wrong</a>'
    )
    assert links.models == {"3"}
    cl = Mock()
    with pytest.raises(XxtError):
        public_portal(cl, Mock(), "https://elsewhere.test")
    cl.b.navigate.assert_not_called()


def make_model():
    return {
        "id": 4,
        "modelFileId": "a" * 32,
        "previewId": "f" * 32,
        "configJSON": json.dumps(
            {
                "modelSettings": {"description": "old"},
                "quizzes": [1],
                "hotSetting": {"hotspots": [{"id": 5, "hidden": 42}]},
            }
        ),
    }


def test_model_file_only_preserves_config_bytes():
    src = make_model()
    assert change_model(src, {"modelFileId": "b" * 32}, []) == dict(
        src, modelFileId="b" * 32
    )


def test_model_preserves_unknown_data_and_checks_anchors():
    src = make_model()
    changed = change_model(src, {"description": "new"}, [{"id": 5, "visible": True}])
    cfg = json.loads(changed["configJSON"])
    assert cfg["hotSetting"]["hotspots"] == [
        {"id": 5, "hidden": 42, "visible": True}
    ] and cfg["quizzes"] == [1]
    with pytest.raises(XxtError):
        change_model(
            src,
            {},
            [{"id": 6, "name": "new", "description": "description", "hotInfo": {}}],
        )
    with pytest.raises(XxtError):
        change_model(src, {}, [{"id": 5, "url": "http://example.org"}])
    with pytest.raises(XxtError):
        change_model(src, {}, [{"id": 5}, {"id": 5}])


def test_chapter_visible_text_does_not_touch_embeds():
    src = '<p>目标</p><iframe title="目标">目标</iframe><script>目标</script>'
    assert replace_visible_text(src, "目标", "A<B") == src.replace(
        "<p>目标</p>", "<p>A&lt;B</p>"
    )
    with pytest.raises(XxtError):
        replace_visible_text(src + "<div>目标</div>", "目标", "改变")
    old = "https://p.cldisk.com/a?t=1&b=2"
    new = "https://p.cldisk.com/b?t=1&b=2"
    source = (
        '<a href="'
        + old.replace("&", "&amp;")
        + '">here</a><script>const s=\'href="'
        + old
        + "\"'</script>"
    )
    changed = patch_card(source, "resource_url", new, old)
    assert changed == source.replace(
        'href="' + old.replace("&", "&amp;") + '"',
        'href="' + new.replace("&", "&amp;") + '"',
    )


def test_management_media_save_uses_native_receipt_and_staged_file(tmp_path):
    import shutil
    import subprocess
    from types import SimpleNamespace
    from xuexitong_mcp.ops_portal_authoring import save_management_image

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the browser-side form fixture")
    c = SimpleNamespace(id="11", cpi="12")
    old = {"logo": "old-logo", "cover": "old-cover"}
    setup = """
      const location={host:'mooc2-ans.chaoxing.com'}, calls=[];
      const attrs={curCourseLogo:'old-cover',curCourseHeaderLogo:'old-logo'};
      const d={querySelector:k=>({getAttribute:()=>attrs[k.slice(1)],value:'1'}),getElementById:k=>({value:'native-field'})};
      const F=async()=>'', D=()=>d, POST=x=>x;
      const document={querySelector:()=>({files:[Object.assign(new Blob(['logo']),{name:'logo.png'})]})};
      const fetch=async(u,p)=>{if(p.body.get('name')!=='logo.png')throw Error('lost file name');
        calls.push('upload');return {ok:true,json:async()=>({status:true,url:'uploaded'})};};
      const J=async(u,p)=>{if(u!='/mooc2-ans/tcm/updatecourseheaderlogo'||p.imageUrl!=='uploaded'||p.courseId!=='11')throw Error('wrong native action');
        calls.push('save');return {status:true,imgUrl:'new-image'};};
    """
    cl = Mock()

    def call(script, retry_safe):
        assert retry_safe is False
        result = subprocess.run(
            [
                node,
                "-e",
                setup
                + ";(async()=>{"
                + script
                + "})().then(x=>console.log(JSON.stringify([x,calls])))",
            ],
            text=True,
            check=True,
            encoding="utf-8",
            capture_output=True,
        )
        receipt, ordered = json.loads(result.stdout)
        assert ordered == ["upload", "save"]
        return receipt

    cl.here.side_effect = call
    f = tmp_path / "logo.png"
    assert save_management_image(cl, c, "logo", f, {"size": 12}, old) == "new-image"
    cl._stage.assert_called_once()
    with pytest.raises(XxtError):
        save_management_image(cl, c, "logo", f, {"size": 5 * 1024**2 + 1}, old)
