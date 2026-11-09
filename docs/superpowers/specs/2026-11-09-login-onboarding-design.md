# 首次使用登录引导设计（Login Onboarding）

日期：2026-11-09 · 状态：待用户审阅 · 版本目标：v0.8.0

## 1. 目标与背景

让任何首次使用 chaoxing-teaching-mcp 的人能顺畅登录：在一个地方输入学习通账号密码，MCP 据此自动登录 `i.mooc.chaoxing.com`，到达使用者自己的主页。解决当前"登录态过期需本人手动重登"的摩擦。

现状冲突：现有设计刻意"不询问/不保存密码、不自动登录、登录由本人处理"（README、policy.py、config.example.toml）。本功能**有意改变这一安全模型**，经维护者明确批准（2026-11-09），改为"凭据存系统 keyring + 半自动登录"。

## 2. 已定决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 登录方向 | **半自动**：MCP 自动填账号密码并提交，**滑块验证码由人工划** | 学习通反爬下滑块无法可靠自动通过；不做反反爬 |
| 凭据输入载体 | **本地网页表单弹出**（localhost） | 跨 MCP 宿主通用，最贴近"弹出"，不依赖宿主交互能力 |
| 凭据存储 | **系统 keyring**（OS 凭据库） | 不落明文 config；Windows 凭据管理器/macOS Keychain/Linux Secret Service |
| auto_login 默认 | **默认开** | 维护者要求所有用户首次默认走引导登录流程 |
| 登录主页 | `https://i.mooc.chaoxing.com/space/index`（即现有 FIXED_HOMEPAGE） | 与现有一致 |

## 3. 架构（新增 `server/xuexitong_mcp/login.py`，4 个组件）

### 3.1 CredentialStore（keyring 封装）
- `get_password(account) -> str|None`、`set_password(account, password)`、`delete_password(account)`、`get_account() -> str|None`。
- keyring service 名固定 `xuexitong-mcp`；account（用户名）作为 keyring username，同时把当前 account 记到 config 的非敏感字段 `login_account`（仅用户名，非密码）。
- keyring 不可用（如无 Linux Secret Service）时**明确报错并回退引导手动登录**，不静默存明文。
- 密码永不进日志、异常文本、MCP 工具结果、config 文件、MANIFEST。

### 3.2 本地凭据表单服务（IntakeFormServer）
- 仅绑 `127.0.0.1`，随机空闲端口；生成一次性 CSRF token 嵌入表单。
- 极简 HTML：账号输入框 + 密码框（type=password）+ 提交按钮 + 一段说明（"凭据仅存于本机系统凭据库，用于自动登录学习通；滑块仍需本人完成"）。
- POST 校验 token + 非空 → `CredentialStore.set_password` → 返回"已保存"页 → 关闭服务。
- 用 `webbrowser.open` 或 bsk 新标签打开表单 URL；服务在提交后或超时（如 5 分钟）自动停止。
- 只收账号密码，不收验证码/cookie。

### 3.3 LoginAutomator（bsk 驱动）
- 导航 `https://passport2.chaoxing.com/login`（已实测：登录按钮 `BUTTON#loginBtn`，存在 `captcha` 滑块与 `needVcode` 隐藏标志）。
- 从 keyring 取凭据，填账号/密码输入框（确切字段 ID 实施时实测确认；页面自身 JS 负责密码加密，MCP 只填明文到框）。
- 点 `#loginBtn` 提交 → 返回"请在浏览器完成滑块验证"的状态 → 轮询 `location.href` 直到离开 passport2 到达 `i.mooc.chaoxing.com`（登录成功）或超时。
- 失败/超时返回明确状态，不自动重试提交（避免重复触发风控）。
- 复用现有 bsk 会话/标签管理；密码经 bsk evaluate 填入，bsk 日志脱敏（现有 _summarize_args 已脱敏值）。

### 3.4 集成
- **CLI**：`xuexitong-mcp login`（跑表单采集 + 自动登录）；`xuexitong-mcp logout`（删 keyring 凭据）。
- **MCP 工具**：`login`（local_write 类，触发引导/报告登录状态，不回传密码）；`logout`。
- **触发**：`health_check`/工具遇到 `login_required` 时，结果引导用户调用 `login`；`auto_login=true` 且 keyring 有凭据时，会话过期自动走 LoginAutomator（滑块仍人工）。
- 学生/教师/预审各 profile 都可用 login（登录是账号级，与角色无关）。

### 3.5 凭据生命周期（输入一次，持久复用）
- **首次**：本地表单输入一次账号密码 → 存 keyring 持久保存 → 自动登录。
- **之后**：会话过期时自动用 keyring 凭据重登，**无需再次输入**；平台不要滑块则全自动，要滑块则人工划一次。
- **仅在**用户 `logout`、修改密码、或清空 keyring 时才需重新输入。
- 密码错误导致登录失败时，提示用户重新跑 `login` 更新凭据，不反复重试。

## 4. 配置变更（config.py / config.example.toml）

```toml
[login]
auto_login = true        # 默认开：会话过期时用 keyring 凭据自动填表（滑块人工）
login_account = ""       # 当前账号用户名（非密码）；密码只在 keyring
```
- config.example.toml 顶部"不放密码"注释保留并补充：密码存 keyring，此文件仅存用户名与开关。
- 环境变量可收窄（如 `XUEXITONG_MCP_AUTO_LOGIN=0` 关闭），与现有 profile 收窄一致。

## 5. 安全边界

- 密码仅存 OS keyring；表单 localhost + 一次性 token + 提交即关。
- 密码不进 config/日志/chat/工具结果/MANIFEST/进程持久参数。
- 填密发生在用户自己的浏览器_profile_，页面 JS 自行加密提交。
- **不 bypass 滑块/短信/协议**——这些仍由本人完成（与现有风控一致）。
- 不做账号密码的集中收集/上传；每台机器各自的 keyring。
- 默认开 auto_login 是维护者明确决定；表单与 README 须明示凭据用途与存储位置，取得使用者知情同意。

## 6. 测试

- 单测（合成数据，mock keyring/bsk）：CredentialStore 增删查、keyring 不可用回退；表单 CSRF 校验/非空校验/localhost 绑定/提交后关闭；LoginAutomator 填表→点击→轮询成功/超时（mock bsk）。
- 实测：维护者本人账号跑完整 login 流程（人工划滑块），核实到达各自首页；会话过期后 auto_login 重登。
- 回归：现有 256 测试不受影响；login 工具在各 profile 注册正确。

## 7. 依赖

- 新增 `keyring`（及其平台后端）；更新 requirements-lock 与 install 脚本依赖安装。Linux 无 Secret Service 时回退手动登录并提示。

## 8. 范围外（明确不做）

- 滑块/短信/协议自动化（反反爬，不做）。
- 密码明文存储、集中收集、上传。
- 多账号切换 UI（每个安装绑定一个浏览器实例/一个账号；多账号=多安装）。
- 改变现有"学生端不代签/不代考"等学术诚信约束（登录功能与那些无关）。

## 9. 已知风险/待实施确认

- passport2 账号/密码输入框确切 ID 与提交后加密流程：实施时实测确认（已确认 loginBtn/captcha 存在）。
- 自动填表可能触发学习通设备风控（新设备滑块更频繁）：半自动设计已预期人工滑块。
- keyring 跨平台后端差异：Linux 需 Secret Service，缺失时回退。
- 默认开 auto_login 改变安全默认：须在 README/表单充分告知。