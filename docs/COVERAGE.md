# 学习通新版界面功能覆盖图与实施计划

目标：**自动化核心覆盖新版学习通师生两端所有功能的读写**。"哪些角色能用哪些功能"由独立的策略层决定（见第 4 节），不在核心里砍功能。

本文的界面结构与接口来自 2026-11-06 在一台教师机上用真实登录态做的探查（BrowserSkill 0.4.2，Chrome 156）。第 1 节是只读探查。1.2 节起的写操作全部在测试课「助手」里实际执行过，测试数据都以 `[MCP测试]` 开头。接口路径只记录主机和路径，不记录签名参数和真实 ID。

## 0. 当前完成度（2026-11-07，v0.3.0）

通过真实 MCP stdio 连接实测：教师配置注册 70 个工具、学生配置 11 个，均能被 agent 调用（list_courses、list_my_assignments 实时返回数据；学生调用 publish_notice 得到 Unknown tool）。下面是按「能不能用 MCP 完成」的总览，细节见后文各节。

**已做成工具并在测试课实测**
- 课程与班级：课程列表、打开课程、模块/仪表盘/资源概览、学生名单、新建班级。
- 章节：读内容、改名、写正文（格式白名单）、插入链接/注释/讨论/扩展阅读/章节测验，以及文档、音频、视频、图片、附件五种文件。
- 作业：23 种题型新建、答题卡作业、发放（含常用设置）、提交情况、逐题读学生作答。
- 试卷与考试：22 种题型（含选做题）建卷、发布考试（含常用防作弊和查看设置）、考试批阅页人数。
- 题库：24 种题型新增、列表（不返回答案）。
- 通知：发送、删除、按 UUID 补记；讨论：发帖、列表；活动：发起普通/签到码签到、结束活动、活动结果；教学任务：新建（作业任务点）、发布；课程资料：上传、列表；成绩：读取。
- 学生端：我的课程/作业/考试/活动/资料/讨论，作业 22 种题型作答（暂存、确认提交），下载资料，回复讨论。
- 策略层与打包：三种角色、确认提交、节流、不可信内容标注、中心辅导、预审记录；安装脚本、一键更新和回退，v0.3.0 已发布。

**还没做（可以继续补）**
- 教师写：批阅给分、打回、修改已发布作业/试卷、随机组卷和平行试卷、题库编辑删除导入导出和标签文件夹、讨论置顶加精回复、问卷/评分/分组任务/随堂练习/抢答选人投票等其余活动的完整验证、教学任务的视频/文档/讨论等其余 18 类任务点、班级设置和学生增删调班、教师团队、成绩权重、资料文件夹和权限、章节新建子目录以外的移动排序。
- 章节插入：速课、投票问卷、本课资料（格式已记录，未做成工具），云盘选文件、图书、图书内页、动画、全景、文档导入、AI 排版/智能编写/AI 校正。
- 读取：首页待办和预警、学情统计各子页、AI 助教会话和知识库、教学日历、下载中心、错题集、学习记录、课程图谱。
- 只能预演、尚不执行：删除作业/考试/试卷/资料/讨论/章节、导出成绩、催交作业（删除后状态或收件人还不能可靠核实）。

**按需求不做或做不了**
- 学生考试作答、读取标准答案或测验答案（需求明确禁止；真正的考核在线下）。
- 刷章节任务点（看视频、读文档计时）这类代替学生学习的操作。
- 口语测评、录音（要麦克风现场录音）；直播（会真的开一场直播，只记录了选项）。
- 滑块验证码、短信、协议同意、登录：一律由本人处理。资源库（另一套登录）、3D 资源和智雅资源库（弹窗一直加载）、课程图谱（课程里没有知识点）暂时无法探查。

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
| 教学活动 | `mobilelearn.chaoxing.com/page/active/activeList` | `v2/apis/active/pcActivelist`、`v2/apis/class/getClassList`、`getClassDetail`、`getTeachers`、`active/getActiveLibraryOpen`、`sign/getLastSignForXd`… | list_activities、activity_result、checkin_status、end_activity、pick_student、start_quick_answer、start_vote、start_checkin(仅预演)、delete_activity | 读已验证；写需要在测试课验证；按钮：添加活动、上课、批量编辑、新建班级 |
| 资源中心 | `stat2-ans.chaoxing.com/stat2-vue/resource` | `stat2/base-data/v3/{coursewareInfo,resInfo,knowledgeInfo,workInfo,examInfo,activityLibraryInfo}`、`mooc2-ans/coursemanagev3/resource-info` | get_resource_overview、list_coursewares、list_practices、list_chapters、list_materials、upload_material、list_assignment_library、list_bank_questions、list_exams(试卷库) | 课件、题库、资料上传已覆盖；知识点、活动库待做 |
| AI助教 | `robot-lc.chaoxing.com/courseCozeV3/web` | `v1/front/conversationList`、`msgList`、`robot/info/*`、`knowledge/getAiKbSetting`… | — | 待做（读会话与知识库设置；写=对话/配置） |
| 学情统计 | `stat2-ans.chaoxing.com/stat2-vue/statistics` | `stat2/stat-nav/teach`（子菜单） | get_grades | 部分覆盖；待做：逐项统计子页 |
| 课程管理 | `mooc2-ans.chaoxing.com/mooc2-ans/tcm/course-manage` | `tcm/clazz-manage`、`tcm/clazz-student` | open_course、list_students | 读已验证；待做：添加学生、分组、导出名单、移除、班级设置 |
| 通知 | `notice.chaoxing.com/pc/course/notice/myNoticeList` | `pc/course/notice/getNoticeList` | list_notices、list_notice_inventory、publish_notice、delete_notice、reconcile_notices | 读写已实测 |
| 讨论 | `groupweb.chaoxing.com/course/topic/topicList?…bbsid` | `course/topic/{bbsid}/getTopicList`、`addTopic`、`pc/invitation/<话题>/addReplys` | list_discussions、create_discussion、delete_discussion(仅预演)、学生端 list_my_discussions / reply_my_discussion | 已修复（bbsid 取自 base-info）并实测 |
| 作业/考试（旧接口） | `mooc2-ans/work/*`、`mooc2-ans/exam/*` | — | list_assignments、submissions、list_exams、exam_marklist… | 读已验证；与"教学任务"的关系待确认 |

2026-11-06 真实只读验证通过的工具：health_check、list_courses、open_course、list_chapters、list_materials、list_notices、list_assignments、list_assignment_library、list_exams、list_activities、list_students、get_grades、list_inbox。

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
7. 接口目录（从页面脚本提取）：`createTask`、`createOrEditTask`、`deleteTaskInfo`、`taskDelete`、`swapTaskOrder`、`taskMoveToFolder`、`addNewFolder`、`reNameFolderConfirm`、`removeFolderConfirm`、`exportTask`、`getCourseImportTasks`/`confirmCourseImport`、`confirmCourseCopyTask`、`tasklabel/getTaskLabelDatas`/`saveOrDeleteTaskLabelData`、`commitPeTaskBaseInfo`、`taskStatistics/index`、`taskReference/getCourseIdClazz`。

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
  - 还没实际插入的：云盘选文件、图书、图书内页、动画、全景资源、文档导入，以及 3 个 AI 功能；录音、3D 资源、智雅资源库、资源库、课程图谱做不了（原因见上）；直播只记录了选项。
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
