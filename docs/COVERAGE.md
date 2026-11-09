# 学习通新版界面功能覆盖图与实施计划

目标：**自动化核心覆盖新版学习通师生两端所有功能的读写**。"哪些角色能用哪些功能"由独立的策略层决定（见第 4 节），不在核心里砍功能。

本文的界面结构与接口来自 2026-11-06 在一台教师机上用真实登录态做的探查（BrowserSkill 0.4.2，Chrome 156）。第 1 节是只读探查。1.2 节起的写操作全部在测试课「助手」里实际执行过，测试数据都以 `[MCP测试]` 开头。接口路径只记录主机和路径，不记录签名参数和真实 ID。

## 0. 当前完成度（2026-11-09，第九轮后）

注册的工具：共 215 个；教师配置 191 个、学生配置 21 个（可再开讨论四项）、预审配置 63 个。学生端的每一次写入（暂存、提交作业、提交活动作答、回复讨论）都必须带学生本人的「确认提交」，注册时就检查。2026-11-07 曾通过真实 MCP stdio 连接实测，均能被 agent 调用（list_courses、list_my_assignments 实时返回数据；学生调用 publish_notice 得到 Unknown tool）。下面是按「能不能用 MCP 完成」的总览，细节见后文各节。

**已做成工具并在测试课实测**
- 课程与班级：课程列表、打开课程、模块/仪表盘/资源概览、学生名单、新建班级、调班、班级分组（查看方案和小组、新建小组、把学生分到小组）。课程设置（学生端配置和课程设置里 20 项开关/选项/文字，含允许学生自测、视频水印、承诺书、课程通知、试读、资源下载、评价、AI 功能、课程说明）；班级设置（允许加入、加入需同意、允许退课、忽略视频拖拽、对学生隐藏、结课/取消结课、人数上限）和班级改名；把学生移出班级、从退课日志恢复、从本课另一个班添加学生；教师团队、成绩权重（经典模式读写）、加班/退课日志。
- 章节：读内容、改名、写正文（格式白名单）、插入链接/注释/讨论/扩展阅读/章节测验/速课/图书/图书内页/全景/投票问卷/课程图谱，以及文档、音频、视频、图片、附件、动画六种文件（本机上传或直接引用课程资料，即「本课资料」）；文档导入（Word/PDF 转成正文）、AI 排版（三种模板，预演即给出排版结果）、智能编写（平台 AI 先写大纲再写正文，追加到页面末尾；自定义文章类型/目录结构/写作风格）、AI 校正（文本和文档检测、把文本修改建议替换进正文）、上传新的全景图片/视频；移到另一章节下、调整顺序、按大纲快速导入目录、删除（锁定子章节）。
- 作业：23 种题型新建、答题卡作业、发放（含常用设置）、修改已发布作业的起止时间、提交情况、逐题读学生作答、批阅给分（含批语、部分批阅）、打回、按学生催交（收件人在预演时锁定）、删除到回收站/还原。
- 试卷与考试：22 种题型（含选做题）建卷、自动随机组卷（按题型从题库抽题）、平行试卷（新建、加入/移除子卷、难度、序号、归类、同步子卷标题，结构不一致时拒绝）、试卷库「导入试卷」（平台 Word 模板或 .ti 文件，也可导入成平行试卷的子卷）、导出试卷（Word/PDF/Excel/Ti）、发布考试（含常用防作弊和查看设置）、修改已发布考试的时间和时长（平台的校验提示原样返回）、考试批阅页人数；考试和试卷删除到回收站、还原、试卷彻底删除（被考试引用的试卷平台不允许彻底删除，工具会拒绝）。
- 题库：24 种题型新增、列表（不返回答案）、修改题目、文件夹（新建、把题移进去）、删除到回收站/还原、难度、标签（新建、打标签）、批量导入（按题目数据生成模板 Excel 导入 14 种题型；导入本机 Excel/.ti 文件；智能导入：普通文本交给平台识别）、导出到本机（Excel/Word/PDF/Ti，可选不含答案）。
- 课程图谱：读取知识点大纲和关系；按缩进大纲批量添加、改名、删除到图谱回收站/还原、前置/后置/关联关系、按班显示隐藏、把题库题目关联到知识点、插入章节。
- 新版图谱（测试课已切换到新版）：切换到新版；六种图谱（知识图谱、知识列表、学习地图、问题图谱、能力图谱、课程思政图谱）的显示/隐藏（新版「设置 → 图谱设置」的开关）；知识列表（分页、排序、按标签筛选，添加知识点）；知识点属性（知识类型、说明、标签、教学目标、参考学时）；学习地图（按阶段读取班级完成率和掌握率）；移动知识点和调整顺序；课程思政图谱读取；问题图谱（层级名称、问题增改、关联下一层问题、删除到回收站/还原、学生探索设置、讨论区读取和发帖）；能力图谱=课程目标（增改删、目标标签、关联知识点）。学生端读取这六种图谱（不含教师参考），并能在问题图谱里探索作答、在讨论区发帖（都要学生本人「确认提交」）。
- 通知：发送、删除、按 UUID 补记；讨论：发帖、列表、置顶/加精及取消、教师回复、删除；课程资料：上传、列表、文件夹、移进文件夹、下载权限、删除/还原/彻底删除；成绩：读取、导出 Excel 到本机。
- 课堂活动（保存为未开始、立即开始都实测）：签到（普通/签到码）、选人、抢答、投票、主题讨论、评分、计时器、随堂练习（单选/多选/填空/判断/简答）、问卷（单选/多选/简答/判断）、分组任务（个人任务，或按分组方案分小组，可设组内/组间互评权重）、学生反馈、白板、抽签、推送课程资料、推送课件、推送教案；结束活动、活动结果。
- 课件库与教案：把课程资料里的 ppt/pptx/pdf/doc/docx 加入课件库；新建教案（可带 课前/课中/课后 等段落）。
- 教学任务：新建、发布；任务点 21 类都已实测添加：作业、考试、章节、知识点、主题讨论、分组任务、任务、仿真、视频、文档、音频、电子书、问卷、审批、测验、自定义、线下课堂、线上课堂、AI实践、签到、自测（新建自测模板：模拟测验或刷题，随机或按题型抽题）。视频/文档/音频可直接引用课程资料；问卷/审批/测验/知识点/自定义/线下线上课堂/AI实践/签到可在添加时新建（AI实践会把任务要求、角色、对话要求、评分标准一起写好）。
- 读取：课程首页（待办、作业/考试/AI实践预警、学情看板、高风险学生）、学情统计（基础数据、学情统计、学习监控、课堂报告）、教学日历、下载中心、AI 助教（是否开启、知识库设置、会话列表）。
- 学生端：我的课程/作业/考试/活动/资料/讨论/教学任务/学习记录/课程图谱（结构、关系、本人完成率和掌握率）/新版的知识列表、学习地图、问题、能力、思政图谱（问题图谱探索作答和讨论区发帖要「确认提交」）/错题集（错题只给题目和本人作答，不给正确答案），作业 22 种题型作答（暂存、确认提交；教学任务里的作业也在作业列表里），下载资料，回复讨论。活动：`open_my_activity` 告诉学生要做什么并给出自己打开的链接；随堂练习、问卷、投票、评分、分组任务、主题讨论回复可以由学生把自己的作答告诉 agent，预览后学生回复「确认提交」才写入，并按各类型的已提交信号读回核实；签到、抢答、选人、白板、抽签、学生反馈和看资料/课件/教案只给链接，由学生本人操作。教学任务：`list_my_tasks`、`list_my_task_points` 列出任务和任务点（类型、是否完成、要求）并给出任务页链接，学生自己点开学习。
- 策略层与打包：三种角色、确认提交、节流、不可信内容标注、中心辅导、预审记录；安装脚本、一键更新和回退；v0.3.0、v0.4.0、v0.5.0、v0.6.0 已发布。

**还没做（可以继续补）**
- 教师写：教师团队增删成员和权限（涉及其他真实教师，只做了读取）。
- 全景「6 张图片」类型：上传接口只收一个文件、不带类型，怎么传 6 张图没弄清。
- 新版图谱：问题图谱探索里的「关联」「知识点」两类任务（只做了「简答」）；独立于课程图谱的自定义学习地图（这门课的学习地图直接用课程图谱，编辑器的保存方式会让换了上级的知识点变成新 ID，没有做成工具）；图谱的批量导入/导出。
- AI 助教对话（只读取了设置和会话列表）。
- 错题集：读取路径已实测（按页面的参数查询，返回空列表）。用本人在测试课里的学生身份，作业答错（0 分）和考试答错（0 分，学生本人完成滑块验证后交卷）都提交了，错题集仍为空。推测平台不给课程创建者本人的学生身份收集错题；要用一个纯学生账号或章节测验再验证。有错题时的返回格式未核实。
- 「课程」(type 0)、「选课」(24) 不在课程任务的添加菜单里，没做。

**按需求不做或做不了**
- 学生考试作答、读取标准答案或测验答案（需求明确禁止；真正的考核在线下）。
- 课程设置里不开放修改：学习监控/人脸识别/抓拍（对学生的生物识别）、学生端 AI 助教机器人（开启要在弹窗里同意协议）、知识共享协议、克隆/映射/重新开课（会把课程复制给其他账号）、课程密码、课程名称（写入白名单可能按名称匹配）；班级设置里不开放：开放班级报名（会公开课程内容）。
- 刷章节任务点（看视频、读文档计时）这类代替学生学习的操作。
- 口语测评、录音（要麦克风现场录音）；直播、腾讯会议、超星会议（会真的开一场直播或会议，只记录了接口）。
- 第三方平台的任务点（3D资源=vr.chaoxing 和 sslibweb、培训班、研修、整书/章节测评、实践作业等 planType 10006–10040）和菜单里的「AI课堂」（planType 10042，棱镜 AI课堂产品，要先在那边生成课堂）：都在别的应用里，只记录了入口。
- 学生端不代做：签到（含任务里的签到）、抢答、白板、看视频/文档/电子书、AI实践对话、自测、问卷星式的表单（office.chaoxing）——只给链接。
- **重要发现**：学生任务页取任务点链接的接口 `/userStudyPlan/getToStudyUrl` 对没有链接的任务点（如自定义）会直接记为完成。所以学生工具只对「作业」任务点取链接（作业要提交才算完成），其他任务点一律只给任务页让学生自己点。
- 滑块验证码、短信、协议同意、登录：一律由本人处理。资源库（另一套登录）、3D 资源和智雅资源库（弹窗一直加载）暂时无法探查。

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
| 教学任务 | `task.chaoxing.com/task/index`（任务引擎） | `task/findTaskFolders`、`task/getTaskDataLists`、`createTask`、`taskCommit`、`saveTaskPoints`、`taskPublish` | list_teaching_tasks、create_teaching_task、publish_teaching_task | 新建（作业任务点）和发布已实测；其余 18 类任务点待做 |
| 教学活动 | `mobilelearn.chaoxing.com/page/active/activeList` | `v2/apis/active/pcActivelist`、`v2/apis/class/getClassList`、`getClassDetail`、`getTeachers`、`active/getActiveLibraryOpen`、`sign/getLastSignForXd`… | list_activities、activity_result、checkin_status、end_activity、create_activity、create_quiz_activity、create_questionnaire、create_group_task、push_material_activity、pick_student、start_quick_answer、start_vote、start_checkin、delete_activity(仅预演) | 读写已在测试班实测（见 1.2「教学活动」） |
| 资源中心 | `stat2-ans.chaoxing.com/stat2-vue/resource` | `stat2/base-data/v3/{coursewareInfo,resInfo,knowledgeInfo,workInfo,examInfo,activityLibraryInfo}`、`mooc2-ans/coursemanagev3/resource-info` | get_resource_overview、list_coursewares、list_practices、list_chapters、list_materials、upload_material、list_assignment_library、list_bank_questions、list_exams(试卷库) | 课件、题库、资料上传已覆盖；知识点、活动库待做 |
| AI助教 | `robot-lc.chaoxing.com/courseCozeV3/web` | `v1/front/conversationList`、`msgList`、`robot/info/*`、`knowledge/getAiKbSetting`… | — | 待做（读会话与知识库设置；写=对话/配置） |
| 学情统计 | `stat2-ans.chaoxing.com/stat2-vue/statistics` | `stat2/stat-nav/teach`（子菜单） | get_grades | 部分覆盖；待做：逐项统计子页 |
| 课程管理 | `mooc2-ans.chaoxing.com/mooc2-ans/tcm/course-manage` | `tcm/clazz-manage`、`tcm/clazz-student`、`tcm/change-clazz`、`tcm/getclazzgroup`、`addclazzgroup`、`changepersongroup` | open_course、list_students、create_class、move_students_class、list_class_groups、create_class_group、assign_class_group | 调班、分组已实测；待做：添加/移除学生、导出名单、班级设置 |
| 通知 | `notice.chaoxing.com/pc/course/notice/myNoticeList` | `pc/course/notice/getNoticeList` | list_notices、list_notice_inventory、publish_notice、delete_notice、reconcile_notices | 读写已实测 |
| 讨论 | `groupweb.chaoxing.com/course/topic/topicList?…bbsid` | `course/topic/{bbsid}/getTopicList`、`addTopic`、`pc/invitation/<话题>/addReplys` | list_discussions、create_discussion、delete_discussion(仅预演)、学生端 list_my_discussions / reply_my_discussion | 已修复（bbsid 取自 base-info）并实测 |
| 作业/考试（旧接口） | `mooc2-ans/work/*`、`mooc2-ans/exam/*` | — | list_assignments、submissions、list_exams、exam_marklist… | 读已验证；与"教学任务"的关系待确认 |

2026-11-06 真实只读验证通过的工具：health_check、list_courses、open_course、list_chapters、list_materials、list_notices、list_assignments、list_assignment_library、list_exams、list_activities、list_students、get_grades、list_inbox。

## 1.05 新版和旧版：接口是不是一样（2026-11-08 核对）

结论：**不用把所有功能针对新版重做一遍。** 学习通的「新版」主要是一个新的外壳和几个新应用，大部分模块里面打开的还是同一批页面、调的同一批接口；本 MCP 从一开始就是照着新版界面里实际发出的请求做的。核对方法和结果：

- **新版教师外壳的模块**（`coursemanagev3/base-info` 的 `courseNavigationListV3`，测试课实读）：教学任务 → `task.chaoxing.com/task/index`；教学活动 → `mobilelearn /page/active/activeList`；资源中心 → `stat2-vue/resource`；AI助教 → `robot-lc`；学情统计 → `stat2-vue/statistics`；课程管理 → `mooc2-ans/tcm/course-manage`；通知 → `notice.chaoxing.com /pc/course/notice`；讨论 → `groupweb /course/topic`。
- **资源中心各库**（`resource-info`）：资料库 `mooc2-ans/coursedata`、课程章节 `mooc2-ans/mycourse/tchcourse`（编辑进新章节编辑器 `ananas2`）、课程图谱 `topic-ans/knowgraph`、智能题库 `mooc2-ans/qbank/questionlist`、作业库 `mooc2-ans/work/library`、考试库 `mooc2-ans/exam/paperlist`、实践库 `mooc2-ans/ai-evaluate/v2/library`、课件库和活动库在 mobilelearn。工具调用的正是这些页面的接口（按页面核对，没有逐个接口比对）。
- **学生端**：「我学的课」里的课程链接是 `mooc1 /visit/stucoursemiddle?…&ismooc2=1&v=2`，跳到 `mooc2-ans/mycourse/stu`，和学生工具用的入口一致。
- **真正换了接口的地方**都已按新版做：新版外壳和首页（`base-info`、待办、预警）、任务引擎、学情统计（stat2）、新章节编辑器（`getcard`/`savecard` 不变，插入项和 AI 是新接口）、新版图谱（`topic-ans/knowgraph` + stat2 的问题图谱和课程目标）。
- **课程图谱逐个接口比对**：把工具用到的每个图谱接口，和新版图谱应用的全部脚本（约 220 个接口）以及新版「编辑」打开的大纲页 `coursetopic/outlinemodehead`（`outlinemode.js`、`topicPropertyEdit.js`）对照。添加、改名、删除、回收站、关系、排序、属性、显示隐藏都和新版界面用的一样。只有三处原来只在旧版框架页里用：
  - 读大纲 `questionBankTopic/knowledgepointsdata` → 已改用新版大纲页的 `coursetopic/outlinemodedata`（结构相同，多一个 `type` 区分分类/知识点），旧接口留作备用；
  - 打标签 `updatetopiclablerelation` → 已改用新版属性编辑的 `savepropertyedit`；
  - 读某个知识点关联的题目 `reltaionquestionbanklist` → 新版里没找到按知识点列题目的接口（`knowledge-v4/questionRelation` 是全课统计），暂时保留。
- **还依赖旧页面的少数地方**（旧版下线时要再看）：上面这个关联题目的读取；「开启问题/能力/课程思政图谱」用的旧设置页接口（新版「设置 → 高级设置」仍然嵌着这个页面）；「体验新版」的切换接口（本来就是从旧版切到新版）。

## 1.1 学生端入口（实测）

- 「我学的课」列表：`POST mooc2-ans/visit/courselistdata`，表单参数 `courseType=1`（0 表示我教的课），返回 HTML；每门课是一个 `div.course.learnCourse`，隐藏字段含 courseId、clazzId、curPersonId。
- 测试课「助手」同时出现在「我教的课」和「我学的课」。学生身份所在的班是「测试」班。
- 学生课程入口：`mooc1/visit/stucoursemiddle?courseid&clazzid&cpi&ismooc2=1&v=2`，会跳到 `mooc2-ans/mycourse/stu`。
- 学生端模块：AI助教（`mooc1/course-ans/ai/getStuAiWorkBench`）、任务（`mobilelearn/page/active/stuActiveList`）、章节（`mooc2-ans/mycourse/studentcourse`）、讨论（groupweb topicList）、作业（`mooc1/mooc2/work/list`）、考试（`mooc1/exam-ans/mooc2/exam/exam-list`）、资料（`mooc2-ans/coursedata/stu-datalist`）、错题集（`mooc2-ans/wrongque/page`）、学习记录（`stat2-ans/study-data/index`）、课程图谱（`stat2-ans/study-knowledge/index`）。
- 学生端活动接口：`mobilelearn/v2/apis/active/student/activelist`、`v2/apis/active/getData`。

### 学生端工具（2026-11-07，用本人在「助手」里的学生身份实测）
| 工具 | 实测结果 |
|---|---|
| `list_my_courses` | 读 mooc1 `/visit/courselistdata?courseType=1`，每个 `li.course` 带 courseid、clazzid、personid（学生 cpi）；列出 20 门 |
| `list_my_assignments` | 打开学生课程外壳（`visit/stucoursemiddle` → `mycourse/stu`），取隐藏字段 enc、workEnc、examEnc、openc、t；作业列表 `mooc1 /mooc2/work/list?courseId&classId&cpi&ut=s&t&stuenc=<enc>&enc=<workEnc>`（跨域，必须从 mooc1 页发起）；列出 2 份作业、状态和剩余时间 |
| `read_my_assignment` | 作业链接跳到 `mooc-ans/mooc2/work/dowork`；列出题号、题型、题干、选项和已暂存作答，不含参考答案（页面里本来就没有） |
| `save_my_answers` | 暂存判断题 2 道，服务端「保存成功！」，读回 true/false。2026-11-07 第二轮：在 23 种题型的作业里暂存 22 种（口语测评要现场录音，明确拒绝），逐题读回全部有值 |
| `submit_my_assignment` | 预演后必须带 `confirm_text="确认提交"` 和 plan_id；提交后作业列表状态从「未交」变为「已完成」；含主观题的全题型作业提交后为「待批阅」 |
| `list_my_exams` | 考试列表 `mooc1 /exam-ans/mooc2/exam/exam-list?courseid&clazzid&cpi&ut=s&t&stuenc=<enc>&enc=<examEnc>&openc`；每项 `goTest(courseId, examId, …, 截止时间, paperId, …)`。**只读，不代答考试**（按需求「真正的考核在线下」） |
| `list_my_activities` | `mobilelearn /v2/apis/active/student/activelist?fid&courseId&classId&showNotStartedActive=0`，activeType 2 签到、45 通知等，status 1 进行中、2 已结束，userStatus 1 已参与 |
| `list_my_materials` / `download_my_material` | 资料 `mooc2-ans /coursedata/stu-datalist?…&stuenc`，每项 `ul.dataBody_td` 带 objectid、isdown（教师是否允许下载）；下载地址来自 `mooc1 /ananas/status/<objectid>` 的 `download`（cldisk 签名链接，不需要登录态）；下载 55 B 测试文件，大小与服务器记录一致 |
| `list_my_discussions` / `reply_my_discussion` | 学生外壳隐藏字段 `bbsid`；回复是 `POST groupweb /pc/invitation/<话题uuid>/addReplys`（courseId、classId、replyId、uuid、topic_content=encodeURIComponent 一次后再表单编码、anonymous、urlToken=话题页 window.obj.urlToken、bbsid）；回复后话题页显示原文，中文正常 |

- 作答表单 `form#submitForm` 提交到 `/mooc-ans/work/addStudentWorkNewWeb?…`（地址里带页面签名 token）。字段：courseId、classId、cpi、workRelationId、workAnswerId、standardEnc、enc_work、totalQuestionNum、workTimesEnc、`answertype<题目ID>`、`answer<题目ID>`，以及 `answerwqbid`（`#questionIds`）。
- 作答值：单选是选项的 data（A），多选是拼起来的字母（AC），判断是 true/false，主观题是 HTML。
- 暂存：地址加 `&pyFlag=1&ua=pc&formType=post&saveStatus=1&version=1`，表单里 pyFlag=1；提交：地址同上但不带 pyFlag，表单 pyFlag 为空。
- **`answerwqbid` 必须填全部题目 ID 加逗号**（页面自己保存前才填），留空服务端返回「无效的参数：code-1」。
- 页面只在真实界面改动后才弹「离开页面」提示（`isContentChanged`）；脚本直接写隐藏字段不会触发，保存后也会复位。
- 各题型的作答字段（2026-11-07 全题型实测）：
  - 单选、判断：`answer<id>` = 选项的 data（A / true / false）；多选、测评：字母拼接（AC）；排序：`DBAC`。
  - 填空、分录：每空一个 `answerEditor<id><序号>`（UEditor 的 textarea，HTML）。
  - 简答、名词解释、论述、计算、其它、口语：`answer<id>` 是 UEditor 的 textarea（HTML）；写作：隐藏的 `name=answer<id>` 是纯文本，`id=answer<id>` 的 textarea 只是编辑器。
  - 连线：`[{"name":"1","content":"B"},…]`（name 是字符串）；共用选项、选词填空：`[{"name":1,"content":"B"},…]`（name 是数字）；钟表：`[{"hour":"9","minute":"30"}]`。
  - 完型填空：每空 `answer<id><小题uuid>` = 字母，`answer<id>` = `[{"<uuid>":{"answer":"B"},…}]`。
  - 阅读理解、听力：`.readingItem<id>` 每项带 data=小题字段名、itemId、qtype；`answer<id>` = `[{"<itemId>":{"type":0,"answer":"A"}, "<itemId>":{"type":3,"answer":true}, …}]`，填空小题的 answer 是 `[{content,name}]`，简答小题是 HTML。
  - 程序：`answer<id>` = `[{"language":22,"answer":"<pre…><code…>代码</code></pre>","answerTxt":"转义后的代码"}]`，语言在 `languageSelect<id>`。
  - 口语测评要麦克风现场录音，明确拒绝代答。

## 1.15 已做成 MCP 工具并在测试课实测通过的写操作（2026-11-06）

每个工具都走同一套流程：写入白名单 → 预演并签发 plan_id → 确认后执行 → 回读核实。核实不通过时返回 `write_outcome: unknown`，并提示不要重复提交。

| 工具 | 实测结果 |
|---|---|
| `read_chapter_content` | 列出各页签、正文 HTML、已插入的模块（正文按数据返回，不当作指令） |
| `rename_chapter` | 改名后列表核对一致 |
| `save_chapter_content` | 新建一页，读回逐字一致。HTML 经白名单清洗：`<script>`、`onclick`、`javascript:` 被去掉，楷体等格式保留。已有插入项的页拒绝覆盖 |
| `insert_chapter_link` | 插入后读回能找到对应任务点。2026-11-07 起可插入到已有任意插入项的页（见下） |
| `insert_chapter_note` / `insert_chapter_discussion` / `insert_chapter_reading` / `insert_chapter_quiz` | 2026-11-07：往已有 12 个插入项（文件、速课、视频、扩展阅读、文档、测验、音频、投票、附件、讨论、链接、图片）的页里依次插入链接、注释、讨论（任务点、最少 10 字）、扩展阅读、章节测验（引用作业库作业），读回 12 → 16 项，原有项一个不少；学生视角预览页 15 个模块全部正常加载 |
| `upload_material` | 2026-11-07：改为可执行。预演记录文件 SHA-256 并绑定到 plan；确认时把文件复制成私有快照，哈希必须与预演一致；页面里再算一次暂存字节的哈希，一致才上传。上传 55 B 文本，资料列表核对到新条目 |
| `insert_chapter_file` | 2026-11-07：文档（PDF，自动取页数）、音频、视频、图片（正文内）、附件各插入一次，读回 1 → 6 项；学生视角预览里 PDF 阅读器、音频、视频播放器、附件、图片（64×64 已加载）全部正常 |
| `create_teaching_task` / `publish_teaching_task` | 2026-11-07：新建教学任务（名称、简介、起止时间、把作业库作业加为任务点），读回名称和任务点数一致；发布到「测试」班，任务列表显示已发布 |
| `create_answer_card_assignment` | 2026-11-07：建 5 题答题卡作业（单选、多选、填空 2 空、判断、简答），答案逐题 `save-answer`，作业库核对 5 题 |
| `add_question_to_bank` | 2026-11-07：24 种题型都建成功，返回题目 ID（现在是 32 位十六进制，早先是数字）。同一文件夹里已有相同题目时，服务端拒绝并说明，工具如实返回「没有新建」 |
| `list_bank_questions` | 2026-11-07：只读，`POST qbank/search`，按关键词、分页列出题型、题干摘要、难度、使用量、文件夹、创建时间、题目 ID。**不返回答案和解析** |
| `create_discussion` | 发帖成功，按服务端返回的 `topicId` 核实，中文正常 |
| `start_checkin` | 普通签到发起成功，30 分钟，新活动核实到；手势、位置、二维码签到仍只支持预演 |
| `create_class` | 新建班级并核实（测试班级已删除） |
| `publish_assignment` | 作业库作业发放到指定班级，可带发放设置；作业列表核实到新发放记录 |
| `reconcile_notices` | 按 UUID 补记结果未明的通知 |
| `create_assignment` | 2026-11-07：一份作业建 23 种题型（自定义评分），作业库核对 23 题，逐题读回题干和答案一致。链路见下文「题型」 |
| `create_exam` | 2026-11-07：一份试卷建 22 种题型（含选做题），试卷库核对 22 题、总分 120，逐题读回答案一致 |
| `publish_exam` | 2026-11-07：发给「测试」班，40 分钟，题目乱序，核实到新考试。`POST exam/test/publish`，设置项按白名单开放 |

三个出题工具共用 `questions.py`：输入纯文本，按题型校验后转成各编辑器的请求，HTML 一律转义。分值显式填 0 会被拒绝，不会被悄悄改成默认 5 分。同一题型的第二道题沿用该题型已有的分组（作业 `relationid`、试卷 `paperLibraryRelationId`），不会每题建一个新分组。`on()` 打开静态基准页时跳过就绪检查（曾经遇到 frame not responding）。

实测中发现并修好的问题：
- 讨论区的 `urlToken` 在 `window.obj.urlToken` 里，而且**每次加载页面都会换**，必须在发帖的那个页面上取。
- 发帖时，网页会先把 `topicTitle`、`topicContent`、`rtf_content` 各做一次 `encodeURIComponent`，再整体按表单编码，服务端多解码一次。只编码一次的话，中文会存成「?」。
- 服务端会自己生成话题 uuid，请求里的 `?uuid=` 只是客户端请求号，要按返回的 `objs.topicId` 核实。
- 讨论页这类大页面拿不到完整的页面观察。所以只需要调接口的导航加了 `readiness=False`，跳过就绪检查。
- 删除班级后立刻读班级列表，可能短暂返回空列表。`ctx` 不再猜一个默认班级，读不到就报错。

## 1.2 已实际执行过的写流程（测试课「助手」，2026-11-06）

### 教学任务（任务引擎 task.chaoxing.com）
1. 新建：`GET /task/createTask?encryptedCourseId&encryptedType&businessCode&folderId`，参数来自 `task/index` 页面内联脚本里的常量。返回 `encryTaskId`、`backToken`、`decryptCourseId`，然后跳到 `/task/newTaskToList?encryptedCourseId&encryTaskId&token`。
2. 基础信息：`POST /task/taskCommit`，JSON 字段包括 `taskId`（加密）、`name`（≤100 字）、`cover`、`startDate`、`endDate`、`introduce`/`introduceRichText`、`selectedModes`（默认 `["list"]`）、`labelList`、`courseId`、`schoolId`、`publishStatus` 等。切到「任务设计」标签时页面会自动提交一次。
3. 添加任务点：「添加」菜单共 19 类，外加「自定义」：
   - 学习内容：视频、音频、文档、章节、知识点、电子书、3D资源
   - 教学活动：线下课堂、线上课堂、主题讨论、分组任务、AI课堂
   - 练习评估：作业、测验、自测、AI实践
   - 其他：问卷、审批、签到

   已验证「作业」（type=4），从本课作业库选择，也可在弹窗里「新建」：
   `POST /homework/getMoocData`（列出作业库）→ `POST /homework/checkAddition [{name,courseId,workLibraryId}]` → `POST /homework/cloneCourseHomework?moocCourseId&encryTaskId [{workLibraryId,score,questionNum,workType,...}]` → `POST /taskPoint/saveTaskPoints {taskPoints:[{type:4,externalDataId:workLibraryId,name,fkTaskId,fkGroupId,courseId,workType,shareType:0,...}]}`。
4. 发布：`GET /peTaskPlan/taskPointCheckPublish` → `POST /taskReference/coursePublishAuthentication` → `POST /taskReference/couresPublishInitData`（返回各班 token）→ `POST /taskReference/taskPublish {encryTaskId, coursePublishParam:[{classId,className,publishtype:0,token}]}`。弹窗里可选班级，也可搜索具体学生。
5. 任务设置：展示样式 16 种（列表、卡片、框架、图谱、藏宝图、3D小岛等）、封面模版、报名开关、证书开关、任务目标（≤200 字）、管理权限；任务设计里还有「达标标准」「组间闯关设置」和分组。
6. 列表项字段：`taskId`（加密）、`name`、`publishStatus`、`taskPointsNumber`、`taskStudentsNumber`、`startDateStr`/`endDateStr`、`labelList`、`isCreator` 等。
6.5 **2026-11-07 接口版（做成工具）**：
   - `task/index?courseId&type=course` 的内联脚本里有 `encryptedCourseId`、`encryptedType` 两个常量（不需要外壳的 enc）。
   - `GET /task/createTask` → `GET /task/newTaskToList?…&token`（打开草稿）→ `GET /task/onMountGetTaskData?taskId=<加密ID>`：`groups[0].id` 是默认分组，`groups[0].fkTaskId` 是数字任务 ID。
   - `POST /task/taskCommit` 是 JSON，最少 `{taskId, name}` 就能保存；**`startDate`、`endDate` 必须是毫秒时间戳**，传「2026-11-07 08:00」这类字符串会 400（Failed to read request）。
   - 作业任务点：`POST /homework/getMoocData {page,pageSize,searchKey,moocCourseId,isCheckedExist:"1"}`（本课作业）→ `POST /homework/checkAddition [{name,courseId,workLibraryId}]` → `POST /taskPoint/saveTaskPoints {taskPoints:[{imageUrl,name,exist,externalDataId:workLibraryId,workType,localDataId:id,desc,courseId,fkGroupId,type:4,fkTaskId,shareType:0}]}`。只有跨课复制才需要 `cloneCourseHomework`。
   - 发布：`GET /peTaskPlan/taskPointCheckPublish?encryptedTaskId` → `POST /taskReference/coursePublishAuthentication {encryTaskId,courseId}` 返回选班插件地址 `mooc2-ans/exam/test/publish-plugin?courseid&cpi`；插件页每个 `.classitem` 带 `data=班级ID`、`data-token`（32 位）→ `POST /taskReference/taskPublish {encryTaskId, coursePublishParam:[{classId:数字,className,publishtype:0,token}], taskPublishParam:null}`（课程任务 taskPublishParam 为 null）。`couresPublishInitData` 只返回已选对象，新任务是空数组。
6.6 **2026-11-07 全部任务点类型（做成工具 `list_task_point_options` / `add_task_points`）**：每类任务点的「添加」弹窗各自拉一个列表，选中后按 `addTaskPointsSubmit` 里的规则拼成条目，统一 `POST /taskPoint/saveTaskPoints {taskPoints:[…, fkGroupId, type, fkTaskId, shareType:0]}`；工具用任务的 `taskPointsNumber` 前后对比核实。

   | 类型 | type | 列表接口（POST JSON） | 取哪个 ID | 实测 |
   |---|---|---|---|---|
   | 作业 | 4 | `/homework/getMoocData`（先 `/homework/checkAddition`） | workLibraryId | ✅ |
   | 考试 | 5 | `/exam/getMoocData`（先 `/exam/checkAddition`） | paperId，另带 paperType | ✅ |
   | 章节 | 8 | `/taskChapter/getData`（树） | id | ✅ |
   | 主题讨论 | 14 | `/discuss/getData` | uuid（名称字段 title） | ✅ |
   | 分组任务 | 18 | `/groupTask/getData` | activeId（名称字段 activeName） | ✅ |
   | 任务 | 16 | `/taskTypeTaskPoints/getData` | taskId | ✅ |
   | 仿真 | 19 | `/simulation/getData` | simulationId，另带 simulationUrl | ✅ |
   | 文档 / 视频 / 音频 | 11 / 10 / 22 | `/document/getData`、`/video/getData`、`/audio/getData` | documentId / videoId / audioId | ✅ |
   | 知识点 | 1 | `/knowledgePoints/getMoocData`，库 `/knowledgePoints/getData` | knowledgePointsId | ✅（新建） |
   | AI实践 | 15 | `/aiCoach/getMoocData`，库 `/aiCoach/getData` | relationUuid | ✅（新建并写好要求） |
   | 问卷 / 审批 | 6 / 7 | `/questionnaire/getData`、`/examineAndApprove/getData` | questionnaireId / examineAndApproveId | ✅（新建） |
   | 测验 | 13 | `/quizTest/getData` | categoryId | ✅（新建） |
   | 自定义 | 9 | `/customizeTaskPoints/getData` | uuid | ✅（新建，含类型） |
   | 线下 / 线上课堂 | 2 / 3 | `/offlineClassroom/getData`、`/onlineClassroom/getData` | offlineClassroomId / onlineClassroomId | ✅（新建） |
   | 电子书 | 21 | `/eBook/getData`（按关键词） | dxid | ✅ |
   | 签到 | 23 | 无库，`/signIn/addOrEdit` 为任务新建 | id | ✅ |

   - 列表参数统一为 `{page, pageSize, searchKey, currTaskId:数字任务ID, currentGroupId, moocCourseId}`。
   - 文档/视频/音频可以直接用课程资料里的云盘文件：`POST /document/addOrEdit {name(去扩展名), objectId, suffix, cover, source}` 返回条目（含 documentId），再存任务点。同一个文件再加到同一任务会被去重，服务端回「任务点个数为空」。
   - 不在课程任务菜单里：课程（0）、选课（24）。第三方：3D资源（planType 10021）、AI课堂（10042）等走 `/taskPointsThirdPartyDocking/getPageUrl`，打开的是别的平台。自测（17）要课程先开启自测功能。
7. 接口目录（从页面脚本提取）：`createTask`、`createOrEditTask`、`deleteTaskInfo`、`taskDelete`、`swapTaskOrder`、`taskMoveToFolder`、`addNewFolder`、`reNameFolderConfirm`、`removeFolderConfirm`、`exportTask`、`getCourseImportTasks`/`confirmCourseImport`、`confirmCourseCopyTask`、`tasklabel/getTaskLabelDatas`/`saveOrDeleteTaskLabelData`、`commitPeTaskBaseInfo`、`taskStatistics/index`、`taskReference/getCourseIdClazz`。

### 2026-11-07 班级分组、课件/教案、学生端活动与任务（做成工具，测试课实测）

- **调班**：`GET /mooc2-ans/tcm/change-clazz?courseId&oldClazzId&newClazzId&personIds&cpi`；名单 `tcm/clazz-student`（行里带 personId）。工具 `move_students_class` 预演列出学生，确认后按两个班的名单核实。
- **分组**：小组列表 `tcm/getclazzgroup`（HTML，`#group_<id>`）、新建 `tcm/addclazzgroup`、分人 `tcm/changepersongroup`；方案 `mobilelearn /v2/apis/task/getMoocGroupPlanList`（id 0 = 班级默认方案）、`getOneMoocGroupPlan`（小组和人数）。分组任务按方案分组时 `groupType=1`、`groupNum`=小组数、`maxStuNumOneGroup`=最大组人数，开始前调 `/widget/renwu/checkgroup`（status 1 才发起）。
- **课件库**：`/page/ppt/coursewareList`；`POST /widget/teachingPlan/createPPT {courseId, parentFolderId, pptData:[{suffix, objectId, name, size}]}`（云盘文件，接受 ppt/pptx/pdf/doc/docx）。**教案库**：`/page/ppt/teachingPlanList`；`GET /v2/apis/activePlan/addTeachingPlan {courseId, planMouldId(-1 空白/-2 标准), parentFolderId, title}`，段落 `addPlanContent {planId, groupName, groupContent}`、删除 `delPlanContent`，读回 `getPlanInfo`。推送到班级都走 `POST /v2/apis/active/createTeachPlanActive {classId, courseId, teachPlanData:[列表行]}`（教案活动 type 60，PDF 课件 62）。
- **任务点更正与补全**：type 15 是菜单里的「AI实践」（打开 ai-evaluate 编辑器），不是 AI课堂；新建的 AI实践要在 `/mooc2-ans/ai-evaluate/v2/editor/save {courseid, cpi, libraryUuid, isPublish:false, data:JSON(form)}` 写好 `requirement`、`sceneChat.aiCharacter/userCharacter/chatPrompt/scoreStandards`，否则加任务点会被拒「【要求】不能为空」。
  电子书 type 21：`/eBook/getData` 按关键词搜，`unitid` 用弹窗的 7719（不能用行里的 null，否则「该书籍暂不支持在线学习」）。签到 type 23：`POST /signIn/addOrEdit {taskId:加密任务ID, courseId, name, cover, describe}`，任务需已发布。
  问卷/审批/测验/知识点/AI实践/线下课堂/线上课堂/自定义的库条目都用 `/<类型>/addOrEdit {name, cover, describe[, startDate, endDate, courseId]}` 新建；自定义要先有类型（`/customType/addOrEditCheck` + `addOrEdit`，名称≤4字）。
- **学生端活动**（学生活动列表 `/page/active/stuActiveList` 的打开逻辑）：随堂练习 `quizDetail2` → `POST JSON /v2/apis/studentQuestion/doQuestionAnswering`（questionList 里填 personAnswer：单多选 myoption、判断用选项名 1/2、填空 blankAnswer、简答 content）；问卷 `quizDetail` → `POST /v2/apis/studentQuestion/doQuestion`（`questionId` 每题一个，`answer<题ID>` 多选重复）；投票 `POST /v2/apis/qvote/doQuestion {questionId, answer}`；评分 `POST /v2/apis/score/stuSubmitAnswer {score, scoreList, content}`；分组任务 `getMyGroupInfo` 取 groupId/editVersion → `POST /widget/apis/renwu/studentSaveRenwu`；活动讨论在班级讨论区（`getTopicDiscussInfo.topicV3Url`，话题 uuid 以 `_topicDiscuss` 结尾），回复同普通讨论 `addReplys`。
  学生端答题数据里没有参考答案（`rightAnswer` 为 null）。活动列表的 `userStatus` 对所有活动都是 1，不能当「已参与」；已提交信号：随堂练习/问卷/投票看 `pptUserAttend` 是否为空，评分看 `getStuScoreStatus.userStatus`，分组任务看 `getMyGroupInfo.commitLogCount`，讨论看话题回复数。
- **学生端教学任务**：`task.chaoxing.com/api/v1/userStudyApi/getMyTaskUrl` → `POST JSON /userStudyTask/getData {page, pageSize, courseId, moocClassId}`（明文 ID）→ `/userStudyPlan/getGroupData`、`getPlanDataByGroupId`（任务点名称、类型、是否完成、可学条件）；任务页 `/userStudyPlan/myPlanList?encryTaskUserId`。

### 2026-11-08 课程与班级管理、回收站、题库管理、读取页面（做成工具，测试课实测）

- **课程设置**：读 `GET mooc2-ans /tcm/getcoursesetting?courseid&cpi`（HTML，每个开关的 `checked` 就是已保存状态）。每个开关单独保存（GET，courseSet.js）：`updatecourseselftest{selftest}`、`updatevideowatermark`、`updatecoursecommitment`、`coursemanage/setsynactivestate`（读 `getsynactivestate`）、`visit/updatesmarkcourse{state}`、`updateQueImportAllowCreateTopic`、`updateAiQuestionExplain`、`setaivideointerpret`、`updateaiassistant{2|-1}`、`updateportalShowAiAssistant`、`updateallowdownload`、`updateHiddenResourcesName`、`updateteacherreview`、`updateisprivately{0 试读全部,1 关闭,3 第一章,2 前三章}`、`updateportaldefaultcolumn{1,2,3}`、`updatecoursestar{1 关闭,0 所有人,2 本课学生}`、`updatesendnoticetype`（五个字段一起发）、`savecoursecommitment`、`POST updatecoursedata`（课程说明、英文名称，其余字段按原值回填）。实测每项改了再改回，读回一致。
- **自测任务点**：任务引擎 `/selfTest/isOpenSelfTest`、`/selfTest/addSelfTestUrl` 给出 mooc2-ans 弹窗 `self-test/template/create-pop?courseid&clazzid=0&type=2`；`POST /mooc2-ans/self-test/template/save {title, type(0 模拟测验/1 刷题), templateType:2, limitTime, randomNum, questionFrom(0 题库/1 错题集), randomType(0 随机/2 按题型), randomTypeSet}` 返回 `{id,title}`；读回用 `create-pop?…&templateid=<id>` 的隐藏字段；任务点 `{type:17, name:title, externalDataId:id, courseId}`。题量来自 `template/question-count`、`template/type-question`。
- **回收站**：作业 `work/delete?…&recycle=1`（0 还原），回收站 `work/list?…&recycle=1`；考试 `exam/test/delete-test?…&recyle=1`（0 还原），回收站 `exam/test?…&recyle=1`；试卷 `POST exam/deletepaper?…&status=2`（0 还原，1 彻底删除；回收站行里没有 `.removeBtn` 时平台不允许彻底删除，服务端却仍回「操作成功」），回收站 `paperlist?…&type=1`；资料 `POST coursedata/batchDelete`，回收站 `coursedata/recycle-data-list`，还原 `recycle-data`，彻底删除 `delete-recycle-data`。删除只有在「目标离开列表、其他条目都还在、回收站里有它」时才算成功。
- **考试列表只显示 clazzid 指定的那个班**：读考试（含回收站）要逐班读，否则会漏掉其他班的考试。
- **修改已发布作业/考试**：作业「修改设置」页 `work/rePublishSetting?courseid&classid=0&cpi&id`，页面自己的 `rePublicWork()` 收集四十多项设置后 `POST work/library/update-publish`；考试 `exam/test/topublishsettings?clazzid&courseid&cpi&id`，`updatepublish(true)`（true 跳过页面内「时间已改」确认）→ `POST exam/test/update-publishsettings`。工具打开页面、改时间字段、调用页面函数并截获响应，屏蔽它保存后的 `window.close()`。**时间字段必须带秒（yyyy-MM-dd HH:mm:ss）**，不带秒时截止时间被存成空。
- **催交**：批阅页 `work/mark` 的「督促」是 `GET work/urge {courseid, clazzid, cpi, workid, studentIds}`，可以只发给指定学生（另有 `whole=true` 全体）。工具在预演时锁定收件人，确认时名单变了就不发。实测只发给本人，收件箱收到「作业督促通知」。
- **讨论**：置顶 `/pc/topic/{uuid}/{set|cancel}/top`、加精 `/pc/topic/{uuid}/{set|cancel}/choice`，置顶状态读 `getTopTopicList`，加精读 `getTopicList` 的 `choice`；教师回复同 `addReplys`，`urlToken` 从回复页 HTML 里取（回复页会重绘，不能在上面执行脚本），话题回复数要过几秒才更新，以服务端回显的回复内容为准。
- **资料**：新建文件夹 `GET coursedata/add-folder`（名称里的 `[]` 等特殊字符被去掉），下载权限 `POST update-isDownload`，移动 `POST coursedata/move {dataId:"id--", folderId}`，文件夹内容 `coursedata?…&dataId=<文件夹>`。
- **成绩导出**：`POST stat2 /stat2/score-data/getEnc` 取 `exportEnc`，再把页面的表单提交到 `fystat-ans /api/export {courseId, classId, exportEnc, createId, seltables:6}`，用 `bsk download` 接住下载，文件以 `PK` 开头（xlsx）。超过 2000 人走下载中心，工具不处理。
- **班级**：设置读 `tcm/getclazzsetting`（按 onclick 函数名认开关），写 `update-enableinvitecode`、`coursemanage/intoclazzvalidation`、`update-clazzretire`、`update-videoctrl`、`updatehideclazz`、`update-clazzstate`、`update-stunumlimit`，改名 `update-clazzname`；移出学生 `delete-clazzstu{personIds}`，退课日志 `tcm/drop-clazz-log`（必须按班读，「全部班级」返回空；记录 ID 在「恢复」按钮的 data 上），恢复 `tcm/recoverystudy{personDropIds}`；从本课另一班添加 `addstubyclazz{addClazzId}`；加班日志 `coursemanage/stuaddclazzlog`（表格）。实测只用了教师本人加进测试课的测试账号和教师自己的学生身份，学生在其他班的身份不受影响。
- **成绩权重**：`tcm/scoreweightdata?courseId&clazzId&cpi` 里的 `#weightForm`（字段 video、ceyan、work、test、aiEvaluate、pbl、attend、active、bbs…），保存 `POST /mooc2-ans/tcm/setWeights?<表单> {customWeightJson, classIdStr}`，另带 `attendAttendance`、`bbsLimit/bbsReplyLimit/bbsPraiseLimit`、`aiEvaluateType`。
- **题库管理**：列表 `POST qbank/search`（每页最多 100 行；文件夹自己的列表只含本层，按关键词搜索才跨文件夹）；回收站是另一个接口 `POST qbank/recycle-search`（行在 `list`）；新建文件夹 `GET insertdir`；移动 `POST update-pid {operateId, type:1, newPid}`；删除/还原 `POST batch-updatestatus {questionIds, status:2|0}`；难度 `POST update-difficulty {qids, difficulty:0.8/0.5/0.2}`；标签 `question-label/add|list|delete`，`list?qid` 的 `checkedIds` 是这道题已打的标签，打标签 `POST update-label?…&labelIds=a,b, {qids}`；修改题目 = 新建表单带 `questionBankId=<id>`、`isEdit=true`。
- **章节**：`POST mooc-ans/edit/chaptermove {courseid, nodeid, pnodeid}`（移到某章下），`POST movechapter/drag {courseid, nodeid, destid, position:before|after|append}`（排序；非一级不能变一级），`POST importdirForText {courseId, text}`（每级缩进**两个空格**），删除 `deletechapter`。
- **随机组卷**：`POST exam/reVersionToSetPaperStructureV2`（`autoPaperParamData` 的字段：每种题型 `<t>_radio=0`（从题库选题）、`<t>_score`、`<t>_totalNum`、`<t>_libraryInputQuestionNum` 等，`typeOrders`、`pageNum`、`title`、`score`）返回 `taskId`，轮询 `exam/autopapertask-status` 到 `taskStatus=ok` 得到 `paperId`。试卷库对随机卷的题量显示「---」。
- **读取页面**：首页待办 `fanya3/t/todoList`、作业预警 `work/teaching-alert`、考试提醒 `exam/test/exam-progress-reminder`、AI实践预警 `teaching-alert/stat/ai-evaluate`、学情看板 `stat2/ai-study-alert/v3/board|high-risk`；学情统计 `stat2/base-data/v3/*`、`stat2/teach-data/*`、`stat2/study-monitor/v2/studyList`、课堂报告 `mobilelearn v2/apis/course/getReportData`；教学日历 `course/calendar/list` + `schedule/list`；AI 助教入口 `goWorkbench` 返回的页面里有 `courseRobotId`，`robot-lc /v1/front/robot/info/<id>`、`knowledge/getAiKbSetting`、`conversationList` 不签名也能读。
- **学生端**：学习记录 `stat2 /study-data/index`（隐藏字段 `pEnc`）→ `/stat2/study-data/{job,sign,point,score,work,test,nearTask,behindTask,self-exam}`，**这些接口没有学习记录页作为 Referer 时回 403**；错题集 `POST mooc2-ans /wrongque/data`（HTML）。

### 2026-11-08（第二轮）平行试卷、学生写操作统一确认
- **学生端写操作**：暂存作答、回复讨论也改为必须带学生本人的 `confirm_text="确认提交"`。注册时检查：学生端写操作没有 `confirm_text` 参数就拒绝注册；确认语不对时 plan 作废，必须重新预演。
- **平行试卷**（`get_parallel_paper` / `create_parallel_paper` / `update_parallel_paper`，发布、删除、还原沿用 `publish_exam`、`delete_exam_paper`、`restore_deleted`）：
  - 新建：`GET exam/createAnEmptyPaper?…&parallelpaper=1` → `POST update-exampaper-title` → `POST exam/complete-choose-paper?courseid&clazzid&cpi&paperid {selectedPaperData:[{pid,cid}]}`（把试卷库里的试卷**复制**成子卷，原卷不变）→ 轮询 `GET exam/choose-paper-status` 到 `taskStatus=success` → `GET exam/create-parallel-paper?…&easy=0|1|2`（易/中/难）。
  - **复制是后台任务**：任务还在跑时就「完成创建」，服务端照样回「创建成功」，但只包含已经复制好的子卷。所以必须等任务完成。
  - 子卷结构不一致时，完成创建返回 `status:false`「各子卷类型、题型、题量、分值需保持一致」，但试卷库里仍显示「平行试卷: N套」、没有「未完成」标记。工具在预演时先用 `exam/lookpaper` 的 `.title` 标题（「一、 单选题（共1题，5分）」）逐份比对结构，不一致直接拒绝。
  - 移除子卷 `GET exam/delete-childpaper?courseid&paperid=<子卷>&cpi`，立即生效。编辑页 `exam/parallel-paper` 的 `.testPrallelBody_td` 行：标题、子卷 ID（`.rename_yes[paperid]`）、结构「单选题 1，题型分值：5.0，…」、题量、分值；隐藏字段 `serialNumberMode`、`questionGroup`、`examPaperOldTitle`，难度在 `#selectBox p span[value]`。
  - 改标题时 `randomPaperRenameSync=1` 把子卷改名为「标题(1)」「标题(2)」…；序号 `POST update-exampaper-serialnumber {serialnumber:0 连续|1 按题型}`，归类 `POST update-exampaper-questiongroup {questionGroup:0 归类|1 不归类}`（不归类时只能连续编号）。
  - 试卷库行：`paperLibLookPaper(类型, id, '1')` 的第三个参数为 1 表示平行试卷，`.random`「平行试卷: N套」，`.incomplete`「[未完成]」；`list_exams(include_papers=true)` 现在带 `parallel`、`unfinished`、`published`（发放次数）。
  - 实测：两份结构相同的测试卷建成平行试卷（难度中）→ 移除一套并改难度、序号 → 加回一套、改标题并同步子卷、改归类 → 发布给测试班（考试列表出现，发放次数 1）→ 删除考试 → 删除平行试卷进回收站 → 还原后两套子卷都在。混入结构不同的试卷在预演就被拒绝。
- **题库导入**（`import_bank_questions` / `import_bank_file` / `smart_import_bank_text`）：
  - 模板导入（列表页「批量导入」，insertTemplate.js）：`POST https://mooc1.chaoxing.com/import-export-ans/import/importquestions?courseId&cpi`（.xls/.xlsx；.ti 用 `import/importquestion-que`），multipart `file`、`pid`（目标文件夹）、`enc`（列表页 `#importQuestionEnc`）、`uuid`、`pMessage`、`status`（`#initStatus`）、`updateSameQue`、`plainText`（1 = 单元格按纯文本，`<b>` 原样保存）、`.ti` 另有 `importDir`。从 mooc2-ans 页面跨域带 Cookie 发送即可。返回 `totalNum`、`insertSuccessNum`、`insertFailedNum/Content`、`ignoreNum/Content`（与题库已有题**内容完全相同**的跳过，按行号列出）、`qidList`（Excel 有，.ti 没有）。
  - 模板 `import-export-ans/template/importQuestionTemplateNew.xls`（v2）：表头 目录、题目类型、自定义题型、大题题干、小题题型、小题题干、正确答案、答案解析、难易度、知识点、标签、选项数、选项A…；组合题的小题各占一行；判断题选项固定「正确/错误」答案 A/B；简答类答案写在选项A、正确答案填 A；连线题选项数写「4+4」，答案按左侧顺序写右侧字母；共用选项题小题行只有小题题干和答案；选做题的选项数列是「任选几题」；目录列「/一级/二级」不存在时自动新建。工具用自带的 xlsx 生成器（`xlsx.py`，不依赖第三方包）按这个格式生成文件，表头带到选项Z，实测 5+5 的连线题（10 列选项）也能导入。
  - 实测：14 种题型（单选、多选、填空、判断、简答、名词解释、论述、分录、连线、排序、完型填空、阅读理解、共用选项、选做）全部导入，导出成 Excel 读回，答案、选项、难度、目录逐项一致；重复导入时平台按「内容相同」跳过，改过内容的题即使 `update_same=true` 也作为新题导入；.ti 文件导入后用导入前后的题库对比找出新题。
  - 智能导入（`qbank/smartimport`）：编辑区文本每行包成 `<p>` 后 `POST /sqp/api/parse?courseid&cpi {html, isParseLatexCode, isParseLatexFormula}` 返回 `paper`（每题 `type` QuestionChoice/MultiChoice/QuestionGapFilling/QuestionYesNo/QuestionCommon/QuestionComposite…、`lines[].notMatch`），页面的 `makeupPaper` 转成 `qjson` 后 `POST import-export-ans/import/import-question {courseId, pid, enc, insertQuestion, qjson, …}`。这个页面会不停重绘（BrowserSkill 拒绝在上面执行脚本），所以工具在静态基础页上调接口，`makeupQ` 移植成 Python。页面在客观题缺答案时不允许加入题库，工具在预演时同样拒绝。预演绑定识别结果的哈希，确认时重新识别，不一致就不导入。
- **题库导出**补全格式：`export-questions?exportType=excel|word|pdf|ti`，选中题目时同步返回文件；Excel、Word 是老格式（OLE2，.xls/.doc），PDF 以 `%PDF` 开头，Ti 以 `{"time"` 开头。
- `list_bank_questions` 原来的 `folder` 字段其实是题干（`dirName` 对题目行放的是内容），改为 `folder_id`。
- **章节插入第二轮**（`search_chapter_resources`、`insert_chapter_suke` / `_book` / `_book_page` / `_panorama` / `_vote`、`insert_chapter_file(kind=动画)`、`import_chapter_document`、`ai_format_chapter`）。接口都从章节编辑器的 `ananas2/assets/Home-*.js` 里读出，读接口都在 mooc1 上（编辑器自己的域）：
  - 速课：`GET /suke/sukeList?lastId&pageSize=20`（`data.list`，按 `lastId` 翻页；pageSize 大了会失败）；模块 `insertmicroCourse {url, title, cover, mid, _jobid, jobid}`。
  - 图书：`GET /ananas/book/query/<关键词>/<页>`（`result[]` 带 dxid、bookname、author、publisher、publishdate、readurl、pdgurl、coverurl、size、isshidu）；模块 `insertbook {readurl, pdgurl, coverurl, bookname, author, publisher, publishdate, size(试读书为1), mid, _jobid, jobid, ywbf:"1", start:1}`，带任务点。
  - 图书内页：`GET /ananas/chapter/query/<关键词>/<页>`；插入的是正文里的行内链接（ProseMirror 标记 chapterLink）：`<a id class="chapterLink" type="text" linktype="0" href _href address title target desc data tips>`。
  - 全景：`mobile3.chaoxing.com/fyportal/threedresourse/panorama/list`（只能同源读，编辑器用 iframe 打开 `threedresourse/panorama/toselect`）；模块 `resourceQj {previewUrl: https://mobile3.chaoxing.com/fyportal/threedresourse/panorama/review/<id>, title, mid}`。上传新全景是同页的 `panorama/upload`（第三轮已做成 `upload_panorama`）。
  - 投票问卷：编辑器弹出 `mobilelearn /page/questionnaire/addOrUpdateQues4Chapter?courseId`，「完成」= `POST /v2/apis/chapterquestion/publish?DB_STRATEGY=COURSEID&STRATEGY_PARA=courseId`（`#formId`：content、courseId、questioncount、timelong（-1 手动结束）、question_type_N（0 单选/1 多选/4 简答/16 判断）、question_content_N、question_options_N/question_option_N_j、question_ismust_N、isscanresult、isanony、isUsed=on），返回 `data.message[0].att_chat_course {id, title, subTitle}`；模块 `insertvote {id, title, description=subTitle, mid, _jobid}`。
  - 动画：和其他上传类一样先传云盘；模块 `insertflash {objectid, name, type:".swf", size, hsize, src, _src, title, mid}`，不带任务点。
  - 文档导入：文档先传云盘 → `POST /sqp/api/upload-from-yp {objectId, fileName, isParseLatexFormula}`（云盘对象刚上传时回 `httpCode 404`，过几秒重试）→ `crc` → `GET /sqp/api/parseToHtml?file=<crc>` → `{html}`，追加到卡片正文末尾。
  - AI 排版：`POST /ai-ans/ai/chapter/format`（JSON `{userId, formatText, styleList, t, enc}`，t/enc 是 `get-course-info` 的 `aiInfo.aiWriting.aiTime` / `aiFormatEnc`）→ `text` 是 `[{styleName, content}]`；页面按模板（通用模板1、通用模板2、科技蓝，样式表写在组件里）把每段包成 `<h1/h2/p style class>`，图片、表格、链接先换成「[图片n]」等占位再放回。工具在预演时就调用 AI 并返回排版后的整页正文，确认时保存的正是这份正文；卡片里有插入项时不处理（AI 排版会重写整页）。
  - 智能编写、AI 校正、文档校正在第三轮做成了工具（见下一节）。
  - 实测：测试章节新建一页，依次插入速课、图书、图书内页、全景、投票问卷（3 道题）、动画（自己生成的 30 字节 swf）、文档导入（自己生成的 docx），每次读回都保留之前的插入项；只读预览页（学生看到的）里速课、图书、全景、投票问卷（题目可见）、动画都正常加载。另一页纯文字用「科技蓝」AI 排版后保存，读回一致；有插入项的页被拒绝。
- **课程图谱**（资源中心 → 课程图谱，`mooc2-ans questionBankTopic/knowledgegraphframe`；工具 `get_course_graph`、`get_knowledge_point`、`add_knowledge_points`、`rename_knowledge_point`、`delete_knowledge_points`、`restore_knowledge_points`、`set_knowledge_relations`、`set_knowledge_visibility`、`link_questions_to_knowledge`、`insert_chapter_graph`，学生端 `list_my_course_graph`）：
  - 列表 `GET questionBankTopic/knowledgepointsdata?courseid&clazzid&cpi&ut=t&query&searchType`（HTML：`li.topicList[data][parentId][level]`、`#listtopicname_<id>`、三个 `.tree_tags_box`=关联/前置/后置、`.labelList`、`#showhidestatus_<id>`）。
  - 添加 `POST addtopic {courseid, cpi, topic, addTopicType, curOperateTopicId}`：`addTopicType=1` 加为 `curOperateTopicId` 的子级（0=最外层），`0` 加为它后面的同级。工具按缩进大纲逐个添加：每层第一个用「子级」，后面的用「上一个的同级」，顺序与大纲一致。
  - 改名 `GET editTopic`；删除 `POST deleteTopic {topicId:"a,b"}`（子级一起删，可能异步，轮询 `asyncdeletetopicstate`）；图谱回收站 `topicrecycle/list?courseId&cpi`（`a.qhsz_restore[data-id]` 是 logId，`#topicModelId`），还原 `POST topicrecycle/recover {courseId, cpi, logIds, topicModelId}`，彻底删除 `topicrecycle/delete`。**实测：只还原上级时子级没有一起还原（页面提示说会），还原后排在原同级前面。**
  - 关系 `GET updatetopicrelation {topicId, relationTopicPrevIds(前置), relationTopicNextIds(后置), relationTopicIds(关联), relationDesc(每个关联一条说明，逗号分隔)}`，整体替换；设置 B 的后置为 C 后，C 的前置自动出现 B。
  - 按班显示/隐藏 `GET coursetopic/showhidetopic {clazzid, showHideTopicIds, showOrHideTopic:1 隐藏|0 显示}`（隐藏的知识点该班学生看不到，不计入学情）。
  - 题目关联知识点 `POST qbank/update-topic {topicIds, qids, updateExamWord:false, retainOldTopicRelation:true}`（后台异步）；读回 `questionBankTopic/reltaionquestionbanklist?topicId`（「关联试题数」和每题题干、题型，没有题目 ID）。
  - 章节插入「课程图谱」：`POST mooc1 /mooc-ans/knowledge-topic-relation/save-knowledge-graph {courseid, mid, topicIds:"a,b,", knowledgeid=章节}` 返回图谱 ID，模块 `knowledgeGraph {mid, knowledgeGraphId}`；预览页显示「章节知识图谱」和关系说明。
  - 学生端：`stat2 /study-knowledge/index`（隐藏字段 `enc-courseId` 等，`pEnc` 为空也能用）→ `GET /stat2/study-knowledge/stu-detail/data {clazzid, courseid, cpi, ut:s, pEnc, topicName, personId=cpi, parentId}`（要带页面作为 Referer），返回树形 `childrenList`、`beforeList/afterList/relationList`、`completeWeightRate`（完成率）、`graspWeightRate`（掌握率）。页面说明：完成率看知识点关联的任务点、作业、考试、章节测验的完成情况，掌握率看这些题目的得分；统计可能延迟 2 小时以内。
  - 其他导入导出（未做成工具）：智能导入 `qbank/import-topic-page`、模板导入 `import-export-ans/import/topicbyobjectid`、xmind 导入 `xmindFileImportTopic`、同步其他课程 `syncothercoursetopic`、课程章节导入 `savetopicbychapterid`；导出 Excel `questionBankTopic/export-knowledge-points`、xmind `exportcoursetopicxmind`。
  - 实测：测试课里建了 A(a1 a2 a3)、B(b1 b2)、C(c2(c22) c1)、D、E(e1(e11)) 一套用字母和数字命名的知识点，关系 B→C、C 前置 B / 后置 D、E / 关联 A，按班隐藏再显示、删除再还原、两道题关联到 A、一题关联到 c1；学生身份读到的结构和关系与教师端一致。
- **其他图谱（只有新版图谱才有）**：课程图谱页「体验新版」会把课程切换到新版（`coursetopic/switchtopicversion`，页面限制切换 2 次；切换后父级知识点变成「分类」，知识点下不能再有子级，同名节点自动加数字）。新版是 `/topic-ans/knowgraph/index.html` 里的单页应用：问题图谱 `#/questionMap`、目标图谱 `#/targetMapTeacher`（课程目标）、目标图谱模板 `#/targetMapTemp`、思政图谱 `#/ideologyPoliticsMap`，地图模式 `#/map`。旧版的四种视图：大纲模式、思维导图模式、图谱模式（`questionBankTopic/topicnewgraphdiagram`）、地图模式。第三轮已把测试课切换到新版并做成工具（见下一节）。
- **错题集排查（2026-11-08）**：学生端错题集页 `wrongque/page`（隐藏字段 `stuId=0`、`queType=-1`，页面自己按 `type=-1` 查 `wrongque/data`；工具已改成同样的参数）。真实测试：作业「[MCP测试]错题集测试」学生本人答错并「确认提交」，作业详情显示 0 分、带「错题练习」按钮（这是按单份作业生成自测：`mooc2/exam/create-self-test {answerId, from:workWrongQuestion, createType:4}`），但错题集 6 小时后仍为空；把这道题事后关联到知识点也没有变化；课程设置里没有错题集相关开关。换成考试测试时，进入考试前平台弹出滑块安全验证，需要学生本人完成。

### 2026-11-08（第三轮）新版图谱、试卷库导入导出、智能编写、AI 校正、全景上传
- **新版图谱**（`ops_graph2.py`，测试课已用 `upgrade_course_graph` 切换）：
  - 切换：`GET mooc2-ans coursetopic/switchtopicversion?switchtopicstatus=1`，再轮询 `switchtopicversionstatus`。切换后师生两端的课程图谱入口都打开 `/topic-ans/knowgraph/index.html#/knowledgeMapTempPage`（学生带 `ut=s`）。
  - 图谱类型：`coursetopic/getmodelheadlist` 的 `topicModelList`：1 知识图谱、6 知识列表、2 学习地图、3 问题图谱、4 能力图谱（就是课程目标）、5 课程思政图谱。开关在旧设置页的 `mapAdvanceSetting.js` 里：`questionBankTopic/updatequestionmap {questionMap}`、`updateabilitymap {abilityMap}`、`updateideologicalmap {ideologicalMap}`。`updatetopicmodel` 改 `isShow` 没有效果。
  - 知识点：旧的 `questionBankTopic` 接口照样能改；有子级的节点是「分类」，最底层才是「知识点」。标签（重点/难点/考点/课程思政/自定义）：`ideologicaltopiclabel` 列表、`addtopiclable` 新建、`POST updatetopiclablerelation {topicId, batchAddLabel:0, topicIdLabels:"a,b,"}` 打标签。课程思政图谱 `ideologicaltopicdata` 的节点带标签 ID，打了「课程思政」标签的知识点显示成花。
  - 问题图谱（stat2，`courseid、clazzid（教师 0）、cpi、ut、modelId:0`）：`question-map/questionLevel/list|update`（层级名称和说明）、`question/list`（按层级分组）、`POST question/add`（`questionId=0` 新建，否则修改；修改时平台会清空没传的字段，工具先读原值再补上）、`levelQuestion/editLink {sourceId, targetIds}`（关联下一层问题）、`question/batch-delete` → `recycle/list|recovery`（回收站记录有自己的 ID，和问题 ID 不同）。问题只能关联最底层的知识点，传「分类」平台会静默丢掉，工具在预演时拒绝。学生端用 `question-map-stu/…`，看不到教师参考。
  - 能力图谱 / 课程目标（stat2）：`course-target/manager/targetList`、`POST addTargetV2 / updateTarget {targetId, name, description, labelIds, topicIds, type:0}`、`POST delete {targetId}`、`labelList` / `POST addLabel {name}`；图 `course-target/knowledge/knowledgeMap`（学生 `study-target/knowledge/knowledgeMap`）。
  - 实测：给几个知识点打上重点、难点、课程思政标签，课程思政图谱里对应的知识点标成思政点；问题图谱建 Q1–Q3（分层、带标签和知识点），关联下一层，删除后从回收站还原；课程目标新建两个（关联知识点、带「知识目标」标签）、改名一个、删除一个；学生身份读到问题、能力、课程思政三种图谱，和教师端一致（不含教师参考）。
- **试卷库导入导出**（`import_exam_paper`、`export_exam_papers`）：
  - 凭据在试卷库页的隐藏字段 `moocImportExportUrl`、`importEnc`、`importExportEnc`、`examExcelExportVersion`。`classId` 必须是 `-1`，否则返回「enc验证失败」。
  - 导入 `POST import-export-ans/import/paperlibrary-word|ti?courseId&classId=-1&pid=0&cpi&enc`（+`&paperid=<平行试卷>` 导入成子卷），multipart `{file, crc:''}`，返回 `{paperid}`；工具再改标题并在试卷库核对。Word 必须用平台模板 `/mooc2-ans/template/importExamPaper.doc`，平台自己导出的 Word 不能再导入。
  - 导出 `import-export-ans/export-paperlibrary?courseId&classId=-1&paperIds&exportType=word|pdf|excel|ti&exportAll=false&cpi&enc&version`（不含答案时加 `includeAnswer=false&includeParser=false`），单份普通试卷直接返回文件。
  - 实测：把一份 2 题的子卷导出成 Ti，再导入成新试卷（2 题、10 分，标题按指定改好）；把平台导出的 Word 再导入，平台拒绝（要用模板），工具返回未写入；导入成平行试卷的子卷也成功。
- **改已发布考试/作业的时间**：页面校验不通过时只弹提示、不发请求，工具原来会一直等到超时。现在截获页面的 `$.toast`，没发请求就直接返回页面提示（不会写入）。
- **章节「智能编写」**（`ai_write_chapter`、`get_ai_writing_options`、`add_ai_writing_option`、`delete_ai_writing_option`，`ops_ai.py`）：
  - t/enc 来自 `get-course-info` 的 `aiInfo.aiWriting`（`aiTime`、`aiEnc`、`aiWritingChapterEnc`、`aiWritingArticleEnc`）。`POST /ai-ans/ai/chapter/writing`（JSON `{userId, content, writingType, t, articleTheme, articleType, hostName, botType, enc}`）返回 SSE 流，每段 `data:{choices[0].message.content}`（豆包模型）。
  - 先写大纲：`writingType=chapter`，`content` = `<文章主题> 帮我生成一篇 <主题><类型名></文章主题><目录结构>引言;结尾;</目录结构><文章字数>n</文章字数>`；再写正文：`writingType=article`，`content` 带 `<目录结构><大纲></目录结构><年级或对象>…<文章字数>…<写作风格>a;</写作风格>`。联网搜索（`botType=1`）时正文后面是 `[textEnd]` 和来源列表 `[{siteName, title, url}]`。
  - 9 种文章类型、25 个目录结构（每种类型默认选哪几个照页面）、6 种写作风格；自定义选项 `mooc-ans/ai/chapter-writing/get|save|delete`（`type` 1 文章类型 / 2 目录结构 / 3 写作风格）。
  - 页面「加入章节」是把渲染后的 Markdown 插到当前页；工具在预演时就生成全文并返回大纲、正文和来源，确认后把这份正文转成 HTML 追加到页面末尾并读回核对。
  - 实测：大纲 → 正文 → 追加到测试页，读回一致；联网搜索版本返回了 3 条来源；自定义写作风格新增、读回、删除。
- **章节「AI 校正」**（`ai_check_chapter`、`stop_ai_check`、`apply_ai_corrections`）：
  - 文本：把这一页正文的纯文字按 1000 字一段 `POST /mooc-ans/edit/ai-correction {courseId, knowledgeId, cardId, cpi, content, batchnum, type:0}`；`GET ai-check-result` 返回 `checkStatus`（-1 没检测过、0 检测中、3 已停止或无结果、其他=完成）和 `data[{type, wrongWord, correctWord}]`，错词在 `<span class="ai-error">`，建议在 `<span class="ai-correct">`；`ai-check-stop` 停止。类型有标点、成语、拼写、语法、搭配、地名、机构名、领导人姓名、时间。
  - 替换：编辑器在正文的文字节点里找错词，并核对错词前后各一个字和检测片段一致才替换，然后保存这一页。工具照搬这个规则；预演给出每一处修改，确认时正文必须和预演时一样，否则不写。
  - 文档：t/enc 是 `edit/chapters/<课程>/<章节>?…&newMooc=true&mooc2=1` 页面里的 `#aiDocCheckTime`、`#aiDocCheckEnc`；`POST ai-doc-correction {objectIds}` 开始，`POST ai-doc-correction-result` 查状态（0 未开始、1 通过、2 可优化、3 进行中、4 失败），`GET ai-doc-correction-data` 取检测结果。文档只读，要在原文件里改好再重新上传。
  - 实测：测试页加了一段带错别字的文字（再接再励、按部就搬、半途而费、的的、半角逗号）。平台很慢：文本检测和测试 PDF 的文档检测都过了一个多小时才出结果（45 分钟时还是「检测中/进行中」，在编辑器里点「开始检测」也一样），所以工具只等最多 3 分钟，之后用 `start=false` 再读。结果：文本 5 处（拼写 1、成语 3、标点 1），PDF「通过」。`apply_ai_corrections` 把 5 处全部替换进正文并保存，读回一致。
- **全景资源上传**（`upload_panorama`）：全景选择页 `mobile3 /threedresourse/panorama/toselect` 的上传只把文件本身（字段 `file`）`POST /fyportal/threedresourse/panorama/upload`，返回 `{status, msg, data:{id, filename}}`，页面上的「资源类型」下拉框不会发送。实测：上传一张 2048×1024 的 jpg，平台识别为 image，再用 `insert_chapter_panorama` 插入测试页。
- **测试数据清理**：试卷库里两份导入测试卷已删到回收站。

### 2026-11-08（第四轮）知识列表、学习地图、移动知识点、问题图谱的探索和讨论
- **图谱显示隐藏**：新版「设置 → 图谱设置」每种图谱一个开关，点一下立刻 `GET coursetopic/updatetopicmodelhide {courseid, cpi, hide, topicModeoId(拼写如此)=<图谱ID>}`，图谱 ID 在 `coursetopic/gettopicsetting` 的 `topicModelData`。实测：这个开关只决定师生两端显不显示这个标签页，问题图谱的「开启」状态（`switchStatusData.problemMapStatus`）不变。`set_graph_type` 现在对所有图谱用这个开关，只有功能本身没开时才用旧设置页把它打开。
- **知识列表**（图谱样式 8，`#/knowledgeMap/listMode`）：`GET coursetopic/gettopicwoodsdata {page, limit, orderType(0 降序/1 升序), orderText, query, lableIds}`，`orderText`：完成率 `completeWeightRate`、掌握率 `graspWeightRate`、使用量 `citecount`、创建时间 `id`。「添加知识点」`GET coursetopic/woodsaddtopic {topic, classify, topicLabelIds, topicDesc}` 加在图谱最外层；列表的索引要过几秒才出现新知识点（大纲里先出现），工具按大纲核对。
- **知识点属性**：`questionBankTopic/edittopicproperty` 读，`POST savepropertyedit {topicIds, classify(1 事实性/2 概念性/3 程序性/4 元认知), cognize:-1, topicLabelIds(整体替换), topicDesc, teachTargert(拼写如此), studyHours}`。实测：类型、说明、标签、参考学时都能保存；教学目标在课程没开启时不保存。
- **学习地图**（图谱样式 1，框架视图）：`GET coursetopic/getframemodeldata {topicModelId:0, getLabelData:1}`，最外层节点是阶段，带所选班级的 `completeWeightRate` / `graspWeightRate`；`getlearnmapmodeldata` 的 `topicDataCount` 是独立学习地图的节点数（测试课 0，学习地图直接用课程图谱）。
- **移动知识点**：学习地图的「编辑」是思维导图编辑器（`#/mindMapEdit` → `questionBankTopic/knowledgegraphmindmapv3`，里面再嵌 `/topic-ans/mindMap`），保存 `POST savetopicbymindmap {topicModelId, topicdata: {root, linkData}}`。**实测：在这里把知识点挪到别的上级后，平台把它删掉重建成新 ID，标签、关系、关联题目都丢了**（同一上级内调顺序 ID 不变）。所以 `move_knowledge_point` 改用知识图谱「编辑」大纲页的拖动保存：`POST questionBankTopic/updatetopicsort {topicsort: [{id, children:[…]}]}`，实测跨上级移动 ID 和标签都保留。目标上级必须是「分类」。
- **问题图谱的学生探索**：设置在 `stat2 /stat2/knowledge/getBaseSetting {modeType:3}` 的 `exploreMode`、`exploreSetting {link, topic, answer}`（关联、知识点、简答三类任务），修改 `GET /stat2/question-map/update-exploreSetting {setting}`、`update-exploreMode {link, topic, answer}`。学生端：`question-map-stu/explore/getSonQuestion {questionIds}` 给出这个问题下要回答的子问题（**返回里带着教师参考 `answer`，工具一律去掉**），`explore/record {type:2}` 是本人已保存的回答，`POST explore/update-record {questionIds, data: {顶层问题ID: [{id, questionLevel, stuAnswer}]}, type:2}` 保存，`explore/progress-questionId` 是进度。工具只做了「简答」（type 2）。
- **问题图谱讨论区**：`question-map-stu/bbs/topic-list {lastValue}`（师生都用这个读），发帖 `POST question-map-stu/bbs/topic-add`（教师 `question-map/bbs/topic-add`）`{topicTitle(≤20 字), topicContent, rtf_content, imgUrlArr, attachment}`，点赞 `topic-praise`。列表不返回作者姓名（只有带用户 ID 的头像地址，工具不返回）。
- 实测：知识列表开关关/开；添加知识点 G、H 并改属性；F 在 E 下和最外层之间来回移动、a3 调顺序，ID 和标签都不变；问题图谱的标签页隐藏再显示；开启学生探索；教师发帖。学生身份：读到知识列表、学习地图、问题图谱探索（没有参考答案），两次「确认提交」保存了两个子问题的回答（第二次保留第一次的回答，进度 33%），讨论区发帖成功。

### 2026-11-08（第五轮）稳定性修复：会话自愈与课程列表静态读取
- **会话已死自愈**：`bsk.ensure_session` 原来只在 `session_idle_timeout` 且 `preserve_tab=False` 时才重建会话；而任何一次报错都会置 `preserve_tab=True`，之后会话闲置或窗口被关就永久卡死，只能重启服务。现在把 `session_idle_timeout` 和 `session_window_closed` 都判为"会话已死"——这两种情况下代理标签页已不存在、无东西可保护，故即使 `preserve_tab=True` 也重建会话；其它错误（permission/transport/unknown，标签页还活着）的 preserve_tab 保护不变。回归测试 `tests/test_session_recovery.py`（合成数据）：两种死会话原因都恢复、三种活页错误仍拒绝。
- **课程列表改静态读取**：`xxt.courses` 原来导航到持续重绘的 `visit/interaction` 页抓 live DOM，间歇被 BrowserSkill 以 `observation_changed` 拒绝（health_check 的 courses 步因此永远失败）。改为从静态基准页同源 fetch `mooc2-ans/visit/courselistdata?courseType=0`，用 DOMParser 解析同一批 `div.course[id^=c_]` 卡片（courseId/curPersonId/role 隐藏字段都在），保留主讲/团队 role 区分。注意 `mooc1/visit/courselistdata?courseType=0` 返回的是不带 role 的 `li.course`，不能用；要用 mooc2-ans 宿主的。实测仍返回 60 门、36 主讲+24 团队、名字/cpi/info 与原版逐条一致。回归测试 `tests/test_courses_fetch.py`。
- **health_check 步骤重排**：把 courses 和界面语言检测移到 guard 导航之前（此时标签页还在稳定静态页，避免从持续重绘的 mobilelearn 页发起下一次导航被拒）；语言检测改为静态 fetch `visit/interaction` 外壳 HTML 判断"我教的课/我学的课/新建课程"标记，不再读活页 body。实测 health_check 现在 courses=60、ui_language=中文、error=null；ok=false 只剩"未装防 App 跳转扩展"这一个真实环境原因。
- 全套 233 项测试通过；重启服务后经真实 MCP stdio 链路复核 health_check 与 list_courses 均正常。

### 2026-11-08（第六轮）把"仅预演/尚未核实"的工具补到可执行+已核实
- **讨论分页**（list_discussions）：`getTopicList` 的 page 号被平台忽略，真实分页是游标式——首页不传 `last_reply_time`，后续页回填上页 `poff.lastValue`（并带 `lastAuxValue=poff.lastAuxValue`），`poff.lastPage==1` 终止。`topics()` 改为沿游标翻页、按 uuid 去重、limit 封顶（页大小常量 TOPIC_PAGE_SIZE）。实测助手课 8 条话题，页大小 2 翻 5 页与单大页结果逐条一致。回归 `tests/test_discussions_pagination.py`。
- **二维码签到**（start_checkin）：`start_checkin_v3` 加 `qr_refresh` 参数，二维码置 `ifrefreshewm=1`+`ewmRefreshTime`；工具放开 bar=2 为可执行（普通/二维码/签到码）。实测发二维码签到，`getPPTActiveInfo` 读回 `ifrefreshewm=1` 确认平台真建成二维码类型。回归 `tests/test_write.py`。
- **活动删除泛化**（delete_activity）：新增 `prepare_activity_deletion`（任意类型，班级校验+唯一性+预演冻结+结果未明保护），复用类型无关的 `setdel`+回收站正向核实。注意 `activities()` 只对通知活动附 class_id 字段，普通活动靠查询 classId scoping+回收站核实（有 class_id 才校验）。实测删普通签到/二维码签到，`absent_from_active_list`+`recycle_row_verified` 双通过。回归 `tests/test_activity_delete.py`。
- **签到名单**（checkin_status）：改读 `/widget/sign/pcTeaSignController/getAttendList`（`yiqianList`/`weiqianList`+`yiqian`/`weiqian`计数+`signRate`），避开重绘的 endSign 页，按计数核对名单长度（lists_verified）。`signRate` 是 0–100 百分比。实测：教师工具按设计不代签，由测试者本人账号驱动学生端 `/v2/apis/sign/signIn` 给林云学生身份造一条已签数据，已签/未签两侧名单+rate=50 全核实。回归 `tests/test_checkin_status.py`。
- **考试批阅名单**（exam_marklist）：改读 `POST /mooc2-ans/exam/test/markresult-new`，`state:'1'`=已交/`state:'0'`=未交（**不是 perspectiveType**），id 用考试关系 ID（clazzAndRelationId[clazzid]，本例等于考试 ID）、clazzid 用考试实际班级（从 class 名映射），分页按计数核对。实测助手课已交 1/未交 1 的考试，submitted_rows/unsubmitted_rows 全核实。回归 `tests/test_exam_marklist.py`。
- 全套 249 项测试通过；每项均经真实 MCP stdio 链路在助手课实测。

### 2026-11-09（第七轮）手势/位置签到补全为可发布（五种签到全通）
- 签到类型由 saveOrBegin 的 query `otherId` 区分（0 普通/2 二维码/3 手势/4 位置/5 签到码，正好等于 SIGN_TYPES 的 bar）。**手势**：口令存正文 `signCode`，就是九宫格 1-9 的数字序列（如 12357=左上→右横→左下斜），实测 getPPTActiveInfo 读回 otherId=3、signCode="12357"。**位置**：`ifopenAddress=1`+正文 `locationText`（地点名）+`locationRange`（默认 500 米），经纬度可空——实测 locationText="湖南中医药大学" 读回正确，平台接受无坐标。
- UI 发布路径（ops_activity.start_checkin 画手势/选地图）实测不可用：既要 `__xxtNoAppGuard` 防跳转扩展（未装），又在重绘的签到表单上被 observation_changed 拒绝。故五种类型统一走 saveOrBegin 接口（静态基准页，可靠）。`start_checkin_v3` 加 other_id/location_text/location_range 参数；工具按 bar 路由。
- 全套 253 项测试通过；手势/位置均经 MCP 工具端到端发布并核实，测试签到已清理。回归 `tests/test_checkin_gesture_location.py`。学生端按设计仍不做签到写操作（不代签）。

### 2026-11-09（第八轮，C 批 checkpoint）问题图谱探索三类任务全通
- **C1 问题图谱探索 link/topic**：`explore/update-record` 的 `type` 映射实证为 **0=关联(link)/1=知识点(topic)/2=简答(answer)**（getBaseSetting 的 exploreSetting{link,topic,answer} 三类全开）。data 结构与简答完全相同 `{topId:[{id,questionLevel,stuAnswer}]}`，只是 stuAnswer 语义不同：简答=HTML 文本（para 包裹），关联=相关问题 ID、知识点=知识点 ID（原始字符串，不包 para）。实测助手课问题图谱（测试班 159260111，林云学生身份）：type1 存 stuAnswer="281207139"（知识点 a2）、type0 存 "11413389"（关联 Q2），读回一致。`my_qm_explore`/`save_my_qm_explore` 加 task_type 参数，学生工具 list/save_my_question_explore 同步暴露。回归 `tests/test_qm_explore_types.py`，全套 256 通过。
- 探查笔记：stat2-vue 是 SPA，问题图谱学生探索逻辑不在 app.js 的 50 个懒加载 chunk 里（前端逆向未果），改用实证 API（直接调 record/update-record 试 type 0/1/2）确定映射，更可靠。`_get` 用 STAT_HOST（带 https://），勿用 xxt.STAT（无 scheme）。

**C 批待续（按可行性排序）**
- C2 图谱批量导入/导出：导出端点 `questionBankTopic/export-knowledge-points`(Excel)/`exportcoursetopicxmind`(xmind) 需新版图谱专属凭据——带课程 enc/ut=t 仍报"非教师无查询权限"/"无效的课程"，旧版大纲页已重定向成空壳；凭据在 topic-ans/knowgraph SPA 里，待逆向。导入 5 种（智能/模板/xmind/同步他课/章节）更复杂。
- C3 错题集：接口通，但课程创建者本人学生身份 stuId=0 收不到错题，**必须纯学生测试号登录**答错后验证非空格式。
- C4 AI 助教对话：读接口已通（robot-lc），发送端点（SSE chat）待抓包。
- C5 全景 6 图：上传机制完全未知，最低优先级。

### 2026-11-09（第九轮）首次登录引导（v0.8.0）
- 新增 `login.py`：CredentialStore（系统 keyring，Windows WinVaultKeyring 实测 roundtrip）、本地表单采集（仅 127.0.0.1 + Host 校验防 DNS-rebinding + 一次性 CSRF + no-store + 请求体上限 + 密码不进日志）、LoginAutomator（bsk 填 passport2 的 `#phone`/`#pwd`、点 `#loginBtn`、轮询 `i.mooc.chaoxing.com` 首页；滑块人工）、run_login/run_logout 编排。
- 流程：首次调 `login` 工具弹本机表单输账号密码 → 存 keyring → 自动填表提交 → 人工划滑块 → 到达各自首页；账号名持久化到 config `[login] login_account`，之后凭据复用、过期自动重登；`logout` 删凭据。`auto_login` 默认开（env `XUEXITONG_MCP_AUTO_LOGIN=0` 可关）。login/logout 跨所有 profile（policy.LOGIN_TOOLS）。
- 实测：维护者本人账号走完整流程，health_check 由"未登录"变"已登录"、courses=60。修复 LoginAutomator 误用 Bsk.here（应为 eval）。全套 277 测试通过。新增依赖 keyring>=24。
- 安全模型变更（维护者批准）：从"完全不碰密码"改为"密码仅存本机系统 keyring + 半自动登录"；滑块/短信/协议仍由本人完成，不做反反爬。

### 讨论（groupweb）
- 发帖：`POST /pc/topic/{bbsid}/addTopic?uuid=<客户端生成的话题uuid>`，表单字段：`topicTitle`、`topicContent`、`rtf_content`、`isRichText=1`、`files_url`/`files_attr`（附件）、`tags=classId<班级ID>,classId<班级ID>`（发布班级）、`folder_uuid`、`label`、`anonymous`、`bbsid`、`courseId`、`urlToken`（页面变量）、`managerNeedAiReply`（AI助教回复）。回复设置：`deadline`、`replyWordsLimit`、`replyWordsMax`、`replyTimesLimit`、`allowViewReply`、`replyCanAnonymous`、`recordAnonymousScore`、`sendNoticeToStu`。
- 发帖页还提供：附件、图片、云盘、笔记、录音、网页链接、公式/LaTeX、表格、思维导图、白板、导入文档、选择讨论区、关联知识点。发帖后页面会整体刷新。
- 话题操作菜单：转发、置顶、加精、编辑、移动到、删除。删除：`GET /pc/topic/{bbsid}/{话题uuid}/deleteTopic`，先弹「确认删除？」。
- 其他入口：新建文件夹、新建讨论区、讨论区管理、话题管理、回收站、章节讨论、我发布的/我回复的/回复我的。
- `list_discussions` 在有话题时已验证可读（字段：topic_id、title、content、author、replies、reads、time）。

### 通知（notice）——用 MCP 自身工具端到端验证
- `publish_notice` 预演 → 确认发送 → 按 UUID 核实标题、正文和班级 → `delete_notice` 预演 → 确认删除 → 复查列表为空，全链路通过。
- 发现并修复：发送后页面被替换时，同步偶尔返回 `not_found`。现在改为直接进入只读核实，不再报「结果未知」。新增 `reconcile_notices`，按 UUID 补记结果未明的发送。

### 教学活动（mobilelearn）
- 「添加活动」共 30 种：
  - 课堂活动：签到、选人、随堂练习、主题讨论、抢答、问卷、分组任务、投票、评分、抽签、群聊、AI实践（另有活动库）
  - 教学工具：白板、计时器、腾讯会议、直播、通知
  - 教学资源：课件、教案、章节、资料、笔记、云盘、电脑文件、网页链接、作业、考试
- 注意：Agent 窗口较窄（约 547px）时，添加菜单会被排到可视区外（x<0），bsk 原生点击会报 not visible。可以用 `bsk session start --width/--height` 放大窗口，或直接触发元素的 click（例如 `li.btnSignIn`）。
- 签到表单字段：`signTitle`；类型 `typebar0/3/4/2/5`（普通、手势、位置、二维码、签到码）；`signIfphoto`（拍照）；`numberCode`（签到码）；`ifopenAddress`和`sign-select-distant`（位置和距离，默认 500）；`signIfrefreshewm`和`select-frequency`（二维码刷新，默认 10 秒）；签到时长；迟到 `late-minute`；签退 `signOutSwitch`、`signOutTime` 和时长；防作弊 `ifNeedVCodeSwitch`、`openCheckFaceSwitch`、`openCheckWeChatSwitch`；定时发放 `openTimer`（一次性 `disposable_publishtime` 或每周重复，有效期，跳过周末）；`onlyAttendForCurrentClass`；`ifSendToOtherClass`；关联知识点。各活动的开始按钮：`#signin_begin`、`#quickAnswer_begin`、`#qvote_begin`、`#timer_begin`、`#selectPerson_begin`、`#grade_begin`、`#discuss_begin`、`#board_begin`。
- 建立签到：`POST /v2/apis/sign/saveOrBegin`。query 参数：`now=1`（立即开始）、`courseId`、`classId`、`timeLong`（毫秒，默认 1800000）、`ifphoto`、`ifrefreshewm`、`ewmRefreshTime`、`ifopenAddress`、`locationLatitude`/`locationLongitude`/`locationRange`、`lateMinute`、`ifNeedVCode`、`openCheckFaceFlag`、`openCheckWeChatFlag`、`openSignOutFlag`、`signOutRelativeTime`/`signOutAbsoluteTime`/`signOutDuration`、`timerCron`/`dateCron`、`disposable_publishtime`、`validity_begintime`/`validity_endtime`、`ifSkipWeek`、`ifSendToOtherClass`、`onlyAttendForCurrentClass`。表单正文：`title`、`signCode`、`locationText`、`sendToOtherClassList`、`knowledgePoints`。开始后页面跳到 `/page/sign/endSign?activeId=…`。
- 用 MCP 自身工具验证：`end_activity`（预演 → 确认 → 已结束）、`activity_result`、`checkin_status` 均通过。
- **2026-11-07 其余活动（做成工具，测试班里保存和开始都实测）**。全部从 mobilelearn 的静态页发请求，不打开编辑器（随堂练习编辑器一直重绘，停在上面时下一次导航会被 BrowserSkill 以 observation_changed 拒绝）。活动类型号：选人 11、抢答 4、主题讨论 5、问卷 14、评分 23、随堂练习 42、资料 44、学生反馈 46、计时器 47、白板 49、投票 43、抽签 80、分组任务 35。
  - 选人 `POST /v2/apis/selectperson/{saveSelectPerson|beginSelectPerson}`；抢答 `POST /v2/apis/answer/{saveAnswer|beginAnswer}`（短字段在 query，标题在正文）；投票 `GET /widget/quickvote/{saveQVote|publishActive}`，`question_options_<预设号>=A…` 重复参数；主题讨论 `POST /v2/apis/discuss/{saveDiscuss|startDiscuss}`，**activeId 要传空**，传 0 会回「未查询到活动信息」；评分 `POST /v2/apis/score/saveOrStartScore`（type 0/1）；计时器 `GET /widget/renwu/{sa|st}`。
  - 学生反馈 `POST /widget/CWareDataController/{saveFeedback|beginFeedback}`，要 `uid`（取 `_uid` cookie）和 `fid`；白板 `POST /widget/whiteboard/{savewb|startwb}`；抽签 `POST /v2/apis/drawLots/{saveDrawLots|beginDrawLots}?DB_STRATEGY=COURSEID&STRATEGY_PARA=courseId`，`activeType=80`、`signatureList="[]"`。
  - 随堂练习 `POST /v2/apis/quiz/{saveOrUpdate2|publish2}?DB_STRATEGY=COURSEID&STRATEGY_PARA=courseId`，`questions` 是编辑器 `vm.questionList` 的 JSON（题型 单选0 多选1 填空2 判断16 简答4；多选 rightAnswer 如 `ACD`，`amin/amax` 是可选数量；判断 rightAnswer 对/错；填空答案在 `answer[].content`；简答在 `answer[0].answer`）。保存必须带活动分组 `planId`（`GET /v2/apis/active/groupPlanList` 第一个，页面弹「保存到」让人选），开始不需要。编辑器默认：存入题库、学生交后可看答案、可改答案、到时自动提交。读回：重新打开草稿的编辑器，5 种题型的题干、选项、答案、分值都对。
  - 问卷 `POST /v2/apis/question/{saveOrUpdate|publish}`，正文就是编辑器 `#formId` 的序列化：`content`(标题)、`questioncount`、每题 `question_type_N`(0/1/4/16)、`questionId=0`、`question_content_N`、`question_options_N`(重复)、`question_option_N_i`、`knowledgePoint_N`、`question_ismust_N`，以及 `credit`、`isanony`、`isscanresult`、`isSaveToReservoir`、`isSaveAct`（保存=1 不进问卷库，开始=0）。
  - 分组任务 `POST /v2/apis/task/saveOrBeginTask?…`，`beginOrSave` 0/1；「不分组（个人任务）」是 `groupType=3`、`isSpecialPersonalTask=1`；评价默认教师 100%。开始时班级没有学生会被拒绝（「班级没有人员，无法发放活动」），工具把这种拒绝报告为 not_written。
  - 推送资料 `GET /v2/apis/resource/getCourseResourceList?courseId&rootId` → 用页面 `dealResourceData` 的规则（按 cataid 和后缀定 resourceType）→ `POST /v2/apis/resource/newRsourceActive?DB_STRATEGY=RANDOM {courseId, classId, resourceData}`。课件、教案走 `POST /v2/apis/active/createTeachPlanActive {classId, courseId, teachPlanData}`，列表分别是 `/v2/apis/activePlan/getCourseWareList`、`getTeachingPlanList`（测试课为空，未实测）。
  - 不做：腾讯会议（`saveOrBeginWeMeet`）、超星会议（`/v2/apis/cxmeet/saveOrBegin…`）、直播，都会真的开会或开播。

### 作业（mooc2-ans/work）
- 作业库：`work/library`。新建方式：手动创建、分组作业、教学资源库。还有导入作业、导出全部作业、草稿箱、新建文件夹、回收站。每份作业的操作：发布（`checkQuestion(workid)`）、编辑、移动到（`showMove`）、复制（`copyWork(workid)`）、删除（`workOperate`）。
- 编辑器：`work/goToWorkEditor`，在**新标签页**打开，保存后会**自己关闭标签页**（截获请求要用同源 localStorage）。
  - 作业级设置：作业类型（题目型或答题卡）、评分机制（百分制或自定义）、是否按题型归类。
  - 题型共 23 种，外加「新建题型」：单选、多选、填空、判断、简答、名词解释、论述、计算、分录、连线、排序、完型填空、阅读理解、程序、口语、听力、共用选项、测评、口语测评、钟表、选词填空、写作、其它。
  - 题目来源：从题库选题、从云盘选题、AI 出题、智能导入。
  - 每题可设：题干（UEditor 富文本）、答案、答案解析、难度、知识点、标签、分值。
- 新建链路（全部是接口）：
  1. `POST work/questionInit`（courseid, clazzid, cpi, workid, relationid, title, directoryid, grading, questionGroup, originType, courseQuestionTypeId）：第一题 `workid` 留空，返回 `{questionid, relationid, workid}`。`relationid` 填该题型已有的分组 ID，没有就填 0（会新建分组）。
  2. 普通题型 `POST work/toEditWorkQuestion`（整张 `#workForm` 序列化，返回 `success:true`）；组合题（完型填空、阅读理解、听力）`POST work/saveInnerQuestion`（返回 `status:true`）。
  3. `GET work/save-work?workid&title&grading&directoryid&workStatus=0&questionGroup=0`：保存。
  - 系统题型的 `courseQuestionTypeId` 等于题型编号。百分制作业不能加测评题（页面限制）。
- 答题卡作业（作业类型选「答题卡作业」，编辑器 `goToWorkEditor?…&scantron=1`）：正文是一个富文本（`POST work/save/explain`），题目只有答题卡：
  1. `GET work/add-question?type&count&score&optionCount&title&grading`：按题型批量加空题（1 选择、2 填空、3 判断、4 简答；15 组合题走 `add-complex`）。
  2. 点选项设答案，每题即时 `POST work/save-answer`（`answer` 是 JSON，如 `[{"name":"B","content":"","isanswer":true}]`）。
  3. `POST work/save-scantron`（questionids、title、answer{题目ID}）→ `GET work/update-scantron`：从草稿箱转入作业库。只调前一步，作业会留在草稿箱。
  - 2026-11-07 实测：建 2 道选择题的答题卡作业，作业库显示「答题卡」标记。已做成工具 `create_answer_card_assignment`。
- 分组作业（作业库「新建作业 → 分组作业」）打开的是 `mobilelearn/page/renwuNew/renwuPublishSetting_new.html`，即教学活动里的分组任务，归到活动一类。

### 题型（作业、试卷、题库共用，2026-11-07 逐个实测）
三个编辑器存的答案 JSON 完全相同，只是接口和少数表单字段不同。下表的「作业字段」指 `toEditWorkQuestion` / `qbank/add_question` 里除公共字段外的部分；试卷每题先 `add-empty-paperquestion`（qtype=题型编号，courseQuestionTypeId=0，relationid=该题型的 paperLibraryRelationId 或新 uuid），再调下表的试卷接口。

| 编号 | 题型 | 作业 / 题库字段 | 试卷接口 | 可用于 |
|---|---|---|---|---|
| 0 | 单选 | `defAnswer`=字母，选项 `A`…`Z` | `editPaperSingleChoiceV2`（A–Z 全发） | 作业 试卷 题库 |
| 1 | 多选 | `defAnswer` 重复多次；试卷里是 `A,C` | `editPaperMultipleChoiceV2` | 全部 |
| 2 / 9 | 填空 / 分录 | 每空 `1`、`2`…；作业 `wrapAnswer`=各空用 ★ 连接，题库和试卷是 `answer`=★ 连接；`isMutex` | `editPaperBlankFillingV2` | 全部 |
| 3 | 判断 | `answerForTF` true/false；试卷是 `answer` | `editPaperTrueFalseV2` | 全部 |
| 4 5 6 7 8 18 | 简答、名词解释、论述、计算、其它、口语 | `answer`=参考答案 HTML（可空），`wordMinNum`、`wordnum` | `editPaperAnswerV2`（另有 useAi、autoScore、promptId=-1） | 全部 |
| 11 | 连线 | `answer`=`[[左项{name:1..}],[右项{name:"A"..}],[{name:1,content:"B"}..]]`，另发 `1`/`A` 字段 | `editPaperConnectionLine` | 全部 |
| 13 | 排序 | `answer`=`[[选项],{"answer":"DBAC"}]` | `editPaperSortQues` | 全部 |
| 14 | 完型填空 | 题干用 `##1##` 标空，保存时换成带下划线的 span；小题只能是单选，小题数必须等于空数；`answer`=小题数组（无 typeId、无小题题干） | `editReadComPrehensionClozeText` | 全部 |
| 15 / 19 | 阅读理解 / 听力 | 小题可为单选、多选、填空、判断、简答；`answer`=`[{id:uuid,type,typeId:0,name,topicIds,targetData,data:{score,content,answer}}]`；判断、简答小题的 `data.answer` 是再序列化一层的字符串 | `editReadComPrehensionClozeText` | 全部 |
| 25 | 选做 | 同阅读理解，另有 `optionalNum`；每个小题分值都等于整题分值 | `editReadComPrehensionClozeText` | 试卷 题库 |
| 17 | 程序 | `answer`=`[{answerCode:<pre><code>…,languageName,languageIndex,exampleArr:[{stdin,stdout,memory,time}],procedureReviewMode:"1"手动/"0"自动,preparedCode:[{codeNum,codeName,code}]}]`；语言编号：C 1、C# 2、Java 3、VB.NET 4、Python2 5、Golang 6、PHP 8、Bash 11、Python3.6.9 16、C++ 17、JavaScript 19、R 20、HTML 21、Python3.12.12 22、Octave 26 | `editPaperProcedure` | 全部 |
| 20 | 共用选项 | `answer`=`[{title:"(1)-(n) 题共用备选答案：",frontDescribe:题干},[选项],[小题题干{name:1..}],[{name:1,content:"B"}..]]` | `editBType` | 全部 |
| 21 | 测评 | `answer`=`[{"selectNum":n},[{name,content,score}..]]`，`selectMaxNum` | `editEvaluation` | 作业（仅自定义评分） 试卷 题库 |
| 22 | 口语测评 | `readText`，`answer`=`[{readText,language:en/cn/fr/jp/sp/kr/de/ru,slack:"2",autoMark:"1",hideReadText:""}]` | — | 作业 题库 |
| 23 | 钟表 | 没有题干；`content`=模式说明文字，`clockType` 0 认读 / 1 拨针，`answer`=`[{type,data:[{period:上午/下午,hour,minute}]}]` | — | 作业 题库 |
| 24 | 选词填空 | 题干 `##n##` 标空；选项是纯文本 `A`…；`answer`=`[[{name:"A",content:词}..],[{name:1,content:"A"}..]]` | `editFillinBlanks` | 全部 |
| 26 | 写作 | `answer`=`[{answer:范文,grade:"cet4",wordMinNum,wordnum:"15000"}]`，`subject=0`、`publishSource=2` | `editPaperAnswerV2` | 全部 |

- 读回方法：作业编辑器左侧点题目是只读视图（显示答案、连线对应、排序结果、程序语言和用例）；试卷编辑器用 `doQuestionLiClick(id,type,0,false)`；题库用 `POST qbank/search`，返回里 `questionBank.answer` / `janswer` 是存下来的答案 JSON（这个接口只在探查时用来核对，`list_bank_questions` 不返回答案）。
- 题库同一文件夹里不允许完全相同的题目，作业、试卷里建的题也会进题库参与判重。钟表题没有题干，同一种模式、同样时刻的钟表题在题库里只能有一道。

- 发布：`GET work/check/question` → 设置页 `work/library/setting?courseid&cpi&workLibraryId` → `POST work/library/publish`。
  - 发放对象：`publishObj=[{"classid":…,"publishType":0}]`，选班控件仍是 `#choosepublish` / `.class_check` / `#confirmchoose`。
  - 有效时段：`startTime`、`endTime`。
  - 截止后查看答案：`answerAfterEnd`、`answerAfterEndDeadline`。
  - 及格与完成：`passingStandard`、`finishStandard`。
  - 重做：`redoTimes`、`redoHighestScore`、`redoDifferQuestion`、`redoDifferLibrary`、`notShowLastAnswer`。
  - 查看权限：`allowAnswer`、`allowScore`、`viewTypeScore`、`knowTrueFalse`、`prohibitViewWork`、`notShowTeacherComment`。
  - 作答限制：`allowPaste`、`randomSort`、`randomOptions`、`allowDownloadAttachment`。
  - 随机抽题：`randomNum`、`randomType`、`randomTypeSet`、`randomCustomScore`。
  - 截止提醒：`endNoticeTime`、`intervalNotice`。
  - 填空和多选评分：`blankobj`、`completionIngoreCase`、`blankIgnoreComma`、`multiHalfScore`、`answerEmptyIsObj`。
  - 互评：`evaluation`、`evaluationStandard`、`evaluationNum`、`evaluationStartTime`、`evaluationEndTime`、`anonymousMarking`、`anonymousMarkingResult`、`teacherMarkScore`、`studentMarkScore`、`evalPartakeScore`、`stuMarkNum`、`selfMark`。
  - 批阅：`aiReview`、`aiAutoMarkScore`、`limitReviewer`、`limitReviewerObj`、`removeMaxMinScore`、`setMarkScore`、`markScoreMin`、`markScoreMax`。
  - 其他：`sortAvgScore`、`questionExplanation`、`saveAsTemplate`、`permissionPassword`/`permissionUuid`。

### 考试（mooc2-ans/exam）
- 试卷库：`exam/paperlist`。操作有：新建考试（`chooseCreatePaperPop`）、导入试卷、导出全部试卷、安全设置（`confirmUpdateSafe`）、新建文件夹、回收站。每份试卷可以：发布（`checkPaperAnswer(paperid,0,'/mooc2-ans/exam/test/topublish?...')`）、编辑（`openUrl`）、锁定题目（`showLockOperate`）、复制或复制后发布（`copyAndPublishPaper`）、移动、题号模式（`saveItemSerialNumberMode`）。
- 新建方式 4 种（`chooseCreatePaperPop` 里的 value）：
  - 0 手动创建：`GET exam/createAnEmptyPaper?courseid&clazzid&pid&parallelpaper=0` 返回 `paperId`，编辑页是 `exam/create-exampaper?courseid&clazzid&paperid&isCustomPaper=false&cpi&ut`
  - 1 随机组卷（从题库）：`exam/toAutoCreatePaperPage?…&createPaperType=1`
  - 2 智能组卷助手：`exam/ai-paper?…&from=2`
  - 3 平行试卷：`createAnEmptyPaper` 加 `parallelpaper=1`，编辑页是 `exam/parallel-paper`
- 编辑器：试卷标题 `#examPaperTitle`、试卷难度、新建分卷、批量操作、题号模式（连续或按题型）、是否按题型归类。题型同作业，多了选做题，没有钟表题和口语测评题。题目来源：从题库、从云盘、AI 出题、智能导入。
- 编辑链路：
  1. `POST exam/update-exampaper-title`（paperid, title）
  2. `POST exam/add-empty-paperquestion`（paperid, relationid, qtype, courseQuestionTypeId=0, groupId）：relationid 是该题型已有分组的 paperLibraryRelationId，没有就给一个客户端 uuid（新建分组）
  3. `GET exam/toHandAddPaperQuestion?…&qtype&questionid&edit=true`（打开题目编辑器）
  4. 每种题型有自己的保存接口（见上文「题型」表），判断题是 `POST exam/editPaperTrueFalseV2`（paperid, courseid, isOpen, score, content, answer, type=3, questionId, typeId, difficulty, easy, topicId, labelIdArr, schoolTopicIds, answerAnalysis）。页面上的校验：分值大于 0、题干非空、已选答案（`.check_answer`，要原生 click 选项 `a.num_option`）。
  5. 「完成」只做 `GET exam/check-question-answer` 和界面确认，不再提交；每题保存时试卷就已经存好了。
- 发放：`exam/test/topublish?taskid=0&clazzid&courseid&ut&cpi&paperid&score` → 确认提示「发布后不可修改题量和分值」→ `POST exam/test/publish`。
  - 发放对象：`publishObj=[{"classid":…,"publishType":0}]`、`makeup`（补考）。
  - 时间：`startTime`、`endTime`、`limitTime`（分钟），`limitTimeType`、`questypeLimitTime`。
  - 交卷与进入：`submitLimitTimeMode`、`submitLimitTime`、`entryLimitTime`、`expiredAutoSubmit`。
  - 防作弊：`forbidMultiterminal`、`terminalFeatureVerify`、`terminalUnlockWay`、`switchScreenControl`、`switchScreenNumberLimit`、`switchScreenThresholdTime`、`snapshotMonitor`、`snapshotInterval`、`notAllowExit`、`pcclientSwitchout`、`clientExam`、`allowCopy`、`allowPaste`、`randomSort`、`randomOptions`、`randomNum`、`randomDifferPaper`、`identifyCode`、`examCode`、`examCodeExpiredTime`、`allowIp`。
  - 查看与成绩：`allowLookpaper`、`allowAnswer`、`allowScore`、`allowViewRightwrong`、`viewTypeScore`、`allowLookObjScore`、`showRank`、`scoreStandard`、`passingStandard`、`retestNum`、`finishStandard`。
  - 评分：`blankobj`、`completionIngoreCase`、`blankIgnoreComma`、`multiHalfScore`。
  - 互评：`evaluation`、`evaluationNum`、`evaluationStandard`、`evaluationStartTime`、`evaluationEndTime`、`anonymousSubmitter`、`anonymousMarker`。
  - 附件与上传：`phoneUploadable`、`forbidCloudFile`、`forbidPhonePhoto`、`forbidPhoneRecording`、`allowDownloadAttachment`。
  - 须知与提醒：`examNotes`、`pcExamNotes`、`examInform`、`scheduledInformTime`、`examNotice`、`endNoticeTime`、`endNoticeTimeMinute`。
  - 作答：`keepLastAnswer`、`allowAnswerBack`。

### 资源中心·智能题库（mooc2-ans/qbank）
- 入口：`qbank/questionlist?courseid&clazzid&cpi&ut=t&enc&t&v=6`。enc、t 和课程外壳的相同；**缺少 `v=6` 会提示「没有此页面访问权限」**。
- 操作：创建题目（手动 `createQuestion()` 或从教学资源库导入 `showZyk()`）、批量导入、新建文件夹、导出（全部或选中，格式有 Ti、Word、Excel、PDF）、题型管理、标签管理（`createLabel`）、安全设置、锁定（`lockQuestion`）、删除（`deleteByIds` → `batchUpdateStatus`）、按题型/课程/正确率筛选、回收站。作业和考试里建的题也会进题库。
- 新建：`qbank/create-question?courseid&cpi&dirId&pageNum&qbanksystem&microTopicId`（不能带课程外壳的其他参数，否则提示无权限），24 种题型都在一个页面里切换。保存是 `POST qbank/add_question?courseid&questionBankId&microTopicId&saveAsNew&useAi&autoScore`，`#workForm` 序列化：公共字段 `qType`=`originType`=题型编号、`courseQuestionTypeId=0`、`systemType=1`、`content`、`answerAnalysis`、`difficulty`、`uploadEnc`（页面变量）、`continueOperate`（true 时留在新建页继续出题），题型字段见上文「题型」表；组合题另带 `typeField`、`score`，选做题带 `optionalNum`。
- 列表：`POST qbank/search`（courseid, cpi, dirId, courseIds, sw 关键词, pageNum, pageSize, qTypes, difficulty, 排序和筛选项），返回 `total`、`pageInfo`、`questionBankRelationList[].questionBank`。

### 资源中心·资料库（mooc2-ans/coursedata）
- 操作：
  - 添加资料：本地上传、云盘、添加网址、在线图书、笔记、教学资源库、跨课导入；
  - 管理：新建文件夹（`addNewFolder`）、上传文件夹、排序、回收站、删除、复制链接、复制到云盘；
  - 权限：设置是否允许下载（`setDownload` 或批量 `batchSetDownload`）、按班级设置文件夹权限（`aievaluatecheck` / `submitFolderPermissionCheck`）；
  - 统计与 AI：导出阅读记录（`exportCourseDataReader`）、AI 摘要/脑图/词云。
- **2026-11-07 改为接口上传（`upload_material`）**：不点弹窗。在页面里注入一个可见的 `<input type=file>`，`bsk upload --selector` 把文件放进去，再用页面自己的 fetch 发：
  1. `POST {ServerHost.uploadDomain}/upload/uploadNew?t&enc2&userId`（这三个参数写在资料页内联脚本里），multipart 字段 `source=1`、`file`，返回 `{url(objectId), fileType, fileSize, fileRealType, original, state:"SUCCESS"}`；
  2. `POST coursedata/adddata`，`jsonData=[{courseId, rootId(#dataId, 根目录 0), dataName, source:"1", dataSize, dataType, objectId, courseName, isOpen:"0", dataRealType}]`、courseid、cpi、microTopicId，返回 `{key:[dataId], status:true}`。
- 本地上传（界面方式，留作参考）：先点「添加资料 → 本地上传」打开弹窗（每次最多 50 个文件，单个 ≤1GB，文件名不能含特殊字符），再用 `bsk upload <「选择本地文件」的 ref> --file <路径>`。plupload 的 input 一直隐藏，直接对它上传会报 not visible。
  1. `POST mooc1/upload-ans/upload/uploadNew?t&enc2&userId`（multipart 文件，`source=1`）
  2. `POST mooc2-ans/coursedata/adddata`（`jsonData=[{courseId, rootId, dataName, …}]`, courseid, cpi, microTopicId）

### 课程管理（mooc2-ans/tcm）
- 6 个子模块：班级管理、教师团队管理、成绩权重、课程管理、操作日志、课程评审。班级管理页 `tcm/clazz-manage` 依赖外层 `tcm/course-manage` 提供 jQuery，单独打开时调用其函数会报 `$ is not defined`。
- 班级：
  - 新建：手动新建或从其他课程导入。手动新建是 `GET tcm/create-clazz?courseid&newClazzName&cpi`。
  - 其他：已结课、重命名、分配、设置、删除。删除是 `GET tcm/delete-clazz?courseid&clazzid&cpi`，删除后无法恢复。
  - 已实测：新建「[MCP测试]班级」后删除，班级列表恢复原样。
- 班级设置：读取用 `GET tcm/getclazzsetting?courseid&clazzid&cpi`（返回 HTML）。
  - 加入与退出：允许学生加入、加入须教师同意、仅限本单位学生、允许学生退课。
  - 开放报名：开放班级报名（可选 6 种 CC 协议，本校或全网开放，报名时间）。
  - 班级属性：所属学期、班级人数上限（默认 1000，可申请提高）。
  - 结课：手动结课，或按时间自动结课（需设开课时间段），结课前 N 天提醒。结课后学生无法再完成任务点、作业、测验，学习和互动数据停止统计。
  - 其他：忽略视频拖拽和窗口切换、对学生隐藏班级，可选择把设置同时应用到其他班级。
- 学生：
  - 添加：手动添加、从学生库添加（`addStudFromStuLib`）、从课程班级添加、批量导入（`importClazzStu`，有下载模板）。
  - 管理：移除（`removeStudent`，可在操作日志里恢复）、调班、学生加入申请（`codeAddClazzApplyList`）、分组管理（`toClazzGroupManage`）、导出学生名单（`exportClassStudent`）、更改学生信息（`updateStudentDataPop`）、访问日志。
  - 部分操作需要绑定手机或通过滑块验证（「请完成安全验证」），只能本人操作。
  - 学生的增删改会影响真实成员，本轮没有执行。

### 章节（新章节编辑器 mooc1/ananas2）
- 入口：
  - 章节列表页 `mooc2-ans/mycourse/tchcourse?courseid&clazzid&cpi&enc&t&ut&v`（资源中心 → 课程章节）。
  - 每个章节的操作：编辑（`toEditOld`）、学生开放设置、教师权限设置、开放（`setOpenStatus`）；顶部还有批量设置、打印、定时开放任务点提醒。
  - 编辑器地址 `mooc1/ananas2/index?courseId&knowledgeId&clazzId&cpi`，由 `mooc1/mycourse/transfer?moocId&clazzid&ut=t&refer=<编码后的编辑器地址>` 跳转进入。
  - 只读预览：`mooc2-ans/mycourse/teacherstudy?chapterId&courseId&clazzid`，内容在 `/knowledge/cards` iframe 里，和学生看到的一致。
- 目录操作（已实测）：
  - 一级目录不能编辑内容，只能加同级目录或子目录。
  - 新建：`POST mooc-ans/edit/createchapter`（courseid、name、parentid、layer、mooc2=1），默认名称是「新建目录课程」。
  - 改名：`POST mooc-ans/edit/changename`（courseid、nodeid、name、cpi）。
  - 节点悬浮菜单：重命名（`a.list_rename`）、移动到（`popMoveBnt`）、删除（`list_delete`）。
  - 其他接口：`deletechapter`、`chaptermove`、`movechapter/drag`、`importdir`、`importdirForText`（按文本批量导入目录）、`get-knowledge-list`。
- 内容卡片：
  - 每个章节可以有多个页签（「无标题」，可「+」新增、可重命名），每个页签是一张卡片。
  - 读取：`GET mooc-ans/edit/getcardlist?courseid&nodeid&cpi`，返回 `data[]`，每项有 `{id,title,description,nodeid}`；`GET mooc-ans/edit/getcard?cardid&nodeid&courseid&cpi`，同样返回 `data[]`。
  - 保存：`POST mooc-ans/edit/savecard`（title、courseId、nodeid、description=正文 HTML、attachments=JSON、id=卡片 ID，新卡为 0；可选 `?recordJson=[…]`）。编辑器切换章节或离开页面时会自动保存。
  - 其他：`deletecard`、`movecard`、`move-attachment`、`set-reuse-card`、`get-reusecard-template`、`validate-chapter-test`。
- 正文编辑器是 ProseMirror。工具栏全部选项：
  - 段落样式：正文、标题 1–6
  - 字体：宋体、楷体、微软雅黑、黑体、隶书、andale mono、arial、arial black、comic sans ms、impact、times new roman
  - 字号：9、12、14、16、18、20、24、28、32、36、42、48、56、64
  - 颜色：文字颜色、背景色
  - 对齐：左、居中、右、两端、顶部、垂直居中、底部
  - 行距：1、1.25、1.5、1.75、2、2.5、3
  - 表格：插入表格、插入行和列、合并、拆分、删除
  - 对已插入元素：下载、剪切、复制、替换、编辑、删除、全屏、预览
- **已实测：工具栏的这些格式都能用指令实现。** 正文 HTML 用行内样式写好（`<hN>`、`font-family`、`font-size`、`color`、`background-color`、`text-align`、`line-height`、`strong/em/u/s/sub/sup`、`ul/ol`、`table`、`hr`、`a`、特殊符号），调一次 `savecard`：
  - 服务端读回与写入逐字一致；
  - 只读预览页（即学生看到的页面）里 11 种字体、14 种字号、7 种行距、4 种对齐、6 级标题、列表、表格、符号全部正确显示。
- **注意**：
  - 不要在页面里用 `execCommand('insertText')` 往 ProseMirror 打字。它产生的是浏览器认定为真实的输入事件，BrowserSkill 会把标签页切到「人工控制」，Agent 之后无法再操作，只能换新会话。
  - `bsk fill` 往 ProseMirror 填写时也可能因为焦点问题失败。
  - 写正文应走 `savecard` 接口。
  - 编辑器离开页面时会弹 beforeunload 对话框。
- 可插入的内容：
  - 学习资料（17 种）：云盘、视频、图片、文档、音频、附件、本课资料、录音、图书、图书内页、链接、动画、3D 资源、智雅资源库、全景资源、资源库、扩展阅读
  - 学习任务（6 种）：章节测验、讨论、投票问卷、直播、速课、课程图谱
  - 更多：注释、文档导入
  - AI：AI 排版（通用模板 1/2、科技蓝，或自定义要求）、智能编写、AI 校正
  - **插入项的存储格式（已用「链接」实测）**：
    - 正文里插入的是一个占位块：`<div class="taskIframeWrap" data-iframeid="ID" contenteditable="false"><iframe class="taskIframe ans-module ans-<模块>-module" id="ID" module="<模块>" type="online" ywbf="1" data="<HTML 转义后的 JSON>" src="/ananas2/html/insert<模块>.html"></iframe></div>`。
    - 同一个对象还要放进 `savecard` 的 `attachments` 数组。链接的那一项是 `{"module":"hyperlink","href","target","title","type":"text|card|preview","linkType":1,"textValue","mid","jobid","_jobid"}`，其中 `jobid` 是任务点编号。
    - `getcard` 和 `getcardlist` 不返回 `attachments`。
    - 已验证：用接口写入「原正文 + 1 个链接占位块 + 1 项 attachments」后，读回正确，只读预览里链接模块正常加载。
    - **2026-11-07 对比确认**：每个插入项在 attachments 里的那一项，就是它占位块 `data` 属性里的 JSON 再加上 `"module"`。例外：链接只保留 href、target、title、type、linkType、textValue、mid、jobid、_jobid；视频多一个 `indexOrder`（它在所有占位块里的序号，从 1 开始）；图片是正文里的 `<img src=".../star4/<objectid>/origin.png" mid=… _jobid=…>`，attachments 项是 `{"module":"insertimage","name":null,"mid","_jobid","objectid"}`。服务端保存后所有占位块的 `src` 都是空的。所以 attachments 可以从正文完整重建，往已有插入项的页里追加不会丢任务点。
    - 各模块占位块的 class 后缀：ballchart、insertaudio 加 ` frame-spread`；insertdoc、insertvideo 加 ` frame-spread ans-attach-online`；insertbbs 加 ` bbsh`。type 属性：ballchart 没有，insertmicroCourse 和 work 是 `null`，其余是 `online`。
    - mid 的格式是「12 位随机数 + 13 位毫秒时间戳」，_jobid 是「毫秒时间戳 + 3 位随机数」，章节测验的 jobid 是 `work-<workid>`。
  - 「链接」弹窗：链接类型（网页链接或章节目录）、标题、网址（必填）、提示文字、在新窗口打开、显示模式（文本、卡片、预览）。插入后带「任务点」开关（默认开，学生打开链接才算完成）。
  - **注意**：用脚本修改弹窗里的表单（包括点 label 让单选框变化）会触发页面 `input` 事件，BrowserSkill 会把它算成人工操作，撤销 Agent 当前动作。弹窗表单要用 `bsk fill` / `bsk click` 按引用操作。另外，几次没完整执行的尝试叠加起来插入了 7 个重复链接，后来用接口清理掉了。
  - **逐个插入的实测记录**（弹窗一律用 `bsk fill`、`bsk click` 按引用操作，没有触发人工锁定）：

    | 插入项 | 存放方式 | 字段 / 说明 |
    |---|---|---|
    | 链接 | 占位块 + attachments | `module:hyperlink`，见上文 |
    | 注释 | **正文里的行内标记，不进 attachments** | `<a textvalue="标题" data="内容" imgs="" insertnotes="1" bgcolor="#333333" type="text" _href="javascript:void(0);" style="text-decoration: underline dotted rgb(242,140,36)">标题</a>`，插在光标处。原生标记里还有一个属性名带全角空格的 `href　=`。弹窗字段：注释标题、注释内容、附件、浮窗背景色。插入注释的工具要自己生成这段标记，不能经过正文清洗器 |
    | 讨论（插入主题讨论） | attachments，话题随 `savecard` 由服务端创建，没有单独请求 | `{"module":"insertbbs","title","detail","images":[],"endtime","replywordnum","replytimes","allowViewReply":1,"isJob","_jobid","mid"}`。弹窗字段：标题、正文、任务点开关、设置（截止时间、最少字数、回复次数、是否可看他人回复）。任务点开关的 input 被隐藏，要点它可见的外层元素 |

  - **上传类插入（2026-11-06 实测，全部插入并保存成功）**：都是先 `POST mooc1/ananas/generate-sign`，再 `POST pan-yz.chaoxing.com/upload/v2/uploadfile`（存到云盘「课程/<课程名>/章节」）。上传控件的 input 被裁成 1px，上面盖着一个 `LABEL`，要对这个 label 执行 `bsk upload`。
    - **2026-11-07 接口版（`insert_chapter_file`）**：不打开章节编辑器（编辑器离开页面会弹 beforeunload，卡住下一次导航），在 mooc1 静态页上完成：`GET /mooc-ans/edit/get-course-info?courseId&clazzId`（和编辑器的 `window.info` 一样，含 uploadParam.uploadEnc/uploadTimeStamp、userInfo.uid、courseInfo.courseName）→ `GET /ananas/getTk`（`data.tk`，可能是空串，照传空串；传字面量 "undefined" 会报参数校验错误）→ `POST /ananas/generate-sign`（`params`=下一步表单字段 m 的 JSON：`_token, d:"/Upload-Files/", puid, hqsd:1, destPathArr:["课程",课程名,"章节"], name, type, lastModifiedDate, size`；`enc`、`t`）返回 appid、timestamp、nonce、signature、_from、lastModifiedDate → `POST pan-yz/upload/v2/uploadfile`（m + file + 签名字段），返回 `data.objectId/size/suffix`。文档再查 `GET /ananas/status/<objectid>` 取 `pagenum`。然后按下表拼插入项，和其他插入项一样追加到卡片。
    | 插入项 | 支持格式 | attachments 项 |
    |---|---|---|
    | 图片 | gif jpeg png jpg svg bmp tif（来源：本地、云盘、课程资料、图片地址） | 正文里是行内 `<img src="https://p.cldisk.com/star4/<objectid>/origin.png" objectid=… size=…>`；attachments 里是 `{"module":"insertimage","objectid","mid","_jobid"}` |
    | 文档 | doc docx ppt pptx pdf xlsx xls | `{"module":"insertdoc","objectid","name","type","size","hsize","title","pagenum","mid","jobid","_jobid"}`，带任务点 |
    | 音频 | aac ac3 aif amr ape asf flac m4a mp3 ogg wav… | `{"module":"insertaudio","objectid","name","type","size","hsize","title","mid","jobid","_jobid"}`，带任务点 |
    | 附件 | 所有格式 | `{"module":"downloadfile","objectid","name","type","size","hsize","src","_src","title","mid"}`，**不带任务点** |
    | 视频 | rmvb 3gp mpg mov wmv avi mkv mp4 flv vob f4v（另有「在线视频」） | `{"module":"insertvideo","objectid","name","type","size","hsize","title","mid","jobid","_jobid","fastforward","doublespeed","indexOrder"}`，带任务点 |
  - **其余插入项的弹窗字段（已打开记录）**：
    - 章节测验：创建新测验（输入标题后去编辑题目），或从作业库选择。
    - 投票问卷：可加单选、多选、简答、判断题，或从问卷库选题；每题可设必答；整体可设允许参与者查看统计、匿名、活动时长。
    - 直播：创建新直播或从个人直播间选择；直播方式有手机 App、直播客户端、OBS；学生在章节里观看直播才算完成任务点。**没有实际创建**，因为会在个人直播间里真的生成一个直播。
    - 速课：从「全部速课」列表里选。
    - 课程图谱：选择知识点（「助手」里暂时没有知识点）。
    - 本课资料：从课程资料库里选，插入后是 `downloadfile` 模块。
    - 录音：需要麦克风，Agent 环境用不了。
    - 图书：按书名或作者搜索在线图书。
    - 图书内页：弹窗标题是「插入知识点」。
    - 动画：只支持 swf，可本地、云盘、课程资料来源，电脑和移动端都不能原位播放。
    - 3D 资源、智雅资源库：弹窗一直在加载。
    - 全景资源：上传全景资源或选择已有资源，可选资源类型。
    - 资源库：提示「未检查到用户登录信息」。
    - 扩展阅读（组件「相关知识」）：按关键词搜索期刊、图书、报纸。
    - 文档导入：本地、云盘、课程资料。
    - 2026-11-07 补做并保存成功：
      - 本课资料：`downloadfile`，objectid 来自课程资料库；
      - 速课：`{"module":"insertmicroCourse","url","title","cover","jobid","_jobid","mid"}`，带任务点；
      - 扩展阅读：`{"module":"ballchart","keyword","mid"}`；
      - 章节测验：选「创建新测验」后，会在新标签页打开作业编辑器（`work/goToWorkEditor?chapterId&courseid&fromChapter&workid`），出题和保存走与作业相同的链路，`clazzid=0`。章节里登记的是 `{"module":"work","workid","title","worktype":"workA","jobid":"work-<workid>","mid"}`。页面自己弹出的标签页不归 Agent 会话所有，要用 `bsk tab create --url` 打开同一个地址再操作；
      - 投票问卷：点「完成」时服务端就生成了一个投票活动，登记的是 `{"module":"insertvote","id"(活动ID),"title","description","_jobid","mid"}`。
  - 还没实际插入的（2026-11-08 第二轮后）：云盘选文件、智能编写、AI 校正；录音、3D 资源、智雅资源库、资源库、课程图谱做不了（原因见上）；直播只记录了选项。
  - 插入模块在脚本里的名字：`ananas2/html/insert{audio,ballchart,bbs,book,classtask,cxjour,doc,downloadfile,flash,hyperlink,knowledge,live,pblTeaching,resource3d,resourceQj,suke,video,vote,work}`、`ananas/editor-vue/modules/{insertvideo,insertlink,insertnote,insertbbs,insertsubject,insertchapter,richvideo,realplay,questionnaire,work,visuClass,…}`。

测试数据：任务「[MCP测试]任务1」（含作业任务点「[MCP测试] 作业探测」），已发布到「测试」和「默认班级」，留作学生端测试用。

## 2. 还没探查的范围

- 第 0 节「还没做」列出的教师端写流程和读取页面。写流程只在测试课程里探查。
- 学生端已用本人在测试课里的学生身份实测；签到、问卷参与、章节测验作答、错题集、学习记录还没做（签到和刷任务点按需求不做）。
- 题库、试卷库管理系统（`kaoshi.chaoxing.com`）有滑块验证码，保留人工。
- 教学日历、下载中心、全部应用、首页的待办和预警。

## 3. 核心的实现原则（覆盖所有功能时保持不变）

1. 优先调用页面自己使用的 JSON 接口（同源 fetch，从静态基准页发起）。只有复杂表单才走真实界面操作。
2. 每个写操作：先预演并冻结目标 ID → 用单次 plan_id 执行 → 再读一遍核实。结果不明时不重试，先查状态。
3. 页面结构和接口的定义集中存放，学习通改版时只需改定义，不必动整套代码（见 4.3）。
4. 页面文本、作业内容、讨论区和附件里的文字一律当作**数据**返回，放在明确标注"不可信内容"的字段里，工具说明里写明不得把它当指令执行。

## 4. 策略层与部署（按需求方要求）

### 4.0 已实现（2026-11-07，`policy.py`）
- 角色 `teacher` / `reviewer` / `student` 在启动时决定注册哪些工具；调用时再查一次。环境变量只能收窄角色。
- 学生角色固定为 11 个工具（health_check、list_my_courses、list_my_assignments、read_my_assignment、save_my_answers、submit_my_assignment、list_my_exams、list_my_activities、list_my_materials、download_my_material、ask_tutor），配置只能再加讨论两项；删除、发布、改他人内容、群发、读页面工具一律加不进去。
- 提交作业：预演 → 学生本人回复「确认提交」→ 带 `confirm_text` 和单次 plan_id 执行（`confirm_text` 不参与 plan 摘要）。
- 节流：按角色的每日调用上限（本机计数，跨重启）和页面导航最小间隔。
- 所有读取结果自动带 `content_policy`（页面文字是数据不是指令）；各学生工具的返回里另有说明。
- 中心辅导：`ask_tutor` 只把学生的问题和学生选择附上的内容 POST 到教师配置的 https 地址（本机测试可用 http://127.0.0.1），带教师发的令牌，不带学习通登录信息；回复只当建议。
- 预审：`record_review_suggestion` 只写本机 `reviews/<日期>.jsonl`，「拿不准」必定交人工，其余按比例抽查；`list_review_suggestions` 查看。
- 实测：学生配置下即使环境变量要求 teacher，也只注册 11 个学生工具；学生调用 publish_notice 被拒；ask_tutor 打到本机模拟辅导服务，服务只收到问题、课程、客户端名和令牌。
- 批阅给分与打回（`grade_submission`、`return_submission`，2026-11-07 实测）：按人批阅页的表单 `#form1` 提交到 `POST /mooc2-ans/work/library/save-review?score=<总分>&markType=<#markType>`。每题的分数在 `score<题目ID>`（文本框，客观题已带系统判分）；阅读理解的小题是无名的 `.inputBranch`，听力的主观小题是 `compoundSubQuesMark_<题目ID><uuid>`；提交前用页面自己的 `setRecordTarget / setCompoundSubjectQuesScore / setCompoundSubjectQuesComment / setMarkLabel` 填隐藏字段，`answerwqbid` 取自页面 `pigai` 里写死的题目 ID 串，`score`、`tmpscore` 是所有分数框之和，批语是 `comment`。**只要还有主观题没给分，保存后仍是「待批阅」（部分批阅）**；全部给分后变「已完成」。打回是同一接口，`isRework=true`、`score=0`、`reason=理由`。实测：先给 4 题打分（读回 3/4/2.5），作业仍待批阅且工具列出未给分的题；补齐后总分 62/120、状态「已完成」；再打回，已交列表清空，学生端显示「待重做」。
- 预审读作答（`read_student_answers`，教师和 reviewer 角色，学生角色加不进去）：已交名单 `work/mark-list?…&submit=true` 每行 `ul.dataBody_td[id=workAnswerId]` 带「批阅」链接 `work/library/review-work?courseid&clazzid&workId&workAnswerId&…`（按人批阅）；每题一个 `.mark_item1[id=index_N]`，组合题里嵌套小题块，文本里有「学生答案…」「正确答案…」，`.mark_name` 是「N. (题型, 分值) 题干」。2026-11-07 用 reviewer 角色实测：全题型作业 22 题逐题读出学生答案和参考答案（阅读理解带 2 道小题），结果带 untrusted 说明；随后记录两条预审建议，「拿不准」必定交人工；reviewer 调用 publish_notice 被拒。

### 4.1 角色配置（规则放在 MCP 里，不放在提示词里）
- 服务端配置 `profile = teacher | student | reviewer`。启动时只注册该角色允许的工具，不允许的工具根本不出现在工具列表里。
- **学生配置只开放**：查任务、查截止时间、下载资料、带确认的提交。不开放：读取标准答案或测验答案、删除、修改他人内容、批量发消息。
- 学生提交：只接受学生本人的文件或原文 → 返回完整预览 → 学生回复"确认提交"（服务端校验确认文本和单次 plan_id）后才执行。
- 教师端预审 agent：作业内容只作为数据传入，结论只作建议。"拿不准"的分类和抽查照常执行。

### 4.2 中心辅导服务
- "辅导"和"掌握判断"做成教师部署的中心服务，学生端 MCP 只提供一个调用它的工具。规则和日志都在教师手里，学生改不了。学生的学习通凭据不经过这个服务。

### 4.3 打包与更新
- **2026-11-07 已实现（v0.3.0）**：`scripts/install.ps1`、`scripts/install.sh` 安装发布标签（文件清单校验、虚拟环境、锁定依赖、默认 student 角色配置、自检）；`update` / `update --check` / `update --to` / `rollback` / `schedule`（见 README）。
- 本机端到端实测：用本仓库的本地裸库打 v0.3.0 标签，安装脚本装好后 `update --check` 发现 v0.3.1，`update` 升级成功（清单校验、自检通过），`rollback` 回到 0.3.0；再发布一个改过文件却沿用旧清单的 v0.3.2，`update` 报「内容不符 server/xuexitong_mcp/policy.py」并自动回到 0.3.0，工作区干净。
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
| P3 ✅ | 学生端读写（作业全题型作答与确认提交、考试和活动列表、资料下载、讨论回复）；签到和考试作答按需求不做 | 已用本人在「助手」里的学生身份实测 |
| P4 ✅ | 策略层（角色配置、确认提交、不可信内容标注）、节流、打包和一键更新 | 发布前需教师在 GitHub 打版本标签 |
| P5 | 3–5 名学生小范围试用，降低频率并观察风控 | 试用名单 |
