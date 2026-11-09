"""首次登录引导：凭据存系统 keyring，本地表单采集，bsk 半自动登录（滑块人工）。"""
from __future__ import annotations

import html
import json
import re
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVICE = "xuexitong-mcp"
LOGIN_URL = "https://passport2.chaoxing.com/login"
HOME_HOST = "i.mooc.chaoxing.com"
_MAX_BODY = 64 * 1024


class LoginError(RuntimeError):
    pass


def _default_backend():
    try:
        import keyring  # type: ignore
        return keyring
    except ImportError as e:
        raise LoginError("未安装 keyring 依赖；请安装后重试，或手动在浏览器登录学习通。") from e


class CredentialStore:
    def __init__(self, backend=None):
        self._kr = backend if backend is not None else _default_backend()

    def get_password(self, account: str) -> str | None:
        try:
            return self._kr.get_password(SERVICE, account)
        except Exception as e:
            raise LoginError(f"系统凭据库不可用（{type(e).__name__}）；请手动在浏览器登录学习通。") from e

    def set_password(self, account: str, password: str) -> None:
        try:
            self._kr.set_password(SERVICE, account, password)
        except Exception as e:
            raise LoginError(f"无法写入系统凭据库（{type(e).__name__}）；请手动在浏览器登录学习通。") from e

    def delete_password(self, account: str) -> None:
        try:
            self._kr.delete_password(SERVICE, account)
        except Exception as e:
            raise LoginError(f"无法删除系统凭据（{type(e).__name__}）。") from e


def validate_submission(fields: dict, token: str, expected_token: str) -> tuple[str, str]:
    if not secrets.compare_digest(str(token).encode("utf-8"), str(expected_token).encode("utf-8")):
        raise LoginError("表单令牌无效或已过期；请重新打开登录表单。")
    account = str(fields.get("account", "")).strip()
    password = str(fields.get("password", ""))
    if not account or not password:
        raise LoginError("账号和密码都不能为空。")
    return account, password


_FORM_HTML = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>学习通 MCP 登录</title>
<body style="font-family:sans-serif;max-width:420px;margin:60px auto">
<h2>学习通 MCP 首次登录</h2>
<p>账号密码仅存于本机系统凭据库（keyring），用于自动登录学习通；滑块验证仍需本人完成。密码不会写入配置文件或日志。</p>
<form method="post" action="/submit">
<input type="hidden" name="token" value="{token}">
<p><input name="account" placeholder="手机号/超星号" style="width:100%;padding:8px" autofocus></p>
<p><input name="password" type="password" placeholder="学习通密码" style="width:100%;padding:8px"></p>
<p><button type="submit" style="padding:8px 24px">保存并登录</button></p>
</form></body></html>"""


def collect_credentials(store, open_browser: bool = True, timeout: float = 300) -> str:
    token = secrets.token_urlsafe(24)
    done = threading.Event()
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence; never log credentials
            pass

        def _localhost_only(self) -> bool:
            # Mitigate DNS-rebinding: only serve requests whose Host is this loopback server.
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            if host not in ("127.0.0.1", "localhost"):
                self.send_response(403)
                self.end_headers()
                return False
            return True

        def _html(self, body: str, status: int = 200):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._localhost_only():
                return
            self._html(_FORM_HTML.format(token=html.escape(token, quote=True)))

        def do_POST(self):
            if not self._localhost_only():
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length < 0 or length > _MAX_BODY:
                    raise ValueError("bad length")
                raw = self.rfile.read(length).decode("utf-8")
                fields = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
                account, password = validate_submission(fields, fields.get("token", ""), token)
                store.set_password(account, password)
                result["account"] = account
                msg = "已保存凭据，可关闭本页。MCP 将继续自动登录（如弹滑块请本人完成）。"
            except LoginError as e:
                msg = str(e)
            except Exception:
                msg = "请求无效；请重新打开登录表单提交。"
            self._html(f"<!doctype html><meta charset='utf-8'><p>{html.escape(msg)}</p>")
            if "account" in result:
                done.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        webbrowser.open(url)
    try:
        if not done.wait(timeout):
            raise LoginError("登录表单超时未提交；请重新运行 login。")
    finally:
        server.shutdown()
        server.server_close()
    if "account" not in result:
        raise LoginError("登录表单未收到有效提交；请重新运行 login。")
    return result["account"]


class LoginAutomator:
    """Fill the passport2 login form and submit; the slider (if any) is solved by the human."""

    def __init__(self, bsk):
        self.b = bsk

    def fill_and_submit(self, account: str, password: str, retries: int = 5) -> None:
        # The passport2 login page breaks the cooperate sync while it re-renders.
        # Navigate once with the raw bsk command (no cooperate context), let the
        # page fully settle, then retry only the evals — re-navigating per attempt
        # would reload the page and keep invalidating the cooperate context.
        from .bsk import BskError
        self.b.run(["navigate", LOGIN_URL, "--tab-id", str(self.b.tab), "--wait-until", "domcontentloaded"],
                   timeout=self.b.cfg.t_navigate + 10)
        time.sleep(3.5)
        fill_js = (
            "const p=document.getElementById('phone'); const w=document.getElementById('pwd');"
            f"p.value={json.dumps(account)}; w.value={json.dumps(password)};"
            "['input','change','keyup'].forEach(n=>{p.dispatchEvent(new Event(n,{bubbles:true}));w.dispatchEvent(new Event(n,{bubbles:true}));});"
            "return true;")
        last = None
        for _ in range(retries):
            try:
                self.b.eval(fill_js)
                self.b.eval("document.getElementById('loginBtn').click(); return true;")
                return
            except BskError as e:
                last = e
                time.sleep(2.0)
        raise last

    def wait_until_logged_in(self, timeout: float = 180, poll: float = 2) -> dict:
        deadline = time.time() + timeout
        url = ""
        while time.time() < deadline:
            url = self.b.eval("return location.href") or ""
            if HOME_HOST in url:
                return {"ok": True, "url": url, "needs_slider": False}
            time.sleep(poll)
        return {"ok": False, "url": url, "needs_slider": "passport2" in url}


def _remember_account(cfg, account: str) -> None:
    """Persist the account username (not the password) so the next login reuses it."""
    cfg.login_account = account
    p = getattr(cfg, "path", None)
    if not p:
        return
    safe = account.replace("\\", "\\\\").replace('"', '\\"')
    line = f'login_account = "{safe}"'
    try:
        text = Path(p).read_text(encoding="utf-8")
        if re.search(r"(?m)^login_account\s*=", text):
            text = re.sub(r"(?m)^login_account\s*=.*$", line, text)
        elif "[login]" in text:
            text = text.replace("[login]", "[login]\n" + line, 1)
        else:
            text = text.rstrip() + "\n\n[login]\n" + line + "\n"
        Path(p).write_text(text, encoding="utf-8")
    except OSError:
        pass


def run_login(cfg, bsk, store=None, open_browser: bool = True) -> dict:
    store = store if store is not None else CredentialStore()
    account = cfg.login_account
    password = store.get_password(account) if account else None
    if not account or not password:
        account = collect_credentials(store, open_browser=open_browser)
        password = store.get_password(account)
        if not password:
            raise LoginError("采集后仍读不到凭据；请重试 login。")
        _remember_account(cfg, account)
    automator = LoginAutomator(bsk)
    automator.fill_and_submit(account, password)
    result = automator.wait_until_logged_in()
    return {"ok": result["ok"], "account": account, "url": result["url"],
            "needs_slider": result["needs_slider"],
            "stage": "logged_in" if result["ok"] else "awaiting_slider_or_failed"}


def run_logout(cfg, store=None) -> dict:
    store = store if store is not None else CredentialStore()
    account = cfg.login_account
    if account:
        store.delete_password(account)
    return {"ok": True, "account": account, "note": "已删除本机保存的学习通凭据。"}