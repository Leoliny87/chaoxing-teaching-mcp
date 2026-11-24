import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.ops_panorama_authoring import register_panorama_authoring
from xuexitong_mcp.xxt import XxtError


def verifier():
    api = Mock()
    api.find_panorama.return_value = {
        "panorama_id": "5",
        "type": "image",
        "title": "Example",
    }
    api.here.return_value = {"width": 20, "height": 10, "bytes": 50, "sha256": "a" * 64}
    funcs = {}

    def tool(*args):
        def save(fn):
            funcs[fn.__name__] = fn
            return fn

        return save

    register_panorama_authoring(tool, lambda: api)
    return api, funcs["verify_panorama_image"]


@pytest.mark.parametrize(
    "expected,ok", [("", True), ("A" * 64, True), ("b" * 64, False)]
)
def test_verify_pixel_and_file_receipt(expected, ok):
    api, run = verifier()
    assert run("course", "5", expected)["ok"] is ok
    assert "redirect:'error'" in api.here.call_args.args[0]


@pytest.mark.parametrize("value,sha", [("5/path", ""), ("0", ""), ("5", "abc")])
def test_invalid_inputs_are_never_fetched(value, sha):
    api, run = verifier()
    with pytest.raises(XxtError):
        run("course", value, sha)
    api.here.assert_not_called()


def test_video_or_wrong_resource_is_rejected():
    api, run = verifier()
    api.find_panorama.return_value = {"panorama_id": "5", "type": "video"}
    with pytest.raises(XxtError):
        run("course", "5")
    api.here.assert_not_called()
