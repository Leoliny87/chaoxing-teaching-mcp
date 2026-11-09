"""首次登录引导：凭据存系统 keyring，本地表单采集，bsk 半自动登录（滑块人工）。"""
from __future__ import annotations

SERVICE = "xuexitong-mcp"


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


import html
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def validate_submission(fields: dict, token: str, expected_token: str) -> tuple[str, str]:
    if not secrets.compare_digest(str(token), str(expected_token)):
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

        def do_GET(self):
            body = _FORM_HTML.format(token=html.escape(token, quote=True)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            fields = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8")).items()}
            try:
                account, password = validate_submission(fields, fields.get("token", ""), token)
                store.set_password(account, password)
                result["account"] = account
                msg = "已保存凭据，可关闭本页。MCP 将继续自动登录（如弹滑块请本人完成）。"
            except LoginError as e:
                msg = str(e)
            body = f"<!doctype html><meta charset='utf-8'><p>{html.escape(msg)}</p>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
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
    return result["account"]