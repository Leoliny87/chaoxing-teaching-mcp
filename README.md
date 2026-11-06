# Chaoxing Teaching MCP — 开发交接源码与合成测试

**这是开发交接源码，不是可直接给师生使用的生产版本。当前仍有日志和错误输出的隐私缺陷；修复并验证前仅使用合成数据，不得使用真实账号。**

本次保留 rc6 运行核心，版本为 `0.2.0rc6+publiccore.1`，定义 45 个 MCP 工具。运行核心保留空白配置模板、依赖版本清单和 stdio 启动入口。本补充提供合成离线测试、作业契约纯函数和默认入口不引用的等待方法参考；**没有 CI 工作流**。历史候选、诊断脚本、现场记录、账号、浏览器登录态和第三方扩展本体均未纳入。

当前有三类已用合成数据确认的输出风险：会话标识可能进入日志、未结构化异常文本可能进入日志、异常内容可能进入 MCP 工具结果。另有等待逻辑可能吞掉部分超时或控制状态错误后继续轮询的问题。这些缺陷需要后续维护者修复和增加回归测试。

本地隔离复测中，兼容集合 109 项通过；默认完整集合 111 项有 3 个已知失败子测试。合成日志审计仍确认 3 类风险。显式 `--reference` 模式通过进程内 monkeypatch 替换等待方法后，连同 5 项作业契约测试共 116 项通过；这不代表默认核心已经修复。这些不是 GitHub CI 结果。测试隔离是防误调用的进程内保护，不是恶意代码沙箱。复现命令、隔离边界和独立参考测试结果见 [合成测试说明](docs/OFFLINE_TESTS.md)。工具数量和离线检查均不代表完整功能验收；新版全部功能、学生端、真实页面稳定性及 DSH 端到端写入尚未完成验收。

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

`MANIFEST.sha256` 列出本次发布文件的 SHA256（不包含清单自身）。`server/` 运行代码、配置模板及正式启动入口保持首批提交的原字节，本补充未修复或替换默认运行逻辑。未部署参考见 [reference/README.md](reference/README.md)，本批未包含的材料见 [交接缺项](docs/OMITTED_MATERIALS.md)。

项目尚未选择统一开源许可证，由维护者决定；本次没有新增许可证或重许可。第三方程序、依赖包缓存、厂商扩展源码和私有宿主组件不随本项目分发，应从其官方渠道取得并遵守对应许可。
