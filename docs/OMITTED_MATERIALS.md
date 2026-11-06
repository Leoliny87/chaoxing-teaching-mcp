# 本批未包含的材料

本批是可核对的补充交接，不声称穷尽历史研究或完成真实平台验收。原始本地材料保留，不作为公开目录的一部分。

## 未部署工作区

以下是逐文件范围清单。仅从作业模块提炼纯函数，并从等待逻辑提炼依赖观察回调与时钟的方法适配，分别放在 `reference/` 中；其余不默认导入，也不以 `.disabled` 后缀代替隔离。

- `README.md`：整套候选入口、工具注册或控制逻辑未纳入，避免形成可误启用的第二套服务。
- `pyproject.toml`：整套候选入口、工具注册或控制逻辑未纳入，避免形成可误启用的第二套服务。
- `tests/test_activity_response_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_assignment_library_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_assignment_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_class_selection_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_discussion_response_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_grades_response_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_guard_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_health_login_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_http_response_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_idle_health_session_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_inbox_response_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_login_redirect_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_no_replay_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_notice_gate_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_notice_response_workbench.cjs`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_observed_target_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_passive_wait_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_readiness_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_safety_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `tests/test_shutdown_workbench.py`：候选版本专属测试，与本批默认核心接口不同，未按本批运行器复测。
- `xuexitong_mcp/__init__.py`：整套候选入口、工具注册或控制逻辑未纳入，避免形成可误启用的第二套服务。
- `xuexitong_mcp/__main__.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/bsk.py`：整套候选入口、工具注册或控制逻辑未纳入，避免形成可误启用的第二套服务。
- `xuexitong_mcp/config.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/ops_activity.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/ops_assignment.py`：仅提炼三个纯函数；真实创建/保存/回收、持久日志和锁协议未公开为可运行候选。
- `xuexitong_mcp/ops_content.py`：讨论控件和导航候选仅交接设计；真实页面遮挡尚未验收。
- `xuexitong_mcp/ops_course.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/ops_notice.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/privacy.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/readiness.py`：与默认核心相同或研究副本重复，没有重复分发。
- `xuexitong_mcp/server.py`：整套候选入口、工具注册或控制逻辑未纳入，避免形成可误启用的第二套服务。
- `xuexitong_mcp/xxt.py`：仅提炼等待函数；整合候选 mixin 的入口未纳入。

完整候选以前有 7 项日志隐私回归失败；这是先前本地结果，本批没有重跑或宣称其通过。

## 历史及外部组件

- 旧 `notice_gate.py`、`test_notice_gate.py`：不同适配接口的通知原型；本批仅保留设计要点，完整原型未重新验收。
- 旧 `bsk_receipt_redact.py`、`test_bsk_receipt_redact.py`：早期日志过滤研究；本批使用当前核心的回归样例与合成输出审计，不把旧过滤器当作当前隐私缺陷已经修复。
- 旧 `bsk_visible_library_probe.py`、`test_bsk_visible_library_probe.py`：包含调用真实 BrowserSkill 的探测驱动；不放入本批纯离线运行范围。
- 旧离线门户、通知和作业试验、旧安装/升级脚本及现场操作驱动：版本与状态契约不同，含依赖现场状态的流程；未逐项重新执行，不提供一键回放。
- BrowserSkill 厂商扩展本体、厂商实现片段和相关诊断补丁：不随本项目分发；从官方渠道取得相应依赖，不据本项目的公开授权推定第三方再分发权。
- 私有宿主代码、认证配置、浏览器 profile、真实教学对象、截图与运行日志：不属于本批公开源码。
- 内部任务提示、私人笔记、个人化规则及会话导出：不公开。

没有因缺少 LICENSE 文件而剔除用户自有项目代码；项目许可证仍由维护者决定。本批也没有新增或变更第三方许可。
