"""Updater: version order, manifest check, update/rollback on a throwaway git repo."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import updater as U  # noqa: E402


def g(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout.strip()


def manifest(d: Path) -> None:
    files = sorted(f for f in g(d, "ls-files").splitlines() if f != "MANIFEST.sha256")
    (d / "MANIFEST.sha256").write_text("".join(f"{hashlib.sha256((d / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest()}  {f}\n"
                                               for f in files), encoding="utf-8", newline="\n")


def release(d: Path, version: str, body: str, tamper: bool = False) -> None:
    (d / "app.py").write_text(body, encoding="utf-8")
    g(d, "add", "-A")
    manifest(d)
    if tamper:
        (d / "app.py").write_text(body + "# changed after manifest\n", encoding="utf-8")
    g(d, "add", "-A")
    g(d, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", version)
    g(d, "tag", version)


@pytest.fixture()
def repos(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    g(src, "init", "-q")
    (src / "requirements-lock-py314-linux.txt").write_text("mcp==2.3.0\n", encoding="utf-8")
    release(src, "v0.3.0", "print(1)\n")
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(bare)], check=True)
    app = tmp_path / "app"
    subprocess.run(["git", "clone", "-q", str(bare), str(app)], check=True)
    g(app, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", "v0.3.0")
    return src, bare, app


def settings(tmp_path):
    s = U.Settings()
    s.state_file = tmp_path / "state" / "update.json"
    return s


def test_version_order():
    assert U.parse_version("0.3.0") > U.parse_version("0.3.0rc2") > U.parse_version("0.2.9")
    assert U.parse_version("v0.10.0") > U.parse_version("0.9.9") and U.parse_version("0.3.0+local") == U.parse_version("0.3.0")


def test_update_rollback_and_tamper(repos, tmp_path, monkeypatch):
    src, bare, app = repos
    monkeypatch.setattr(U, "self_test", lambda root: None)
    s = settings(tmp_path)
    assert U.update(s, app, current="0.3.0", deps=False, log=lambda m: None)["updated"] is False
    release(src, "v0.3.1", "print(2)\n")
    g(src, "push", "-q", str(bare), "HEAD:refs/heads/master", "--tags")
    assert U.update(s, app, current="0.3.0", check_only=True, deps=False)["available"] == "v0.3.1"
    r = U.update(s, app, current="0.3.0", deps=False, log=lambda m: None)
    assert r["to"] == "v0.3.1" and (app / "app.py").read_text() == "print(2)\n"
    assert U.rollback(s, app, deps=False)["ok"] and (app / "app.py").read_text() == "print(1)\n"
    release(src, "v0.3.2", "print(3)\n", tamper=True)
    g(src, "push", "-q", str(bare), "HEAD:refs/heads/master", "--tags")
    with pytest.raises(U.UpdateError) as e:
        U.update(s, app, current="0.3.0", deps=False, log=lambda m: None)
    assert "已回到原版本" in str(e.value) and (app / "app.py").read_text() == "print(1)\n"


def test_update_refuses_local_changes_and_failed_self_test(repos, tmp_path, monkeypatch):
    src, bare, app = repos
    release(src, "v0.3.1", "print(2)\n")
    g(src, "push", "-q", str(bare), "HEAD:refs/heads/master", "--tags")
    s = settings(tmp_path)
    (app / "app.py").write_text("print('local edit')\n", encoding="utf-8")
    with pytest.raises(U.UpdateError):
        U.update(s, app, current="0.3.0", deps=False)
    g(app, "checkout", "--", ".")

    def boom(root):
        raise U.UpdateError("自检失败")
    monkeypatch.setattr(U, "self_test", boom)
    with pytest.raises(U.UpdateError):
        U.update(s, app, current="0.3.0", deps=False, log=lambda m: None)
    assert (app / "app.py").read_text() == "print(1)\n"


def test_signed_tags_required_without_signers_file(repos, tmp_path):
    src, bare, app = repos
    release(src, "v0.3.1", "print(2)\n")
    g(src, "push", "-q", str(bare), "HEAD:refs/heads/master", "--tags")
    s = settings(tmp_path)
    s.require_signed_tags = True
    with pytest.raises(U.UpdateError):
        U.update(s, app, current="0.3.0", deps=False)
    assert (app / "app.py").read_text() == "print(1)\n"
