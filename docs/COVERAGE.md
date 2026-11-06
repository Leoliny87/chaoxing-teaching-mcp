# 学习通新版界面功能覆盖图与实施计划

目标：**自动化核心覆盖新版学习通师生两端所有功能的读写**。"哪些角色能用哪些功能"由独立的策略层决定（见第 4 节），不在核心里砍功能。

本文的界面结构与接口来自 2026-11-06 在一台教师机上用真实登录态做的探查（BrowserSkill 0.4.2，Chrome 156）。第 1 节是只读探查。1.2 节起的写操作全部在测试课「助手」里实际执行过，测试数据都以 `[MCP测试]` 开头。接口路径只记录主机和路径，不记录签名参数和真实 ID。

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

## 1.1 学生端入口（实测）

- 「我学的课」列表：`POST mooc2-ans/visit/courselistdata`，表单参数 `courseType=1`（0 表示我教的课），返回 HTML；每门课是一个 `div.course.learnCourse`，隐藏字段含 courseId、clazzId、curPersonId。
- 测试课「助手」同时出现在「我教的课」和「我学的课」。学生身份所在的班是「测试」班。
- 学生课程入口：`mooc1/visit/stucoursemiddle?courseid&clazzid&cpi&ismooc2=1&v=2`，会跳到 `mooc2-ans/mycourse/stu`。
- 学生端模块：AI助教（`mooc1/course-ans/ai/getStuAiWorkBench`）、任务（`mobilelearn/page/active/stuActiveList`）、章节（`mooc2-ans/mycourse/studentcourse`）、讨论（groupweb topicList）、作业（`mooc1/mooc2/work/list`）、考试（`mooc1/exam-ans/mooc2/exam/exam-list`）、资料（`mooc2-ans/coursedata/stu-datalist`）、错题集（`mooc2-ans/wrongque/page`）、学习记录（`stat2-ans/study-data/index`）、课程图谱（`stat2-ans/study-knowledge/index`）。
- 学生端活动接口：`mobilelearn/v2/apis/active/student/activelist`、`v2/apis/active/getData`。

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
  1. `POST work/questionInit`（courseid, clazzid, cpi, workid=空, relationid=0, title, directoryid, grading, questionGroup, originType=3, courseQuestionTypeId）：建作业和第一题。
  2. `POST work/toEditWorkQuestion`（workid, questionid, workLibraryRelationid, type, typeName, courseQuestionTypeId, content, 判断题答案 answerForTF, score, answerAnalysis, difficulty, topicId, labelIdArr…）：写题目。
  3. `GET work/save-work?workid&title&grading&directoryid&workStatus=0&questionGroup=0`：保存。
  - 已确认 `courseQuestionTypeId=3` 表示判断题，其他题型的编号待逐一验证。
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
  2. `POST exam/add-empty-paperquestion`（paperid, relationid=客户端 uuid, qtype, courseQuestionTypeId, groupId）
  3. `GET exam/toHandAddPaperQuestion?…&qtype&questionid&edit=true`（打开题目编辑器）
  4. 每种题型有自己的保存接口，判断题是 `POST exam/editPaperTrueFalseV2`（paperid, courseid, isOpen, score, content, answer, type=3, questionId, typeId, difficulty, easy, topicId, labelIdArr, schoolTopicIds, answerAnalysis）。页面上的校验：分值大于 0、题干非空、已选答案（`.check_answer`，要原生 click 选项 `a.num_option`）。
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
- 新建：`qbank/create-question?courseid&cpi&dirId&pageNum&qbanksystem&microTopicId`，UEditor 实例 key 为 content、answerAnalysis、answerA–D。保存是 `POST qbank/add_question?courseid&questionBankId&microTopicId&saveAsNew&useAi&autoScore`，表单字段：`qType`、`courseQuestionTypeId`（单选是 0，判断是 3）、`content`、`A`/`B`/`C`/`D`、`defAnswer`（单选正确项）、`answerForTF`（判断题）、`answerAnalysis`、`difficulty`、`topicId`、`labelIdArr`、`dirId`、`uploadEnc`（页面变量）、`continueOperate`。

### 资源中心·资料库（mooc2-ans/coursedata）
- 操作：
  - 添加资料：本地上传、云盘、添加网址、在线图书、笔记、教学资源库、跨课导入；
  - 管理：新建文件夹（`addNewFolder`）、上传文件夹、排序、回收站、删除、复制链接、复制到云盘；
  - 权限：设置是否允许下载（`setDownload` 或批量 `batchSetDownload`）、按班级设置文件夹权限（`aievaluatecheck` / `submitFolderPermissionCheck`）；
  - 统计与 AI：导出阅读记录（`exportCourseDataReader`）、AI 摘要/脑图/词云。
- 本地上传：先点「添加资料 → 本地上传」打开弹窗（每次最多 50 个文件，单个 ≤1GB，文件名不能含特殊字符），再用 `bsk upload <「选择本地文件」的 ref> --file <路径>`。plupload 的 input 一直隐藏，直接对它上传会报 not visible。
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
  - 插入模块在脚本里的名字：`ananas2/html/insert{audio,ballchart,bbs,book,classtask,cxjour,doc,downloadfile,flash,hyperlink,knowledge,live,pblTeaching,resource3d,resourceQj,suke,video,vote,work}`、`ananas/editor-vue/modules/{insertvideo,insertlink,insertnote,insertbbs,insertsubject,insertchapter,richvideo,realplay,questionnaire,work,visuClass,…}`。**这些插入项还没有逐个实际添加过。**

测试数据：任务「[MCP测试]任务1」（含作业任务点「[MCP测试] 作业探测」），已发布到「测试」和「默认班级」，留作学生端测试用。

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
