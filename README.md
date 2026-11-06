# Chaoxing Teaching MCP — 开发交接首批源码

**这是开发交接源码，不是可直接给师生使用的生产版本。当前仍有日志和错误输出的隐私缺陷；修复并验证前仅使用合成数据，不得使用真实账号。**

本次保留 rc6 运行核心，版本为 `0.2.0rc6+publiccore.1`，定义 45 个 MCP 工具。首批仅含运行源码、空白配置模板、依赖版本清单和 stdio 启动入口，**不含测试集或 CI 工作流**。历史候选、诊断脚本、现场记录、账号、浏览器登录态和第三方扩展本体均未纳入。

交接时列出的三类输出风险（会话标识进入日志、未结构化异常文本进入日志、异常内容进入 MCP 工具结果）和等待逻辑吞掉超时/控制状态错误的问题已在 `fix/privacy-and-wait-defects` 分支修复，并在 `tests/test_privacy_and_wait.py` 中用合成数据加了回归测试（`python -m pytest tests`）。同时修复了 Windows 上的问题：bsk 输出按系统 GBK 解码导致中文标签的浏览器实例被判为“未连接”；`O_NONBLOCK` 不存在导致上传预演报错。另外，读取工具改为总在静态基准页执行同源 fetch，避免新版 Vue 页面持续重绘导致 BrowserSkill 拒绝执行。

2026-11-06 在一台 Windows 教师机上用真实登录态只读验证：health_check、list_courses、open_course、list_chapters、list_materials、list_notices、list_assignments、list_assignment_library、list_exams、list_activities、list_students、get_grades、list_inbox 均返回结构完整的数据。`list_discussions` 仍然失败：课程入口已跳转到新版界面 `mooc2-ans-vue/fanyav3/tch`，旧版 iframe 结构不存在，讨论区 bbsid 取不到。health_check 的 `ok` 仍为 false，原因只是未安装防 App 跳转扩展。Windows 上请把虚拟环境建在短路径（例如 `%USERPROFILE%\.cache\xuexitong-mcp\venv`），否则依赖的 DLL 可能因路径过长而加载失败。

先前本地兼容测试集合有 109 项通过，这不是本仓库的 CI 结果，本次也未重新执行该集合。先前包含已知等待问题的检查运行 111 项，有 3 个失败子测试。工具数量和离线检查均不代表完整功能验收；新版全部功能、学生端、真实页面稳定性及 DSH 端到端写入尚未完成验收。

## 安装与离线开发

使用独立 Python 环境。`requirements-lock-py314-linux.txt` 记录已观察到的 Linux / CPython 3.14.4 环境中 28 个运行依赖版本；它不是含包哈希的完整供应链锁，未覆盖 setuptools 构建工具，干净安装和跨平台安装尚未验收。

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -c requirements-lock-py314-linux.txt -e ./server
# 离线列出工具契约；不会调用浏览器业务：
.venv/bin/python -I scripts/launch_stdio.py --list-tools --config config/config.example.toml
```

Python 依赖从官方分发渠道安装；Chrome、BrowserSkill CLI/daemon/扩展及防 App 跳转扩展需要另行配置，不由本项目安装。先前观察到的 BrowserSkill 版本为 0.4.2，来源为 [Tencent/BrowserSkill](https://github.com/Tencent/BrowserSkill)。本次未验证新机器上的兼容性。缺少防跳转扩展时，健康检查对应项可能不满足，不能据此承诺 `health_check` 全部通过。

## 修复后的本地接入参考

以下仅说明未来接入方式；修复前不要用真实账号执行。每位成员在自己的电脑和选定的 Chrome profile 中手动登录自己的学习通账号，连接本人已有的 BrowserSkill 实例。复用该指定实例；连接不可用时停止，不切换其他实例。不要共享 profile、密码库、cookie 或运行状态。本项目没有“填入账号密码即可获得完整功能”的接口。

把 `config/config.example.toml` 复制到仓库外的 `~/.config/xuexitong-mcp/config.toml`，按本人的环境配置。模板的课程写入白名单和上传目录白名单均为空。MCP 宿主可参考 `config/mcp.stdio.example.json`，填写本机绝对路径及本人已有 BrowserSkill 实例 ID，不把个人配置提交到仓库。

```sh
# 仅供修复后完成本地权限配置时参考：
export XUEXITONG_MCP_BROWSER='YOUR_EXISTING_BROWSER_INSTANCE_ID'
.venv/bin/python -I scripts/launch_stdio.py
```

推荐入口为 `scripts/launch_stdio.py`，运行 `server/` 中的代码并隔离各进程状态；默认使用 stdio，不开启 HTTP 监听。写工具有预演和显式确认参数，宿主仍需实现权限与审批，`plan_id` 本身不等于人工批准。失败、超时或结果不明时先核查状态，避免重复提交；不要绕过浏览器访问校验。

## 文件与许可证

`MANIFEST.sha256` 列出本次发布文件的 SHA256（不包含清单自身）。除本 README 与新清单外，运行代码及模板均保持交接快照中的原字节，本次未修复或替换运行逻辑。

项目尚未选择统一开源许可证，由维护者决定；本次没有新增许可证或重许可。第三方程序、依赖包缓存、厂商扩展源码和私有宿主组件不随本项目分发，应从其官方渠道取得并遵守对应许可。
