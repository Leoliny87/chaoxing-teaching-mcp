# 首次登录引导 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让首次使用者在本地表单输入一次学习通账号密码（存系统 keyring），MCP 自动填表登录、人工划滑块后到达各自首页，之后凭据持久复用。

**Architecture:** 新增 `login.py`，含 CredentialStore（keyring 封装）、IntakeFormServer（localhost 表单）、LoginAutomator（bsk 填表+轮询首页）与编排函数；config 增 `[login]`；policy 让 login/logout 跨 profile 可用；server 注册 login/logout 工具；CLI 增 login/logout 命令。

**Tech Stack:** Python 3.10+，keyring（OS 凭据库），http.server（localhost 表单），现有 bsk（BrowserSkill）驱动 Chrome，pytest。

**Spec:** `docs/superpowers/specs/2026-11-09-login-onboarding-design.md`

## Global Constraints

- 密码绝不进 config 文件、日志、异常文本、MCP 工具结果、MANIFEST、进程持久参数；只存 OS keyring。
- 表单服务仅绑 `127.0.0.1`，随机端口，一次性 CSRF token，提交后或超时即停。
- 不 bypass 滑块/短信/协议（人工完成）；登录失败不自动重试提交。
- `auto_login` 默认 `true`；环境变量 `XUEXITONG_MCP_AUTO_LOGIN=0` 可收窄关闭。
- 登录主页 `https://i.mooc.chaoxing.com/space/index`；登录页 `https://passport2.chaoxing.com/login`，账号框 `#phone`、密码框 `#pwd`、按钮 `#loginBtn`（已实测）。
- keyring 不可用时明确报错并回退引导手动登录，不静默存明文。
- 遵循现有 TDD：先写失败测试→运行确认失败→最小实现→运行确认通过→提交。测试用合成数据，mock keyring/bsk，不碰真实账号。
- 运行测试命令统一：`C:/Users/11079/.cache/xuexitong-mcp/venv/Scripts/python.exe -m pytest tests/<file> -v`（仓库根目录运行）。

## File Structure

- Create `server/xuexitong_mcp/login.py` — CredentialStore / validate_submission / IntakeFormServer / LoginAutomator / run_login / LoginError。
- Modify `server/xuexitong_mcp/config.py` — Config 增 `auto_login: bool=True`、`login_account: str=""`；load() 解析 `[login]` + 环境变量收窄。
- Modify `server/xuexitong_mcp/policy.py` — `LOGIN_TOOLS=frozenset({"login","logout"})`，allowed_tools 各 profile 都并入。
- Modify `server/xuexitong_mcp/server.py` — 注册 `login`/`logout` 工具（L 类）；login_required 引导。
- Modify `server/xuexitong_mcp/__main__.py` — CLI 增 `login`/`logout` 命令。
- Modify `config/config.example.toml` — 增 `[login]` 段与说明。
- Modify `requirements-lock-py314-linux.txt`、`server/pyproject.toml`、`scripts/install.*` — keyring 依赖。
- Modify `README.md` — 登录引导说明与安全告知。
- Create tests：`tests/test_login_config.py`、`tests/test_credential_store.py`、`tests/test_intake_form.py`、`tests/test_login_automator.py`、`tests/test_login_policy.py`。

---

### Task 1: Config 增 auto_login / login_account

**Files:**
- Modify: `server/xuexitong_mcp/config.py:18-45`（Config 字段）、`config.py:97` 后（load 解析）
- Test: `tests/test_login_config.py`

**Interfaces:**
- Produces: `Config.auto_login: bool`（默认 True）、`Config.login_account: str`（默认 ""）；`load()` 读 `[login]` 表与 `XUEXITONG_MCP_AUTO_LOGIN` 环境变量。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_login_config.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.config import Config, load

def test_defaults_auto_login_on():
    c = Config()
    assert c.auto_login is True
    assert c.login_account == ""

def test_load_login_section(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[login]\nauto_login = false\nlogin_account = "13800000000"\n', encoding="utf-8")
    c = load(p)
    assert c.auto_login is False
    assert c.login_account == "13800000000"

def test_env_narrows_auto_login_off(tmp_path, monkeypatch):
    p = tmp_path / "config.toml"
    p.write_text('[login]\nauto_login = true\n', encoding="utf-8")
    monkeypatch.setenv("XUEXITONG_MCP_AUTO_LOGIN", "0")
    assert load(p).auto_login is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_login_config.py -v`
Expected: FAIL（Config 无 auto_login 属性 / load 不解析 [login]）

- [ ] **Step 3: Write minimal implementation**

In `config.py` Config dataclass, after `update: dict = ...` line add:
```python
    auto_login: bool = True
    login_account: str = ""
```
In `load()`, after `cfg.update = dict(d.get("update", {}) or {})` add:
```python
        li = d.get("login", {}) or {}
        cfg.auto_login = bool(li.get("auto_login", True))
        cfg.login_account = str(li.get("login_account", "") or "")
```
Before `return cfg`, after the XUEXITONG_MCP_BSK block add:
```python
    if os.environ.get("XUEXITONG_MCP_AUTO_LOGIN") == "0":
        cfg.auto_login = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_login_config.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/config.py tests/test_login_config.py
git commit -m "feat(login): config auto_login (default on) and login_account"
```

---

### Task 2: CredentialStore（keyring 封装）

**Files:**
- Create: `server/xuexitong_mcp/login.py`
- Test: `tests/test_credential_store.py`

**Interfaces:**
- Produces: `login.LoginError(RuntimeError)`；`login.CredentialStore(backend=None)` with `get_password(account:str)->str|None`、`set_password(account:str,password:str)->None`、`delete_password(account:str)->None`；`login.SERVICE="xuexitong-mcp"`。backend 为可注入对象，需有 `get_password(service,account)`/`set_password(service,account,password)`/`delete_password(service,account)`（与 keyring 模块同签名）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_credential_store.py
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import CredentialStore, LoginError, SERVICE

class FakeKeyring:
    def __init__(self): self.store = {}
    def get_password(self, service, account): return self.store.get((service, account))
    def set_password(self, service, account, password): self.store[(service, account)] = password
    def delete_password(self, service, account): self.store.pop((service, account), None)

def test_set_get_delete():
    kr = FakeKeyring()
    cs = CredentialStore(backend=kr)
    assert cs.get_password("13800000000") is None
    cs.set_password("13800000000", "secret")
    assert kr.store[(SERVICE, "13800000000")] == "secret"
    assert cs.get_password("13800000000") == "secret"
    cs.delete_password("13800000000")
    assert cs.get_password("13800000000") is None

def test_keyring_unavailable_raises_login_error():
    class Broken:
        def get_password(self, *a): raise RuntimeError("no backend")
        def set_password(self, *a): raise RuntimeError("no backend")
        def delete_password(self, *a): raise RuntimeError("no backend")
    cs = CredentialStore(backend=Broken())
    with pytest.raises(LoginError):
        cs.set_password("x", "y")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_credential_store.py -v`
Expected: FAIL（No module named xuexitong_mcp.login）

- [ ] **Step 3: Write minimal implementation**

Create `server/xuexitong_mcp/login.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_credential_store.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/login.py tests/test_credential_store.py
git commit -m "feat(login): CredentialStore keyring wrapper with unavailable fallback"
```

---

### Task 3: 表单提交校验 + 本地表单服务

**Files:**
- Modify: `server/xuexitong_mcp/login.py`
- Test: `tests/test_intake_form.py`

**Interfaces:**
- Consumes: `CredentialStore`（Task 2）。
- Produces: `login.validate_submission(fields:dict, token:str, expected_token:str)->tuple[str,str]`（返回 account,password，非法抛 LoginError）；`login.collect_credentials(store, open_browser:bool=True, timeout:float=300)->str`（起 localhost 表单、采集、存凭据、返回 account）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_intake_form.py
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import validate_submission, LoginError

def test_valid_submission():
    acc, pwd = validate_submission({"account": "13800000000", "password": "secret"}, "tok", "tok")
    assert acc == "13800000000" and pwd == "secret"

def test_bad_token_rejected():
    with pytest.raises(LoginError):
        validate_submission({"account": "x", "password": "y"}, "bad", "tok")

def test_empty_account_rejected():
    with pytest.raises(LoginError):
        validate_submission({"account": "  ", "password": "y"}, "tok", "tok")

def test_empty_password_rejected():
    with pytest.raises(LoginError):
        validate_submission({"account": "x", "password": ""}, "tok", "tok")

def test_account_stripped():
    acc, _ = validate_submission({"account": " 13800000000 ", "password": "y"}, "tok", "tok")
    assert acc == "13800000000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intake_form.py -v`
Expected: FAIL（cannot import name validate_submission）

- [ ] **Step 3: Write minimal implementation**

Append to `login.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_intake_form.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/login.py tests/test_intake_form.py
git commit -m "feat(login): localhost intake form with CSRF token and validation"
```

---

### Task 4: LoginAutomator（bsk 填表 + 轮询首页）

**Files:**
- Modify: `server/xuexitong_mcp/login.py`
- Test: `tests/test_login_automator.py`

**Interfaces:**
- Consumes: 一个 bsk 对象（现有 `Bsk`），需有 `navigate(url, **kw)`、`eval(js, **kw)`、`here(js, **kw)`。
- Produces: `login.LoginAutomator(bsk)` with `fill_and_submit(account:str,password:str)->None`、`wait_until_logged_in(timeout:float=180,poll:float=2)->dict`（返回 `{"ok":bool,"url":str,"needs_slider":bool}`）；常量 `LOGIN_URL`、`HOME_HOST="i.mooc.chaoxing.com"`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_login_automator.py
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import LoginAutomator, LOGIN_URL

class FakeBsk:
    def __init__(self, urls): self.urls = iter(urls); self.evals = []; self.navs = []
    def navigate(self, url, **kw): self.navs.append(url); return url
    def eval(self, js, **kw): self.evals.append(js); return True
    def here(self, js, **kw): return next(self.urls)

def test_fill_and_submit_targets_fields():
    b = FakeBsk([])
    LoginAutomator(b).fill_and_submit("13800000000", "secret")
    assert b.navs == [LOGIN_URL]
    joined = "\n".join(b.evals)
    assert "getElementById('phone')" in joined
    assert "getElementById('pwd')" in joined
    assert "getElementById('loginBtn')" in joined
    assert "13800000000" in joined

def test_wait_until_logged_in_success():
    b = FakeBsk(["https://passport2.chaoxing.com/login", "https://i.mooc.chaoxing.com/space/index"])
    r = LoginAutomator(b).wait_until_logged_in(timeout=10, poll=0)
    assert r["ok"] is True
    assert r["url"].startswith("https://i.mooc.chaoxing.com")

def test_wait_until_logged_in_timeout():
    b = FakeBsk(["https://passport2.chaoxing.com/login"] * 50)
    r = LoginAutomator(b).wait_until_logged_in(timeout=0.05, poll=0.01)
    assert r["ok"] is False
    assert r["needs_slider"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_login_automator.py -v`
Expected: FAIL（cannot import name LoginAutomator）

- [ ] **Step 3: Write minimal implementation**

Append to `login.py`:
```python
import json
import time

LOGIN_URL = "https://passport2.chaoxing.com/login"
HOME_HOST = "i.mooc.chaoxing.com"


class LoginAutomator:
    def __init__(self, bsk):
        self.b = bsk

    def fill_and_submit(self, account: str, password: str) -> None:
        self.b.navigate(LOGIN_URL, wait="domcontentloaded", readiness=False)
        self.b.eval(
            "const p=document.getElementById('phone'); const w=document.getElementById('pwd');"
            f"p.value={json.dumps(account)}; w.value={json.dumps(password)};"
            "['input','change','keyup'].forEach(n=>{p.dispatchEvent(new Event(n,{bubbles:true}));w.dispatchEvent(new Event(n,{bubbles:true}));});"
            "return true;")
        self.b.eval("document.getElementById('loginBtn').click(); return true;")

    def wait_until_logged_in(self, timeout: float = 180, poll: float = 2) -> dict:
        deadline = time.time() + timeout
        url = ""
        while time.time() < deadline:
            url = self.b.here("return location.href") or ""
            if HOME_HOST in url:
                return {"ok": True, "url": url, "needs_slider": False}
            time.sleep(poll)
        return {"ok": False, "url": url, "needs_slider": "passport2" in url}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_login_automator.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/login.py tests/test_login_automator.py
git commit -m "feat(login): LoginAutomator fills passport2 form and polls for homepage"
```

---

### Task 5: run_login 编排

**Files:**
- Modify: `server/xuexitong_mcp/login.py`
- Test: `tests/test_login_flow.py`

**Interfaces:**
- Consumes: `CredentialStore`、`collect_credentials`、`LoginAutomator`、`Config.login_account/auto_login`。
- Produces: `login.run_login(cfg, bsk, store=None, open_browser=True)->dict`（无凭据先采集；填表提交；等待登录；返回 `{"ok","account","url","needs_slider","stage"}`，密码不入返回）；`login.run_logout(cfg, store=None)->dict`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_login_flow.py
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import login as L
from xuexitong_mcp.config import Config

class FakeBsk:
    def navigate(self, url, **kw): return url
    def eval(self, js, **kw): return True
    def here(self, js, **kw): return "https://i.mooc.chaoxing.com/space/index"

def test_run_login_with_stored_credentials(monkeypatch):
    cfg = Config(); cfg.login_account = "13800000000"
    class Store:
        def get_password(self, a): return "secret"
        def set_password(self, a, p): pass
        def delete_password(self, a): pass
    monkeypatch.setattr(L, "collect_credentials", lambda *a, **k: pytest.fail("should not open form"))
    r = L.run_login(cfg, FakeBsk(), store=Store(), open_browser=False)
    assert r["ok"] is True and r["account"] == "13800000000"
    assert "secret" not in str(r)

def test_run_login_collects_when_no_credentials(monkeypatch):
    cfg = Config(); cfg.login_account = ""
    class Store:
        def __init__(self): self.pwd = None
        def get_password(self, a): return self.pwd
        def set_password(self, a, p): self.pwd = p
        def delete_password(self, a): pass
    store = Store()
    def fake_collect(s, **k): s.set_password("13900000000", "secret"); return "13900000000"
    monkeypatch.setattr(L, "collect_credentials", fake_collect)
    r = L.run_login(cfg, FakeBsk(), store=store, open_browser=False)
    assert r["account"] == "13900000000"

def test_run_logout_deletes(monkeypatch):
    cfg = Config(); cfg.login_account = "13800000000"
    class Store:
        def delete_password(self, a): self.deleted = a
    store = Store()
    r = L.run_logout(cfg, store=store)
    assert r["ok"] is True and store.deleted == "13800000000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_login_flow.py -v`
Expected: FAIL（module has no attribute run_login）

- [ ] **Step 3: Write minimal implementation**

Append to `login.py`:
```python
def run_login(cfg, bsk, store=None, open_browser: bool = True) -> dict:
    store = store if store is not None else CredentialStore()
    account = cfg.login_account
    password = store.get_password(account) if account else None
    if not account or not password:
        account = collect_credentials(store, open_browser=open_browser)
        password = store.get_password(account)
        if not password:
            raise LoginError("采集后仍读不到凭据；请重试 login。")
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_login_flow.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/login.py tests/test_login_flow.py
git commit -m "feat(login): run_login/run_logout orchestration, credentials never returned"
```

---

### Task 6: Policy 让 login/logout 跨 profile 可用

**Files:**
- Modify: `server/xuexitong_mcp/policy.py:28-61`
- Test: `tests/test_login_policy.py`

**Interfaces:**
- Consumes: `policy.allowed_tools(profile, tools, extra, deny)`。
- Produces: `policy.LOGIN_TOOLS=frozenset({"login","logout"})`；allowed_tools 对 student/reviewer/teacher 都并入 LOGIN_TOOLS（与已有 health_check 跨角色一致）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_login_policy.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import policy as P

TOOLS = [("login", "local_write"), ("logout", "local_write"), ("health_check", "read"),
         ("publish_notice", "write"), ("list_my_courses", "read")]

def test_login_logout_in_every_profile():
    for prof in ("student", "reviewer", "teacher"):
        allowed = P.allowed_tools(prof, TOOLS, [], [])
        assert "login" in allowed and "logout" in allowed, prof

def test_student_still_cannot_publish():
    allowed = P.allowed_tools("student", TOOLS, [], [])
    assert "publish_notice" not in allowed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_login_policy.py -v`
Expected: FAIL（login not in student/reviewer allowed）

- [ ] **Step 3: Write minimal implementation**

In `policy.py`, after `REVIEW_TOOLS = frozenset(...)` add:
```python
LOGIN_TOOLS = frozenset({"login", "logout"})   # account-level, available in every profile
```
In `allowed_tools`, change the three return branches to union LOGIN_TOOLS intersected with names. Replace the final `return (allow & names) - set(deny)` with:
```python
    allow |= LOGIN_TOOLS
    return (allow & names) - set(deny)
```
(This adds login/logout to whichever profile branch built `allow`, then intersects with registered names.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_login_policy.py tests/test_policy.py -v`
Expected: PASS（new tests pass; existing policy tests unchanged）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/policy.py tests/test_login_policy.py
git commit -m "feat(login): login/logout available across all profiles"
```

---

### Task 7: MCP login/logout 工具 + CLI 命令

**Files:**
- Modify: `server/xuexitong_mcp/server.py`（工具注册区，约 2750 行附近基础工具旁）、`server/xuexitong_mcp/__main__.py:14-15`（命令 choices）
- Test: `tests/test_login_tools.py`

**Interfaces:**
- Consumes: `login.run_login/run_logout`、`client()`（返回带 bsk 的 client）、`_state["cfg"]`、`tool(L, ...)`。
- Produces: MCP 工具 `login()`→dict、`logout()`→dict（L 类，注册进 TOOLS）；CLI `xuexitong-mcp login`/`logout`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_login_tools.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import server as srv

def test_login_logout_registered():
    names = {n for n, _, _, _ in srv.TOOLS}
    assert "login" in names and "logout" in names
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    assert kinds["login"] == "local_write" and kinds["logout"] == "local_write"

def test_login_tool_returns_status_without_password(monkeypatch):
    from xuexitong_mcp import login as L
    monkeypatch.setattr(L, "run_login", lambda cfg, bsk, **k: {"ok": True, "account": "138", "url": "https://i.mooc.chaoxing.com/space/index", "needs_slider": False, "stage": "logged_in"})
    raw = dict((n, f) for n, _, _, f in srv.TOOLS)["login"]
    class C: b = object()
    monkeypatch.setattr(srv, "client", lambda: C())
    monkeypatch.setitem(srv._state, "cfg", __import__("xuexitong_mcp.config", fromlist=["Config"]).Config())
    r = raw()
    assert r["ok"] is True and "password" not in r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_login_tools.py -v`
Expected: FAIL（login not in TOOLS）

- [ ] **Step 3: Write minimal implementation**

In `server.py`, near the basic tools (e.g. after `health_check` tool), add:
```python
@tool(L, "首次登录引导：打开本机表单输入学习通账号密码（存系统 keyring），自动填表登录，滑块需本人完成；之后凭据持久复用。不回传密码。")
def login() -> dict:
    from . import login as _login
    cfg = _state["cfg"] or _config.load()
    try:
        return _login.run_login(cfg, client().b)
    except _login.LoginError as e:
        return {"ok": False, "error": str(e), "hint": "也可手动在浏览器登录 https://i.mooc.chaoxing.com/space/index 。"}


@tool(L, "退出登录：删除本机系统 keyring 里保存的学习通凭据。")
def logout() -> dict:
    from . import login as _login
    cfg = _state["cfg"] or _config.load()
    try:
        return _login.run_logout(cfg)
    except _login.LoginError as e:
        return {"ok": False, "error": str(e)}
```
In `__main__.py`, extend the command choices and handling. Change:
```python
    ap.add_argument("command", nargs="?", default="serve", choices=["serve", "update", "rollback", "schedule", "login", "logout"],
```
After the `if a.command in ("update", "rollback", "schedule"):` block (before `from .server import ...`), add:
```python
    if a.command in ("login", "logout"):
        import json as _json
        from . import login as _login
        from .bsk import Bsk
        try:
            if a.command == "logout":
                out = _login.run_logout(cfg)
            else:
                b = Bsk(cfg)
                b.ensure_session()
                out = _login.run_login(cfg, b)
        except _login.LoginError as e:
            print(_json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)); sys.exit(1)
        print(_json.dumps(out, ensure_ascii=False, indent=1)); return
```
Also update the `login_required` hint in `server.py` `_err` (the `if e.code == "login_required":` branch) so its `hint` mentions the new tool:
```python
            "error": msg, "hint": "请调用 login 工具（或 xuexitong-mcp login）输入账号密码自动登录，滑块需本人完成；也可手动在浏览器登录。不自动重试，不更换实例。"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_login_tools.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add server/xuexitong_mcp/server.py server/xuexitong_mcp/__main__.py tests/test_login_tools.py
git commit -m "feat(login): MCP login/logout tools and CLI commands"
```

---

### Task 8: 依赖、配置模板、README、安装脚本

**Files:**
- Modify: `server/pyproject.toml`（dependencies）、`requirements-lock-py314-linux.txt`、`config/config.example.toml`、`README.md`、`scripts/install.sh`、`scripts/install.ps1`

**Interfaces:**
- Consumes: 前述 login 模块。
- Produces: 安装即带 keyring；config 模板含 `[login]`；README 告知凭据用途。

- [ ] **Step 1: Add keyring dependency**

In `server/pyproject.toml` `dependencies` list, add `"keyring>=24"`:
```toml
dependencies = ["mcp>=1.9", "keyring>=24", "tomli>=2.0; python_version < '3.11'"]
```
In `requirements-lock-py314-linux.txt`, add a line `keyring==25.6.0`（安装后按实际锁定版本回填；先 `pip install keyring` 取版本）。

- [ ] **Step 2: Update config.example.toml**

Add after the top comment block (keep "No username, password... belongs in this file" and clarify):
```toml
[login]
# 首次登录引导：账号密码存系统 keyring（不在此文件），MCP 自动填表登录，滑块需本人完成。
auto_login = true        # 默认开：会话过期时用 keyring 凭据自动重登；设 false 或 env XUEXITONG_MCP_AUTO_LOGIN=0 关闭
login_account = ""       # 当前账号用户名（非密码）；运行 login 后自动填写
```

- [ ] **Step 3: Update README**

Add a "首次登录" section: 运行 `xuexitong-mcp login`（或 MCP `login` 工具）→ 浏览器弹本机表单输账号密码 → 存系统 keyring → 自动填表登录 → 如弹滑块本人完成 → 到达各自首页；之后凭据持久复用，`logout` 删除。安全告知：密码仅存本机系统凭据库，不进配置/日志；滑块/短信/协议仍由本人完成；auto_login 默认开。

- [ ] **Step 4: Install keyring into the dev venv and verify import**

Run: `C:/Users/11079/.cache/xuexitong-mcp/venv/Scripts/python.exe -m pip install keyring`
Run: `C:/Users/11079/.cache/xuexitong-mcp/venv/Scripts/python.exe -c "import keyring; print(keyring.get_keyring())"`
Expected: prints a backend (Windows: WinVaultKeyring). If backend unavailable, note Linux fallback in README.

- [ ] **Step 5: Commit**

```bash
git add server/pyproject.toml requirements-lock-py314-linux.txt config/config.example.toml README.md scripts/install.sh scripts/install.ps1
git commit -m "feat(login): keyring dependency, config template, README onboarding docs"
```

---

### Task 9: 全套回归 + 真实登录实测 + 发布

**Files:**
- Modify: `docs/COVERAGE.md`（登录引导轮次记录）、`server/xuexitong_mcp/__init__.py`（版本）、`MANIFEST.sha256`

- [ ] **Step 1: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: 全部通过（现有 256 + 新增 login 测试）。

- [ ] **Step 2: Startup self-test**

Run: `BSK_AUTO_START=0 python -I scripts/launch_stdio.py --list-tools`
Expected: login/logout 出现在工具列表。

- [ ] **Step 3: 真实登录实测（需维护者本人账号 + 人工滑块）**

前提：维护者已在浏览器登录态过期或首次。运行 MCP `login` 工具或 `xuexitong-mcp login`：
- 确认本机表单弹出（127.0.0.1）。
- 输入本人账号密码提交 → 确认存进 keyring（`python -c "import keyring; print(keyring.get_password('xuexitong-mcp','<account>') is not None)"` 返回 True，**不要在聊天里打印密码本身**）。
- 确认 bsk 自动填表提交，弹滑块时本人完成。
- 确认到达 `i.mooc.chaoxing.com` 首页，`login` 返回 ok=true。
- 会话过期后再跑，确认无需重新输入（凭据复用）。

- [ ] **Step 4: Update COVERAGE + version + MANIFEST**

Add a round note to `docs/COVERAGE.md` documenting login onboarding (semi-auto, keyring, human slider). Bump `__init__.py` `__version__ = "0.8.0"`. Regenerate MANIFEST.sha256（LF-normalized sha256 of all tracked files except MANIFEST）and verify with `updater.check_manifest`.

- [ ] **Step 5: Commit, tag, push（需维护者确认推送）**

```bash
git add -A && git commit -m "Release 0.8.0: first-time login onboarding (keyring + semi-auto)"
git tag -a v0.8.0 -m "xuexitong-mcp 0.8.0: login onboarding"
git push origin fix/privacy-and-wait-defects && git push origin v0.8.0 && git push origin fix/privacy-and-wait-defects:main
```