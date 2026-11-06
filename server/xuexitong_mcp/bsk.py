"""Thin, defensive wrapper around the `bsk` (BrowserSkill 0.4.x) CLI.

Implements the internal helpers from mcp-tool-proposal.md / bsk-workarounds.md:
  * session lifecycle with auto-restart and state reuse across server restarts
  * cooperate sync -> (context_id, observation_id, observation text) + retry rules
  * zh/en label matching on observation refs (@eN)
  * guarded native clicks, rich-text helpers, readonly date JS
  * adopt_new_tab / recover_tab / recover_session
  * download helper (fetch_export) and verify-after-write hooks (done in client)

Every failed sync or action stops immediately. Successful passive observations
may be compared by readiness.py, but no error triggers a replacement session,
tab, repeated navigation or write. retry_safe is retained as API metadata only.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import Config
from .privacy import redact_text

STATE_FILE = Path("~/.cache/xuexitong-mcp/state.json").expanduser()

# Each local installation must explicitly bind its own browser profile.
# Never fall back to another connected browser when it is missing.
FIXED_BROWSER_INSTANCE = os.environ.get("XUEXITONG_MCP_BROWSER", "").strip()
FIXED_HOMEPAGE = "https://i.mooc.chaoxing.com/space/index"
# Optional visible course anchor for this installation's readiness check.
FIXED_BOOTSTRAP_COURSE = os.environ.get("XUEXITONG_MCP_BOOTSTRAP_COURSE", "").strip() or None

BLANK_URL = "https://mooc2-ans.chaoxing.com/mooc2-ans/js/ServerHost.js"


class BskError(RuntimeError):
    """origin="local": code and message were written by this package (safe to show).
    origin="cli": message/raw came from the bsk process and may echo page data or inputs;
    callers that report to users or logs must use only `code` and privacy.safe_browser_error_details().
    """

    def __init__(self, code: str, message: str, data: Any = None, raw: str = "", *, origin: str = "local"):
        super().__init__(f"{code}: {message}")
        self.code = code or "error"
        self.message = message or ""
        self.data = data if isinstance(data, dict) else {}
        self.raw = raw
        self.origin = origin

    @property
    def not_dispatched(self) -> bool:
        d = self.data or {}
        if d.get("dispatched") is True:
            return False          # bsk says it WAS dispatched: never treat as safe to replay
        if d.get("dispatched") is False or d.get("effect_state") == "none":
            return True
        m = self.message.lower()
        # text fallbacks only for errors raised before dispatch (stale observation/context)
        return "not dispatched" in m or "requires an unused strict observation" in m

    @property
    def transient(self) -> bool:
        m = (self.message + " " + self.raw).lower()
        return any(s in m for s in (
            "still settling", "observation changed", "shared page control", "timed out",
            "unused strict observation", "no observable document", "did not finish cancellation",
            "coverage changed", "wait and synchronize",
        ))


class JsError(RuntimeError):
    pass


_REDACT = [
    # signed / secret URL params
    (re.compile(r"(?i)\b(enc|openc|pEnc|t|token|sign|signature|_t|ticket|key|uuid|fid|cpi|personid|uid|_uid)=([^&\s\"'\\]+)"), r"\1=<redacted>"),
    # JSON fields holding people / ids / links
    (re.compile(r'(?i)(\\?"(?:name|userName|createUserName|createrName|realname|loginName|student_no|person_id|personId|uid|downloadUrl|phone|email|content|text|page_text)\\?"\s*:\s*)(\\?"(?:[^"\\]|\\.)*?\\?")'), r'\1"<redacted>"'),
    (re.compile(r"(?i)(cookie|authorization)\s*[:=]\s*\S+"), r"\1=<redacted>"),
]


def redact(s: str) -> str:
    s = redact_text(s)
    for rx, sub in _REDACT:
        s = rx.sub(sub, s)
    return s


class _RedactLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def _summarize_args(args: list[str]) -> str:
    """Keep command shape only; values, paths and scripts never enter logs.

    Regex redaction cannot recognize arbitrary lesson text, selectors or a CLI
    error echoing an input. The subprocess still receives the original args.
    """
    commands = {"doctor", "browsers", "session", "tab", "cooperate", "navigate", "evaluate",
                "observe", "click", "fill", "select", "press", "upload", "download", "screenshot", "dialog"}
    subcommands = {"session": {"start", "stop", "list"}, "tab": {"create", "select", "close", "list"},
                   "cooperate": {"sync", "status", "wait", "enable"}, "dialog": {"status", "accept", "dismiss"}}
    valued_flags = {"--context", "--observation", "--session", "--tab-id", "--browser", "--url", "--scope",
                    "--wait-until", "--timeout", "--max-tokens", "--save-full", "--baseline", "--value",
                    "--file", "--selector", "--out", "--expect", "--depends-on", "--policy", "--cursor"}
    switches = {"--json", "--full-page", "--overwrite", "--no-focus", "--all", "--settle"}
    out: list[str] = []
    value_pending = False
    options_ended = False
    for index, arg in enumerate(args):
        hidden = f"<arg chars={len(arg)}>"
        if value_pending:
            out.append(hidden)
            value_pending = False
        elif index == 0:
            out.append(arg if arg in commands else "<command>")
        elif index == 1 and arg in subcommands.get(args[0], set()):
            out.append(arg)
        elif options_ended:
            out.append(hidden)
        elif arg == "--":
            options_ended = True
            out.append("--")
        elif arg in valued_flags:
            out.append(arg)
            value_pending = True
        elif arg in switches:
            out.append(arg)
        elif "=" in arg and arg.split("=", 1)[0] in valued_flags:
            flag, value = arg.split("=", 1)
            out.append(f"{flag}=<arg chars={len(value)}>")
        else:
            out.append(hidden)
    return " ".join(out)


def _setup_logger(cfg: Config) -> logging.Logger:
    lg = logging.getLogger("xuexitong_mcp.bsk")
    # Only our own redacting file handler counts: a handler attached by a host
    # or test framework must not stop the file log (and its filter) being set up.
    if any(getattr(h, "_xxt_redacting", False) for h in lg.handlers):
        return lg
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(cfg.log_dir, 0o700)
    except OSError:
        pass
    old_umask = os.umask(0o077)   # bsk.log* created 0600
    try:
        h = logging.handlers.RotatingFileHandler(cfg.log_dir / "bsk.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    finally:
        os.umask(old_umask)
    try:
        os.chmod(cfg.log_dir / "bsk.log", 0o600)
    except OSError:
        pass
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    h.addFilter(_RedactLogFilter())
    h._xxt_redacting = True
    lg.addHandler(h)
    lg.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    lg.propagate = False
    return lg


def _short(s: str, n: int = 300) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


class Bsk:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.log = _setup_logger(cfg)
        self.lock = threading.RLock()
        self.session: str | None = None
        self.tab: int | None = None
        self.obs_text: str = ""
        self.url: str = ""
        self.calls = 0
        self.preserve_tab = False
        self._shutdown_attempted = False

    # ------------------------------------------------------------------ low level
    def run(self, args: list[str], timeout: float | None = None, session: bool = True) -> dict:
        """Run `bsk <args> --json` and return the parsed JSON. Raises BskError."""
        cmd = [self.cfg.bsk()] + args
        if session and self.session and "--session" not in args:
            cmd += ["--session", self.session]
        if "--json" not in cmd:
            cmd.append("--json")
        t0 = time.time()
        self.calls += 1
        try:
            # bsk emits UTF-8 JSON. Without an explicit encoding Windows decodes it
            # with the ANSI code page (e.g. GBK) and Chinese labels/page text break.
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout or self.cfg.t_command)
        except subprocess.TimeoutExpired:
            self.log.warning("bsk TIMEOUT %.1fs %s", time.time() - t0, _short(_summarize_args(cmd[1:])))
            raise BskError("timeout", f"bsk command timed out after {timeout or self.cfg.t_command}s")
        except FileNotFoundError:
            raise BskError("bsk_missing", f"bsk executable not found: {self.cfg.bsk()}")
        dt = time.time() - t0
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        # stdout/stderr can contain arbitrary course data or echoed inputs.
        # Keep lengths only at every log level, including DEBUG. The original
        # parsed response/error remains available to the caller below.
        self.log.info("bsk rc=%s %.2fs %s => out_len=%d err_len=%d", p.returncode, dt,
                      _short(_summarize_args(cmd[1:]), 300), len(out), len(err))
        data: Any = None
        for txt in (out, err):
            if not txt:
                continue
            try:
                data = json.loads(txt)
                break
            except json.JSONDecodeError:
                # some commands print text lines before JSON
                i = txt.find("{")
                if i >= 0:
                    try:
                        data = json.loads(txt[i:])
                        break
                    except json.JSONDecodeError:
                        pass
        if isinstance(data, dict) and data.get("code") and (p.returncode != 0 or "message" in data):
            raise BskError(str(data.get("code")), str(data.get("message", "")), data.get("data"), raw=out + err, origin="cli")
        if p.returncode != 0:
            raise BskError("exit_%d" % p.returncode, _short(err or out, 500), raw=out + err, origin="cli")
        if data is None:
            return {"text": out}
        return data if isinstance(data, dict) else {"value": data}

    # ------------------------------------------------------------------ session
    def _save_state(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({"session": self.session, "tab": self.tab}))
        except OSError:
            pass

    def _live_sessions(self) -> list[str]:
        try:
            d = self.run(["session", "list"], session=False)
        except BskError as e:
            if e.code == "permission_denied":
                raise
            return []
        lst = d.get("value", d) if isinstance(d, dict) else d
        if isinstance(lst, dict):
            lst = lst.get("sessions", [])
        return [s["session_id"] for s in (lst or [])
                if isinstance(s, dict) and isinstance(s.get("session_id"), str) and s["session_id"]
                and s.get("browser_instance_id") == FIXED_BROWSER_INSTANCE]

    def ensure_session(self, *, renew_idle_readonly: bool = False):
        with self.lock:
            if self.session and renew_idle_readonly:
                # Health checks may begin a new read-only session only after
                # the CLI explicitly confirms normal idle expiry. Never turn
                # a permission, transport, or unknown failure into recovery.
                try:
                    self.run(["tab", "list", "--scope", "agent"])
                except BskError as e:
                    if (e.code != "not_found" or e.data.get("reason") != "session_idle_timeout"
                            or (self.preserve_tab and not getattr(self, "_login_handoff", False))):
                        raise
                    self.session = None
                    self.tab = None
                    self.url = ""
                    self.obs_text = ""
                    self.preserve_tab = False
                    self._login_handoff = False
                    self._save_state()
                    self.start_session()
                    return
            if self.session:
                return
            # reuse the session of a previous server run when still alive
            try:
                st = json.loads(STATE_FILE.read_text())
                if st.get("session") in self._live_sessions():
                    self.session, self.tab = st["session"], st.get("tab")
                    # Session/tab identifiers are control handles: never log them.
                    self.log.info("reusing session from previous run")
                    if self.tab:
                        try:
                            self.run(["tab", "select", str(self.tab)])
                        except BskError as e:
                            if e.code == "permission_denied":
                                raise
                            self.tab = None
                    if not self.tab:
                        self._new_tab()
                    return
            except (OSError, ValueError, KeyError):
                pass
            self.start_session()

    def start_session(self):
        if not FIXED_BROWSER_INSTANCE:
            raise BskError("browser_profile_unconfigured", "Set XUEXITONG_MCP_BROWSER to your explicitly selected local BrowserSkill instance; no fallback is allowed.")
        browsers = self.run(["browsers"], session=False)
        instances = browsers.get("value", browsers) if isinstance(browsers, dict) else browsers
        matches = [b for b in instances if isinstance(b, dict) and b.get("instance_id") == FIXED_BROWSER_INSTANCE] if isinstance(instances, list) else []
        if len(matches) != 1 or matches[0].get("unresponsive") is True:
            raise BskError("browser_profile_unavailable", "配置指定的浏览器实例 未连接或不可响应；请重新连接此 Profile。")
        d = self.run(["session", "start", "--browser", FIXED_BROWSER_INSTANCE], session=False)
        if d.get("browser_instance_id") != FIXED_BROWSER_INSTANCE:
            raise BskError("browser_profile_mismatch", "新会话未确认绑定 配置指定的浏览器实例，停止操作。")
        self.session = d["session_id"]
        self.tab = None
        self._initialize_owned_tab()
        self.log.info("started session")

    def _initialize_owned_tab(self):
        """Navigate the one session-created blank tab before attempting a sync.

        Do not create or take control of a page-opened popup.  A refused or
        unexpected initial state ends startup without a fallback or retry.
        """
        d = self.run(["tab", "list", "--scope", "agent"])
        tabs = d.get("tabs") if isinstance(d, dict) else None
        if (not isinstance(tabs, list) or len(tabs) != 1 or not isinstance(tabs[0], dict)
                or tabs[0].get("scope") != "agent" or tabs[0].get("url") != "about:blank"
                or tabs[0].get("tab_id") is None):
            raise BskError("initial_tab_unexpected", "新会话的初始标签不是唯一空白任务标签，已停止。")
        self.tab = int(tabs[0]["tab_id"])
        result = self.run(["navigate", FIXED_HOMEPAGE, "--tab-id", str(self.tab),
                           "--wait-until", "load"], timeout=self.cfg.t_navigate + 10)
        if result.get("tab_id") != self.tab:
            raise BskError("initial_tab_mismatch", "主页导航返回了不同的标签，已停止。")
        if result.get("reached") != "load":
            raise BskError("initial_load_incomplete", "主页未确认完成 load，已停止。")
        self.obs_text = ""
        self.url = result.get("final_url") or result.get("url") or ""
        self._save_state()

        # A completed navigation to the observed Chaoxing login endpoint is
        # an authentication handoff, not slow course-card rendering. Preserve
        # the owned page and stop before any further browser command.
        destination = urlsplit(self.url)
        if (destination.scheme in ("http", "https")
                and destination.hostname == "passport2.chaoxing.com"
                and destination.path.rstrip("/") == "/login"):
            self._login_handoff = not self.preserve_tab
            self.preserve_tab = True
            raise BskError("login_required", "配置指定的 Profile 已跳转到学习通登录页；请本人在此 Profile 手动登录后再继续。")

        # load fires before the portal asynchronously renders its course cards.
        # Observe bounded, successful receipts; never replay a refused action.
        self.wait_readiness(FIXED_BOOTSTRAP_COURSE)

    def wait_readiness(self, course_name: str | None = None):
        from .readiness import wait_observation_ready
        return wait_observation_ready(self, course_name)

    def _new_tab(self, url: str = BLANK_URL) -> int:
        # NOTE: about:blank cannot be synced (no content script: "Receiving end does not
        # exist"), so new tabs open a tiny static Chaoxing file; real pages are then loaded
        # with `navigate` (first load of a tab created with a page URL may render English).
        d = self.run(["tab", "create", "--url", url])
        old = self.tab
        self.tab = int(d["tab_id"])
        for i in range(20):  # the new tab is not observable until its document commits
            try:
                self.run(["tab", "select", str(self.tab)])
                break
            except BskError as e:
                if e.code == "permission_denied" or i == 19 or "observable" not in e.message.lower():
                    raise
                time.sleep(0.5)
        self.obs_text = ""
        self.url = url
        if old and old != self.tab:
            try:
                self.run(["tab", "close", str(old)], timeout=10)
            except BskError:
                pass
        self._save_state()
        return self.tab

    def stop(self):
        """Close only this owned tab once, using current normal control receipts."""
        with self.lock:
            if self._shutdown_attempted or not self.session:
                return
            self._shutdown_attempted = True
            if self.preserve_tab:
                self.log.warning("Leaving owned task tab available: write outcome or editor state needs reconciliation")
                return
            if not isinstance(self.tab, int):
                return
            try:
                tabs = self.run(["tab", "list", "--scope", "agent"]).get("tabs", [])
                if not any(x.get("tab_id") == self.tab and x.get("scope") == "agent" for x in tabs if isinstance(x, dict)):
                    return
                d = self.run(["cooperate", "sync", "--tab-id", str(self.tab)])
                state = d.get("state") or {}
                if (d.get("tab_id") != self.tab or state.get("mode") != "ready" or state.get("editing") or d.get("activity")
                        or not d.get("context_id") or not d.get("observation_id")):
                    return
                closed = self.run(["tab", "close", str(self.tab), "--context", d["context_id"], "--observation", d["observation_id"]])
                if closed.get("tab_id") != self.tab:
                    return
            except BskError as e:
                self.log.warning("Cleanup stopped without retry: %s", e.code)
                return
            self.session = None
            self.tab = None
            self._save_state()

    def recover_tab(self):
        """Abandon a stuck tab (e.g. cdp_failed) and continue in a fresh one."""
        self.log.warning("recover_tab: replacing owned tab")
        try:
            self._new_tab()
        except BskError as e:
            if e.code == "permission_denied":
                raise
            self.recover_session()

    def recover_session(self):
        """Hard recovery (permission_denied 'Receiving end does not exist', stuck session)."""
        self.log.warning("recover_session: restarting session")
        old = self.session
        self.session = None
        if old:
            try:
                self.run(["session", "stop", old], session=False, timeout=20)
            except BskError:
                pass
        self.start_session()

    # ------------------------------------------------------------------ sync
    def sync(self, max_tokens: int | None = None) -> tuple[str, str | None]:
        """cooperate sync -> (context_id, observation_id). Updates self.obs_text."""
        # The extension can return an incremental receipt without observation
        # text, even when no max_tokens was supplied. Never leave a prior page's
        # labels available to a caller after a new (or failed) sync.
        self.obs_text = ""
        self.ensure_session()
        last: Exception | None = None
        for i in range(1):
            try:
                args = ["cooperate", "sync"]
                if isinstance(getattr(self, "tab", None), int):
                    args += ["--tab-id", str(self.tab)]
                if max_tokens:
                    args += ["--max-tokens", str(max_tokens)]
                d = self.run(args)
                ctx = d.get("context_id")
                obs = d.get("observation_id")
                # A command can succeed while shared control is not ready. Do
                # not treat a stale or contradictory receipt as permission.
                state = d.get("state") or {}
                if d.get("ready") is False or state.get("mode") != "ready" or state.get("editing") or d.get("activity"):
                    raise BskError("control_not_ready", "BrowserSkill 报告控制尚未就绪；停止操作。")
                if isinstance(getattr(self, "tab", None), int) and d.get("tab_id") != self.tab:
                    raise BskError("sync_incomplete", "sync returned a different or missing owned tab_id")
                if not isinstance(ctx, str) or not ctx:
                    raise BskError("sync_incomplete", "sync returned no context_id", raw=json.dumps(d)[:300])
                o = d.get("observation") or {}
                if (isinstance(o, dict) and isinstance(o.get("text"), str) and not max_tokens
                        and not o.get("truncated") and not o.get("capture_truncated")
                        and not o.get("next_cursor") and not d.get("next_cursor")):
                    self.obs_text = o["text"]
                if d.get("tab_id"):
                    self.tab = int(d["tab_id"])
                return ctx, obs
            except BskError as e:
                raise
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------------ action runner
    def _act(self, build, *, retry_safe: bool, need_obs: bool, timeout: float | None = None, full_obs: bool = False):
        last: BskError | None = None
        for attempt in range(1):
            # Use the latest receipt. An incremental sync need not include text;
            # sync() clears cached labels in that case instead of guessing.
            try:
                ctx, obs = self.sync(None)
            except BskError as e:
                # Fixed labels only: never retain the URL, page data or script.
                # They distinguish a failed sync from a rejected dispatch without
                # retrying either one after a permission denial.
                e.xxt_stage = "sync"
                raise
            if need_obs and (not isinstance(obs, str) or not obs):
                e = BskError("sync_incomplete", "严格观察操作缺少当前 observation_id；停止操作。")
                e.xxt_stage = "sync"
                raise e
            args = build(ctx, obs)
            try:
                return self.run(args, timeout=timeout)
            except BskError as e:
                last = e
                e.xxt_stage = "dispatch"
                e.xxt_operation = args[0] if args and args[0] in ("navigate", "evaluate", "click", "press", "fill") else "other"
                raise
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------------ high level
    def navigate(self, url: str, wait: str = "load", settle: float | None = None, *, allow_leave: bool = False,
                 readiness: bool = True) -> str:
        """Navigate the agent tab.

        allow_leave=True may ONLY be passed by a write op that has already finished and verified its
        own write (e.g. leaving the topic editor after the topic is in the list). It lets us accept a
        *beforeunload* dialog raised by a page on an allowed Chaoxing host. Any other pending dialog
        (alert/confirm/prompt, or beforeunload when allow_leave=False) is NEVER auto-accepted: a
        confirm() may be the site's own "确定删除/发布?" question.
        """
        def b(ctx, obs):
            return ["navigate", url, "--context", ctx, "--observation", obs, "--wait-until", wait,
                    "--timeout", f"{int(self.cfg.t_navigate)}s"]
        try:
            d = self._act(b, retry_safe=True, need_obs=True, timeout=self.cfg.t_navigate + 10)
        except BskError as e:
            if e.code == "permission_denied":
                raise
            if (e.data or {}).get("reason") != "dialog_pending" and e.code != "dialog_pending":
                raise
            if not self._resolve_leave_dialog(allow_leave):
                raise
            d = self._act(b, retry_safe=True, need_obs=True, timeout=self.cfg.t_navigate + 10)
        self.url = d.get("final_url") or d.get("url") or url
        self.obs_text = ""
        time.sleep(self.cfg.settle if settle is None else settle)
        # readiness=False: the caller only runs same-origin requests from this
        # page's JS context (no observation-based clicks), and very large pages
        # (e.g. the discussion editor) never yield a complete observation.
        if readiness:
            self.wait_readiness()
        return self.url

    _LEAVE_OK_HOSTS = (".chaoxing.com",)

    def _resolve_leave_dialog(self, allow_leave: bool) -> bool:
        """Accept exactly one pending *beforeunload* dialog when allowed; refuse everything else."""
        import urllib.parse as _up
        try:
            d = self.run(["dialog", "status"], timeout=10)
        except BskError as e:
            if e.code == "permission_denied":
                raise
            return False
        dialogs = [x for x in (d.get("dialogs", []) or []) if isinstance(x, dict)]
        if not dialogs:
            return False
        for dl in dialogs:
            typ = str(dl.get("type") or "").lower()
            host = (_up.urlsplit(str(dl.get("url") or "")).hostname or "").lower()
            if typ != "beforeunload" or not allow_leave or not host.endswith(self._LEAVE_OK_HOSTS):
                self.log.warning("refusing to auto-handle dialog type=%s host=%s", typ, host)
                # The dialog text is page content (may name people); keep it out of
                # the error so it cannot reach tool results or logs.
                raise BskError("dialog_needs_human",
                               f"页面上有未处理的 {typ or '未知'} 对话框，为安全起见不会自动点“确定”。"
                               "请在 Chrome 里人工查看并处理后再试。", data={"dialog": {"type": typ, "host": host}})
        for dl in dialogs:
            did = dl.get("dialog_id") or dl.get("id")
            self.run(["dialog", "accept", str(did)], timeout=10)
            self.log.info("accepted beforeunload dialog on allowed host (allow_leave=True)")
        return True

    def eval(self, js: str, *, retry_safe: bool = True, parse: bool = True, timeout: float | None = None) -> Any:
        """Evaluate JS in the page. `js` is the BODY of an async function; use `return`.

        The body is wrapped in an async IIFE (avoids leaking const/let into the page's
        global scope, which would break the next call) and the result JSON-encoded.
        """
        wrapped = "(async()=>{const __r=await (async()=>{%s})();return JSON.stringify(__r===undefined?null:__r);})()" % js

        def b(ctx, obs):
            return ["evaluate", "--context", ctx, "--observation", obs, wrapped]
        d = self._act(b, retry_safe=retry_safe, need_obs=True, timeout=timeout)
        if d.get("ok") is False:
            err = d.get("error") or {}
            raise JsError(str(err.get("text", err))[:500])
        v = d.get("value")
        if parse and isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    def href(self) -> str:
        # A browser error must not silently return a stale URL: callers parse
        # course/class IDs from it. Only a page-script failure keeps the cache.
        try:
            self.url = self.eval("return location.href")
        except JsError:
            pass
        return self.url

    # --- observation / refs --------------------------------------------------
    def observe(self) -> str:
        ctx, _ = self.sync()
        if self.obs_text:
            return self.obs_text
        if not isinstance(self.tab, int):
            raise BskError("observation_unavailable", "同步结果没有正文或可确认的任务标签；停止观察。")
        # A supplementary observation is a read, not a replacement for the
        # sync receipt required by a later strict action. Never put its text in
        # the action cache: callers must separately re-plan any later action.
        d = self.run(["observe", "--tab-id", str(self.tab), "--context", ctx])
        if (d.get("tab_id") != self.tab or d.get("truncated") is not False
                or d.get("capture_truncated") is True or d.get("next_cursor")
                or not isinstance(d.get("text"), str) or not d.get("text")):
            raise BskError("observation_unavailable", "页面观察不完整或目标不匹配；停止观察。")
        return d["text"]

    def find_ref(self, pattern: str, text: str | None = None, nth: int = 0) -> str | None:
        """Return the @eN ref of the nth observation line matching regex `pattern`."""
        t = text if text is not None else self.obs_text
        rx = re.compile(pattern)
        hits = [ln for ln in t.splitlines() if rx.search(ln) and re.search(r"@e\d+", ln)]
        if len(hits) <= nth:
            return None
        return re.search(r"@e\d+", hits[nth]).group(0)  # type: ignore[union-attr]

    def _ref_action(self, verb: str, pattern: str, extra: list[str], *, nth: int = 0, retry_safe: bool, timeout=None):
        last: Exception | None = None
        for attempt in range(1):
            ctx, _ = self.sync()
            if not self.obs_text:
                raise BskError("observation_unavailable", "同步结果没有可用页面正文；停止按旧标签定位控件。")
            ref = self.find_ref(pattern, nth=nth)
            if not ref:
                last = BskError("ref_not_found", f"页面上找不到元素 /{pattern}/")
                time.sleep(1.0 + attempt)
                continue
            try:
                return self.run([verb, ref, "--context", ctx] + extra, timeout=timeout)
            except BskError as e:
                last = e
                raise
        raise last  # type: ignore[misc]

    def click_label(self, pattern: str, *, nth: int = 0, retry_safe: bool = False, settle: float | None = None):
        r = self._ref_action("click", pattern, [], nth=nth, retry_safe=retry_safe)
        time.sleep(self.cfg.settle if settle is None else settle)
        return r

    def fill_label(self, pattern: str, value: str, *, nth: int = 0):
        return self._ref_action("fill", pattern, ["--value", value], nth=nth, retry_safe=True)

    def upload_label(self, pattern: str, files: list[str]):
        extra: list[str] = []
        for f in files:
            extra += ["--file", f]
        return self._ref_action("upload", pattern, extra, retry_safe=False, timeout=self.cfg.t_upload + 10)

    def upload_selector(self, selector: str, file: str):
        """Set one local file on a visible <input type=file> found by CSS selector."""
        def b(ctx, obs):
            return ["upload", "--selector", selector, "--file", file, "--context", ctx]
        return self._act(b, retry_safe=False, need_obs=False, timeout=self.cfg.t_upload + 10)

    def click_selector(self, selector: str, *, retry_safe: bool = False, settle: float | None = None):
        def b(ctx, obs):
            return ["click", "--selector", selector, "--context", ctx]
        r = self._act(b, retry_safe=retry_safe, need_obs=False)
        time.sleep(self.cfg.settle if settle is None else settle)
        return r

    def press(self, key: str, selector: str | None = None):
        def b(ctx, obs):
            a = ["press", key, "--context", ctx, "--observation", obs]
            if selector:
                a += ["--selector", selector]
            return a
        return self._act(b, retry_safe=True, need_obs=True)

    def set_readonly_date(self, selector: str, value: str, callback: str | None = None):
        """My97 WdatePicker inputs are readonly: set value via JS then call the page callback."""
        js = "const e=document.querySelector(%s); if(!e) return false; e.value=%s; e.dispatchEvent(new Event('change',{bubbles:true}));" % (
            json.dumps(selector), json.dumps(value))
        if callback:
            js += "try{%s}catch(x){}" % callback
        js += "return e.value;"
        return self.eval(js)

    def ueditor_set(self, key_or_index: str | int, html: str) -> bool:
        """Set UEditor content (more reliable than fill+End for long text)."""
        js = """
        if(typeof UE==='undefined') return false;
        const ins=Object.values(UE.instants||{}); const k=%s;
        const u= typeof k==='number' ? ins[k] : (ins.find(x=>x.key===k)||null);
        if(!u) return false; u.setContent(%s); try{u.fireEvent('contentChange')}catch(e){}; return true;
        """ % (json.dumps(key_or_index), json.dumps(html))
        return bool(self.eval(js))

    def fill_richtext_end(self, pattern: str, value: str):
        """Fallback recipe for rich text: bsk fill then press End (keeps caret/commit)."""
        self.fill_label(pattern, value)
        self.press("End")

    def adopt_new_tab(self, url: str) -> str:
        """Editors that open in a new tab: navigate our own tab to the target URL instead."""
        return self.navigate(url)

    def screenshot(self, out: str, full_page: bool = False) -> str:
        def b(ctx, obs):
            a = ["screenshot", "--out", out, "--context", ctx, "--observation", obs]
            if full_page:
                a.append("--full-page")
            return a
        self._act(b, retry_safe=True, need_obs=True, timeout=150)
        return out

    def download_selector(self, selector: str, out: str, timeout: float = 120) -> dict:
        def b(ctx, obs):
            return ["download", "--selector", selector, "--out", out, "--overwrite", "--context", ctx,
                    "--timeout", f"{int(timeout)}s"]
        return self._act(b, retry_safe=False, need_obs=False, timeout=timeout + 15)

    def doctor(self) -> list[dict]:
        # `bsk doctor` exits 1 when any check fails but still prints the JSON list
        try:
            d = self.run(["doctor"], session=False, timeout=30)
        except BskError as e:
            if e.code == "permission_denied":
                raise
            txt = e.raw or ""
            i = txt.find("[")
            try:
                d = json.loads(txt[i:txt.rfind("]") + 1]) if i >= 0 else None
            except ValueError:
                d = None
            if d is None:
                raise
        v = d.get("value", d) if isinstance(d, dict) else d
        return v if isinstance(v, list) else [v]
