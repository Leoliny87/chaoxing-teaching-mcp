import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import ops_model_library as lib
from xuexitong_mcp.xxt import XxtError


C = SimpleNamespace(id="1", cpi="2", clazz_id="3", name="Course")
ITEM = {"id": "4", "name": "Example"}


def glb(path):
    payload = b'{"asset":{"version":"2.0"}} '
    path.write_bytes(
        struct.pack("<4sIIII", b"glTF", 2, 20 + len(payload), len(payload), 0x4E4F534A)
        + payload
    )


def test_glb_format_checked_before_upload(tmp_path):
    p = tmp_path / "file.glb"
    glb(p)
    lib.glb_file(p)
    p.write_bytes(p.read_bytes()[:-1])
    with pytest.raises(XxtError):
        lib.glb_file(p)


@pytest.mark.parametrize(
    "target",
    [
        "https://example.org/out-api/redirect",
        "https://vr.chaoxing.com/else",
        "https://vr.chaoxing.com@example.org/out-api/redirect",
    ],
)
def test_no_navigation_to_untrusted_resource_picker(target):
    api = Mock()
    api.chapters.return_value = [{"chapter_id": "9"}]
    api.wait_for.side_effect = [True, target]
    with pytest.raises(XxtError):
        lib.ModelLibrary(api, C, "9").open()
    assert api.b.navigate.call_count == 1


def test_reject_other_courses_chapter():
    api = Mock()
    api.chapters.return_value = [{"chapter_id": "9"}]
    with pytest.raises(XxtError):
        lib.ModelLibrary(api, C, "10").open()
    api.b.navigate.assert_not_called()


def test_preview_checks_rendered_native_viewer():
    api = Mock()
    lib.ModelLibrary(api, C, "9").preview(ITEM)
    api.b.navigate.assert_called_once_with("https://vrmodel.sslibweb.com/preview/4")
    assert (
        "canvas" in api.wait_for.call_args.args[0]
        and "config/get" in api.wait_for.call_args.args[0]
    )
    api.wait_for.return_value = False
    with pytest.raises(XxtError):
        lib.ModelLibrary(api, C, "9").preview(ITEM)


def test_each_next_page_must_advance():
    api = Mock()
    d = {"current": 1, "items": [], "more": True}
    api.here.side_effect = [d, True, d]
    with pytest.raises(XxtError):
        lib.ModelLibrary(api, C, "9").page(2)


@pytest.fixture
def env(monkeypatch, tmp_path):
    api = Mock()
    api.ctx.return_value = C
    studio = Mock(api=api, c=C)
    monkeypatch.setattr(lib, "ModelLibrary", lambda *args: studio)
    funcs = {}

    def tool(*args):
        def reg(fn):
            funcs[fn.__name__] = fn
            return fn

        return reg

    p = tmp_path / "model.glb"
    glb(p)
    check = Mock(return_value=C)
    lib.register_model_library(
        tool,
        lambda: api,
        check,
        lambda c, a, **k: k,
        lambda x: p,
        lambda x: {"sha256": "a" * 64},
    )
    return SimpleNamespace(f=funcs, s=studio, api=api, p=p, check=check)


def test_binding_no_upload_on_preview(env):
    env.s.page.return_value = None
    p = env.f["upload_teaching_model"]("1", "9", "Example", str(env.p))
    assert p["bind"] == {"file_path": str(env.p), "file_sha256": "a" * 64}
    env.api._snapshot.assert_not_called()
    env.s.upload.assert_not_called()


def test_existing_own_model_is_not_overwritten(env):
    env.s.page.return_value = ITEM
    with pytest.raises(XxtError):
        env.f["upload_teaching_model"]("1", "9", "Example", str(env.p), True, "a" * 64)
    env.api._snapshot.assert_not_called()


def test_staged_upload_confirmation_and_readback(env, tmp_path):
    d = tmp_path / "snapshot"
    d.mkdir()
    p = d / "model.glb"
    glb(p)
    env.api._snapshot.return_value = (d, p, {})
    env.s.page.side_effect = [None, ITEM]
    env.s.preview.return_value = {
        "model_id": "4",
        "name": "Example",
        "preview_url": "https://vrmodel.sslibweb.com/preview/4",
    }
    r = env.f["upload_teaching_model"]("1", "9", "Example", str(env.p), True, "a" * 64)
    assert r["ok"] and r["model_id"] == "4"
    env.s.upload.assert_called_once_with(p, "Example")
    assert not d.exists() and env.p.exists()


def test_get_preview_checks_membership_before_viewer(env):
    env.s.page.return_value = None
    with pytest.raises(XxtError):
        env.f["get_teaching_model_preview"]("1", "9", "77")
    env.s.preview.assert_not_called()


def test_platform_failure_against_new_file_is_uncertain(env, tmp_path):
    d = tmp_path / "snapshot"
    d.mkdir()
    p = d / "model.glb"
    glb(p)
    env.api._snapshot.return_value = (d, p, {})
    env.s.page.return_value = None
    env.s.upload.side_effect = XxtError("Uncertain remote outcome")
    with pytest.raises(XxtError):
        env.f["upload_teaching_model"]("1", "9", "Example", str(env.p), True, "a" * 64)
    env.s.upload.assert_called_once()
    assert not d.exists()
