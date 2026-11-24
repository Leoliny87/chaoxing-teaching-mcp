# 课程建设读写工具

以下入口共用 MCP 的教师身份、课程写入范围及写入预演机制。课程名重复时传入原生课程 ID。文件上传沿用配置中的本地目录和文件摘要检查。

| 教学工作 | 读取与核验 | 修改与保存 |
| --- | --- | --- |
| 章节、工单和章节测验 | 原有章节目录、卡片与任务点读取工具 | 原有章节编辑、原生测验和题库工具。已有任务点的卡片可用 `patch_chapter_card` 追加图文、定点改字和更新资源链接 |
| 知识点正文 | `read_knowledge_bodies` 从教师编辑器解析原生 ID，逐张返回正文和附件数 | `fill_knowledge_bodies` 每批最多 40 个知识点，逐点回报。已有正文与附件受保护 |
| 章节、图谱及思政归属 | `get_point_chapter_links`、`get_rendered_point_chapter_links`、`get_resource_point_links`、`get_graph_point_card_display` | `add_point_chapter_links`、`add_resource_point_links`、`set_graph_point_card_display`、`set_point_ideology_membership`。原有工具管理知识点、能力目标、问题图谱、标签及题目关联 |
| 课程门户 | `get_course_branding`、`get_portal_articles` | `set_course_branding_file` 分别更新课程封面、标志、门户背景、片花。`edit_portal_article` 更新已有叶子栏目 |
| 原生展厅 | `get_exhibit_form`、`get_course_exhibit`。参观端可读取导览站点、展板坐标、文字和媒体 ID | `save_exhibit_form` 暂存模板、讲解词、亮点和媒体。`publish_exhibit_form` 提交重建，平台可能覆盖手工展板。`edit_course_exhibit_item` 调整展板或站点，`add_exhibit_panel_image` 在指定位置新增独立配图 |
| 三维模型、全景和素材 | `get_teaching_model` 读取门户栏目链接的模型及热点。`verify_panorama_image` 和 `verify_exhibit_media` 核验资源实际字节、摘要及媒体信息 | `upload_course_asset` 上传素材并取得可复用的原生文件 ID。`edit_teaching_model` 修改 GLB、封面、热点、相机或演示设置。原有 `upload_panorama` 及章节资源工具负责全景发布和挂载 |
| AI 助教与实践 | `list_assistant_faq`、`list_assistant_libraries`、`list_assistant_documents`、`read_assistant_document_segments` | `add_assistant_faq`、`save_assistant_library`、`set_assistant_library_pinned`、`upload_assistant_document`、`edit_assistant_document_segment`、`create_course_practice_draft`。已有任务点工具负责挂载实践 |

首次建模可用 `list_teaching_model_library` 查看当前教师的模型，`upload_teaching_model` 导入独立 GLB 文件，`get_teaching_model_preview` 核对公开预览入口。

## 核验方式

读取知识点正文需要教师界面提供的编辑器网址及原生知识点 ID。链接记录、学生布局中的渲染结果和实际学生身份访问是不同的验证层级。展厅的提交回执仅表示平台收到重建请求，发布后可用 `get_course_exhibit(public=true)` 核对参观端，再用媒体工具核对文件。课程设置、模型及展板返回的修订摘要用于发现预演后发生的并发修改。

自动化测试使用合成内容。新工具上线时，可先对指定课程调用读取工具及写入预演，再用专用测试课程验证真实保存。课程正文、媒体、账号配置和浏览器会话不属于源码发布包。
