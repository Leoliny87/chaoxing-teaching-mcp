"""Configuration loading (~/.config/xuexitong-mcp/config.toml)."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

try:  # py3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

DEFAULT_PATH = Path(os.environ.get("XUEXITONG_MCP_CONFIG", "~/.config/xuexitong-mcp/config.toml")).expanduser()


@dataclass
class Config:
    write_allow_courses: list[str] = field(default_factory=list)
    cpi: str = ""
    fid: str = ""
    bsk_path: str = "bsk"
    t_command: float = 45
    t_navigate: float = 40
    t_upload: float = 120
    settle: float = 1.5
    course_list_ttl: float = 600
    course_ctx_ttl: float = 1800
    log_dir: Path = Path("~/.local/state/xuexitong-mcp").expanduser()
    log_level: str = "INFO"
    download_dir: Path = Path("~/Downloads/xuexitong-mcp").expanduser()
    # upload_material may only read files below these dirs (a prompt-injected agent must not upload ~/.ssh etc.)
    upload_allow_dirs: list[str] = field(default_factory=list)
    # policy layer (see policy.py): teacher | reviewer | student
    profile: str = "teacher"
    extra_tools: list[str] = field(default_factory=list)
    deny_tools: list[str] = field(default_factory=list)
    daily_call_budget: int | None = None      # None = the profile default
    min_nav_interval: float | None = None     # seconds between page navigations; None = profile default
    spot_check_rate: float = 0.2
    tutor_url: str = ""
    tutor_token: str = ""
    tutor_timeout: float = 60
    path: Path | None = None

    def bsk(self) -> str:
        p = os.path.expanduser(self.bsk_path)
        return shutil.which(p) or p


def load(path: str | os.PathLike | None = None) -> Config:
    p = Path(path).expanduser() if path else DEFAULT_PATH
    cfg = Config()
    if p.exists():
        with open(p, "rb") as f:
            d = tomllib.load(f)
        cfg.path = p
        allow = d.get("write_allow_courses", [])
        if not isinstance(allow, list) or any(not isinstance(x, str) or not x.strip() for x in allow):
            raise ValueError("write_allow_courses 必须是非空字符串组成的数组；空数组表示禁止所有写入。")
        cfg.write_allow_courses = allow
        cfg.cpi = str(d.get("cpi", "") or "")
        cfg.fid = str(d.get("fid", "") or "")
        cfg.bsk_path = str(d.get("bsk_path", "bsk") or "bsk")
        t = d.get("timeouts", {}) or {}
        cfg.t_command = float(t.get("command", cfg.t_command))
        cfg.t_navigate = float(t.get("navigate", cfg.t_navigate))
        cfg.t_upload = float(t.get("upload", cfg.t_upload))
        cfg.settle = float(t.get("settle", cfg.settle))
        c = d.get("cache", {}) or {}
        cfg.course_list_ttl = float(c.get("course_list_ttl", cfg.course_list_ttl))
        cfg.course_ctx_ttl = float(c.get("course_ctx_ttl", cfg.course_ctx_ttl))
        lg = d.get("log", {}) or {}
        cfg.log_dir = Path(lg.get("dir", str(cfg.log_dir))).expanduser()
        cfg.log_level = str(lg.get("level", cfg.log_level))
        dl = d.get("downloads", {}) or {}
        cfg.download_dir = Path(dl.get("dir", str(cfg.download_dir))).expanduser()
        if "upload_allow_dirs" in d:
            cfg.upload_allow_dirs = [str(x) for x in d.get("upload_allow_dirs") or []]
        prof = str(d.get("profile", "teacher") or "teacher")
        if prof not in ("teacher", "reviewer", "student"):
            raise ValueError("profile 只能是 teacher、reviewer 或 student。")
        cfg.profile = prof
        pol = d.get("policy", {}) or {}
        cfg.extra_tools = [str(x) for x in pol.get("extra_tools") or []]
        cfg.deny_tools = [str(x) for x in pol.get("deny_tools") or []]
        if "daily_call_budget" in pol:
            cfg.daily_call_budget = int(pol["daily_call_budget"])
        if "min_nav_interval" in pol:
            cfg.min_nav_interval = float(pol["min_nav_interval"])
        cfg.spot_check_rate = float(pol.get("spot_check_rate", cfg.spot_check_rate))
        tu = d.get("tutor", {}) or {}
        cfg.tutor_url = str(tu.get("url", "") or "")
        cfg.tutor_token = str(tu.get("token", "") or "")
        cfg.tutor_timeout = float(tu.get("timeout", cfg.tutor_timeout))
    # The environment can narrow the explicitly configured allowlist, never
    # create or broaden authority.  An explicitly empty variable denies all.
    if "XUEXITONG_MCP_WRITE_ALLOW" in os.environ:
        requested = {x.strip() for x in os.environ["XUEXITONG_MCP_WRITE_ALLOW"].split(",") if x.strip()}
        cfg.write_allow_courses = [x for x in cfg.write_allow_courses if x in requested]
    if os.environ.get("XUEXITONG_MCP_BSK"):
        cfg.bsk_path = os.environ["XUEXITONG_MCP_BSK"]
    return cfg
