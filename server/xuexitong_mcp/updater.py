"""One-command update and rollback for a git-checkout install.

An install is a clone of the teacher's repository; releases are tags vX.Y.Z (the
"rc" channel also accepts vX.Y.ZrcN).  `update` will:

1. refuse if tracked files were modified locally (config lives outside the repo);
2. fetch tags from the configured remote and pick the newest release above the
   running version (or the one given with --to);
3. if [update] require_signed_tags is on, run `git verify-tag` against the
   configured allowed-signers file (SSH signatures);
4. remember the current commit, check out the tag (detached);
5. verify every tracked file against MANIFEST.sha256 (LF-normalized, so Windows
   checkouts with CRLF still match) and that no tracked file is missing from it;
6. reinstall dependencies only when the lock file changed;
7. self-test (`--list-tools` in a fresh interpreter);
any failure in 4-7 checks the previous commit out again.  `rollback` returns to
the commit remembered by the last update.  Nothing here reads or sends
credentials; config.toml and browser profiles are outside the checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parents[2]
LOCK = "requirements-lock-py314-linux.txt"
_TAG = {"stable": re.compile(r"^v(\d+)\.(\d+)\.(\d+)$"), "rc": re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?$")}


class UpdateError(RuntimeError):
    pass


def parse_version(v: str) -> tuple:
    """'0.3.0' > '0.3.0rc2' > '0.2.9'; local suffixes (+...) are ignored."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?", v or "")
    if not m:
        return (0, 0, 0, -1)
    a, b, c, rc = m.groups()
    return (int(a), int(b), int(c), int(rc) if rc is not None else 10 ** 6)


@dataclass
class Settings:
    remote: str = "origin"
    channel: str = "stable"
    require_signed_tags: bool = False
    allowed_signers: str = ""
    state_file: Path = Path("~/.local/state/xuexitong-mcp/update.json").expanduser()
    lock_file: str = LOCK


def settings_from(cfg) -> Settings:
    s = Settings()
    u = getattr(cfg, "update", None) or {}
    s.remote = str(u.get("remote", s.remote))
    s.channel = str(u.get("channel", s.channel))
    if s.channel not in _TAG:
        raise UpdateError("[update] channel 只能是 stable 或 rc。")
    s.require_signed_tags = bool(u.get("require_signed_tags", False))
    s.allowed_signers = str(Path(str(u.get("allowed_signers", ""))).expanduser()) if u.get("allowed_signers") else ""
    s.state_file = Path(getattr(cfg, "log_dir", s.state_file.parent)) / "update.json"
    return s


def git(root: Path, *args: str, timeout: float = 120, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if check and p.returncode != 0:
        raise UpdateError(f"git {args[0]} 失败：{(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout.strip()


def check_manifest(root: Path) -> list[str]:
    """Return problems (empty list = ok).  Hashes are over LF-normalized bytes."""
    mf = root / "MANIFEST.sha256"
    if not mf.exists():
        return ["缺少 MANIFEST.sha256"]
    listed = {}
    for line in mf.read_text(encoding="utf-8").splitlines():
        if line.strip():
            h, _, name = line.partition("  ")
            listed[name.strip()] = h.strip()
    problems = []
    for name, h in listed.items():
        f = root / name
        if not f.is_file():
            problems.append(f"缺少文件 {name}")
        elif hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != h:
            problems.append(f"内容不符 {name}")
    tracked = set(git(root, "ls-files").splitlines()) - {"MANIFEST.sha256"}
    for name in sorted(tracked - set(listed)):
        problems.append(f"清单外的文件 {name}")
    return problems


def _file_hash(root: Path, name: str) -> str:
    f = root / name
    return hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if f.exists() else ""


def available(root: Path, s: Settings, fetch: bool = True) -> list[str]:
    if fetch:
        git(root, "fetch", "--tags", "--force", "--prune", s.remote, timeout=180)
    tags = [t for t in git(root, "tag", "--list").splitlines() if _TAG[s.channel].match(t)]
    return sorted(tags, key=parse_version)


def self_test(root: Path) -> None:
    p = subprocess.run([sys.executable, "-I", str(root / "scripts" / "launch_stdio.py"), "--list-tools"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120, env={**os.environ, "BSK_AUTO_START": "0"})
    if p.returncode != 0 or not p.stdout.strip():
        raise UpdateError("新版本自检失败（--list-tools 没有正常列出工具）。")


def install_deps(root: Path, lock: str) -> None:
    p = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(root / lock)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        raise UpdateError(f"依赖安装失败：{(p.stderr or p.stdout).strip()[-300:]}")


def update(s: Settings, root: Path = ROOT, to: str = "", check_only: bool = False, deps: bool = True,
           current: str = __version__, log=print) -> dict:
    if not (root / ".git").exists():
        raise UpdateError(f"{root} 不是 git 安装目录；请用 scripts/install 安装后再更新。")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise UpdateError("安装目录里有被改动的文件；为避免覆盖，没有更新。请先恢复（git checkout -- .）或联系教师。")
    tags = available(root, s)
    if to:
        if to not in tags:
            raise UpdateError(f"远端没有版本 {to}（{s.channel} 通道）。")
        target = to
    else:
        newer = [t for t in tags if parse_version(t) > parse_version(current)]
        if not newer:
            return {"ok": True, "updated": False, "current": current, "latest": tags[-1] if tags else None, "message": "已是最新版本。"}
        target = newer[-1]
    if check_only:
        return {"ok": True, "updated": False, "current": current, "available": target, "message": f"可以更新到 {target}。"}
    if s.require_signed_tags:
        if not s.allowed_signers or not Path(s.allowed_signers).is_file():
            raise UpdateError("已要求签名校验，但 [update] allowed_signers 文件不存在。")
        p = subprocess.run(["git", "-C", str(root), "-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={s.allowed_signers}",
                            "verify-tag", target], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if p.returncode != 0:
            raise UpdateError(f"版本 {target} 的签名校验失败；没有更新。")
    prev = git(root, "rev-parse", "HEAD")
    lock_before = _file_hash(root, s.lock_file)
    s.state_file.parent.mkdir(parents=True, exist_ok=True)
    s.state_file.write_text(json.dumps({"previous": prev, "previous_version": current, "target": target}), encoding="utf-8")
    log(f"正在切换到 {target} …")
    git(root, "checkout", "--quiet", "--detach", target)
    try:
        problems = check_manifest(root)
        if problems:
            raise UpdateError("文件校验不通过：" + "；".join(problems[:5]))
        lock_changed = _file_hash(root, s.lock_file) != lock_before
        if deps and lock_changed:
            log("依赖有变化，正在安装 …")
            install_deps(root, s.lock_file)
        self_test(root)
    except Exception as e:
        log(f"更新失败，正在回到原版本：{e}")
        git(root, "checkout", "--quiet", "--detach", prev)
        if deps and _file_hash(root, s.lock_file) != lock_before:
            install_deps(root, s.lock_file)
        raise UpdateError(f"更新到 {target} 失败，已回到原版本：{e}") from None
    return {"ok": True, "updated": True, "from": current, "to": target, "deps_reinstalled": bool(deps and lock_changed),
            "message": "更新完成；重启 MCP 客户端（或本服务）后生效。"}


def rollback(s: Settings, root: Path = ROOT, deps: bool = True) -> dict:
    try:
        st = json.loads(s.state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise UpdateError("没有可回退的记录。") from None
    prev = str(st.get("previous") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", prev):
        raise UpdateError("回退记录损坏。")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise UpdateError("安装目录里有被改动的文件；没有回退。")
    lock_before = _file_hash(root, s.lock_file)
    git(root, "checkout", "--quiet", "--detach", prev)
    if deps and _file_hash(root, s.lock_file) != lock_before:
        install_deps(root, s.lock_file)
    return {"ok": True, "rolled_back_to": st.get("previous_version") or prev[:12], "message": "已回到上一个版本；重启后生效。"}


def schedule_command(root: Path = ROOT, hour: int = 3, minute: int = 17) -> dict:
    """The command a deployer can register for a daily automatic update (printed, not installed)."""
    py, launch = sys.executable, root / "scripts" / "launch_stdio.py"
    if os.name == "nt":
        tr = f'\\"{py}\\" -I \\"{launch}\\" update'
        cmd = f'schtasks /Create /F /SC DAILY /ST {hour:02d}:{minute:02d} /TN xuexitong-mcp-update /TR "{tr}"'
        return {"platform": "windows", "command": cmd}
    log = Path("~/.local/state/xuexitong-mcp/update.log").expanduser()
    return {"platform": "posix", "crontab_line": f"{minute} {hour} * * * {py} -I {launch} update >> {log} 2>&1"}
