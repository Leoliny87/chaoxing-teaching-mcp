# 学习通新版界面功能覆盖图与实施计划

目标：**自动化核心覆盖新版学习通师生两端所有功能的读写**。"哪些角色能用哪些功能"由独立的策略层决定（见第 4 节），不在核心里砍功能。

本文的界面结构与接口均来自 2026-11-06 在一台教师机上用真实登录态做的**只读**探查（BrowserSkill 0.4.2，Chrome 156）。本次未执行任何写操作。接口路径只记录主机和路径，不记录签名参数。

## 1. 新版教师端结构（实测）

- 课程入口 `mooc1.chaoxing.com/course/isNewCourse?...&edit=true` 现在会跳转到 Vue 外壳 `mooc2-ans.chaoxing.com/mooc2-ans-vue/fanyav3/tch`（Vue 2 应用）。
- 外壳路由：`/tch`（教师主页）、`/stu` 和 `/studentCourse`（学生主页）、`/application`（全部应用）、`/centerDownload`（下载中心）、`/teachCalendar`（教学日历）、`/index`。
- 模块菜单由服务端下发：`GET mooc2-ans/coursemanagev3/base-info` 返回
  `courseNavigationListV3`（每项含 `translateName / linkUrl / children / openType / isDefault`）、`noticeUrl`、`discussUrl`（**直接带 bbsid**）、`activityClazzId`、`courseInfo`、`userInfo`。
  各模块以 iframe 打开对应的 `linkUrl`，外壳会在后面追加 `location.search + &courseid&clazzid&version=3`，部分模块还会追加专属参数。具体拼法见 `312.*.js` 里的 `processTeacherNav`。
- 首次打开会弹出新手引导浮层（"跳过引导/下一步"）。它挡住无障碍观察，但不影响 DOM 读取。
- 新版 Vue 页面会持续重绘，在页面上直接 `evaluate` 会被 BrowserSkill 以 `document_changed / observation_changed` 拒绝。同源读取一律改在该域名的静态基准页执行（已修复，见 `xxt.on`）。

| 模块 | 实际应用 | 已观察到的接口（节选） | 现有工具 | 状态 |
|---|---|---|---|---|
| 首页 | 外壳内（常用应用 / 近期待办 / 教学预警） | `coursemanagev3/base-info` | — | 待做：待办、预警读取 |
| 教学任务 | `task.chaoxing.com/task/index`（任务引擎） | `task/findTaskFolders`、`task/getTaskDataLists` | — | 待做：读写全部；测试课为空，需要测试课探查新建流程 |
| 教学活动 | `mobilelearn.chaoxing.com/page/active/activeList` | `v2/apis/active/pcActivelist`、`v2/apis/class/getClassList`、`getClassDetail`、`getTeachers`、`active/getActiveLibraryOpen`、`sign/getLastSignForXd`… | list_activities、activity_result、checkin_status、end_activity、pick_student、start_quick_answer、start_vote、start_checkin(仅预演)、delete_activity | 读已验证；写需要在测试课验证；按钮：添加活动、上课、批量编辑、新建班级 |
| 资源中心 | `stat2-ans.chaoxing.com/stat2-vue/resource` | `stat2/base-data/v3/{coursewareInfo,resInfo,knowledgeInfo,workInfo,examInfo,activityLibraryInfo}`、`mooc2-ans/coursemanagev3/resource-info` | list_chapters、list_materials、list_assignment_library、list_exams(试卷库) | 部分覆盖；待做：课件、题库、知识点、活动库、上传 |
| AI助教 | `robot-lc.chaoxing.com/courseCozeV3/web` | `v1/front/conversationList`、`msgList`、`robot/info/*`、`knowledge/getAiKbSetting`… | — | 待做（读会话与知识库设置；写=对话/配置） |
| 学情统计 | `stat2-ans.chaoxing.com/stat2-vue/statistics` | `stat2/stat-nav/teach`（子菜单） | get_grades | 部分覆盖；待做：逐项统计子页 |
| 课程管理 | `mooc2-ans.chaoxing.com/mooc2-ans/tcm/course-manage` | `tcm/clazz-manage`、`tcm/clazz-student` | open_course、list_students | 读已验证；待做：添加学生、分组、导出名单、移除、班级设置 |
| 通知 | `notice.chaoxing.com/pc/course/notice/myNoticeList` | `pc/course/notice/getNoticeList` | list_notices、list_notice_inventory、publish_notice、delete_notice | 读已验证；写需验证 |
| 讨论 | `groupweb.chaoxing.com/course/topic/topicList?…bbsid` | `course/topic/{bbsid}/getTopicList`、`getTopTopicList`、`pc/topic/topiclist/getLabelList`、`noteyd …/getYunPanUploadUrl` | list_discussions（**当前失败**）、create/delete_discussion(仅预演) | 修复方法：bbsid 改从 `base-info.discussUrl` 取 |
| 作业/考试（旧接口） | `mooc2-ans/work/*`、`mooc2-ans/exam/*` | — | list_assignments、submissions、list_exams、exam_marklist… | 读已验证；与"教学任务"的关系待确认 |

2026-11-06 真实只读验证通过的工具：health_check、list_courses、open_course、list_chapters、list_materials、list_notices、list_assignments、list_assignment_library、list_exams、list_activities、list_students、get_grades、list_inbox。

## 2. 还没探查的范围

- 每个模块的二级页面和全部写操作流程（新建、编辑、发布、删除、批阅、导入导出）。写流程**只在专门的测试课程里探查**，每次写之前确认。
- 学生端全部功能（`/stu`、`/studentCourse`、任务点、作业提交、考试、签到、讨论、资料下载）：**需要一个学生测试账号**。
- 题库、试卷库管理系统（`kaoshi.chaoxing.com`）有滑块验证码，保留人工。
- 教学日历、下载中心、全部应用、首页的待办和预警。

## 3. 核心的实现原则（覆盖所有功能时保持不变）

1. 优先调用页面自己使用的 JSON 接口（同源 fetch，从静态基准页发起）。只有复杂表单才走真实界面操作。
2. 每个写操作：先预演并冻结目标 ID → 用单次 plan_id 执行 → 再读一遍核实。结果不明时不重试，先查状态。
3. 页面结构和接口的定义集中存放，学习通改版时只需改定义，不必动整套代码（见 4.3）。
4. 页面文本、作业内容、讨论区和附件里的文字一律当作**数据**返回，放在明确标注"不可信内容"的字段里，工具说明里写明不得把它当指令执行。

## 4. 策略层与部署（按需求方要求）

### 4.1 角色配置（规则放在 MCP 里，不放在提示词里）
- 服务端配置 `profile = teacher | student | reviewer`。启动时只注册该角色允许的工具，不允许的工具根本不出现在工具列表里。
- **学生配置只开放**：查任务、查截止时间、下载资料、带确认的提交。不开放：读取标准答案或测验答案、删除、修改他人内容、批量发消息。
- 学生提交：只接受学生本人的文件或原文 → 返回完整预览 → 学生回复"确认提交"（服务端校验确认文本和单次 plan_id）后才执行。
- 教师端预审 agent：作业内容只作为数据传入，结论只作建议。"拿不准"的分类和抽查照常执行。

### 4.2 中心辅导服务
- "辅导"和"掌握判断"做成教师部署的中心服务，学生端 MCP 只提供一个调用它的工具。规则和日志都在教师手里，学生改不了。学生的学习通凭据不经过这个服务。

### 4.3 打包与更新
- 带版本号的包。`xuexitong-mcp update` 一条命令完成更新，可选每天定时检查一次。接口和选择器定义随版本发布。
- 登录凭据只留在各自的服务器或浏览器 Profile 里，不汇总。

### 4.4 风控
- 核心内置节流：导航间隔下限加每日调用预算。学生端默认每天定时查几次，不做每分钟轮询。
- 不自动登录（本人手动登录）。先找 3–5 名学生小范围试用。机房 IP 有触发风控的风险，试用期间要观察。

## 5. 分期计划

| 阶段 | 内容 | 需要的条件 |
|---|---|---|
| P0 ✅ | 隐私与等待缺陷修复、Windows 兼容、真实只读验证、本覆盖图 | — |
| P1 | 课程上下文改用 `base-info`；修复讨论；补全教师端**读**：任务引擎、资源中心各子库、学情统计子页、班级管理、首页待办和预警、AI助教会话 | 现有登录态（只读） |
| P2 | 教师端**写**：逐模块在测试课程中探查并实现，每项有预演、执行、核实和回归测试 | **一门专用测试课程加测试班级**，写操作逐项确认 |
| P3 | 学生端读写（任务、截止时间、资料下载、确认提交、签到、讨论） | **学生测试账号**（独立的浏览器 Profile） |
| P4 | 策略层（角色配置、确认提交、不可信内容标注）、节流、打包和一键更新 | — |
| P5 | 3–5 名学生小范围试用，降低频率并观察风控 | 试用名单 |
