"""Course AI assistant authoring through its native FAQ and knowledge-library pages."""

from __future__ import annotations

import json
import re
import shutil
from urllib.parse import urlencode, urlsplit

from .ops_course_graph_authoring import digest, numeric
from .ops_reads import ROBOT
from .ops_upload import MAX_BYTES, safe_name
from .xxt import M1, M2, XxtError

_DOM = """
const shown=e=>!!e && !!e.getClientRects().length;
const shownAll=(sel,root=document)=>[...root.querySelectorAll(sel)].filter(shown);
const txt=e=>(e?.innerText||'').trim();
const one=a=>a.length===1?a[0]:null;
const exact=(sel,t,root=document)=>one(shownAll(sel,root).filter(e=>txt(e)===t));
const dialog=one(shownAll('.el-dialog'));
const libraryCard=id=>one(shownAll('.lib-card').filter(e=>record(e)?.id!=null && String(record(e).id)===id));
function record(e){const label=e?.querySelector('.lib-desc-title');let n=label||e;
 while(n&&!n.__vue__)n=n.parentElement;
 for(let v=n?.__vue__;v;v=v.$parent)if(v.cardDetail)return v.cardDetail;return null}
function popup(b){if(!b)return false;b.click();b.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true}));return true}
"""
_LIB = """return shownAll('.lib-card').map(e=>{const v=record(e);if(!v?.id || !v.baseName)throw Error('knowledge library');
 return {id:String(v.id),name:v.baseName,description:v.description??null,pinned:txt(e).includes('已置顶')};});"""
_DOC = """const el=document.querySelector('.el-table'), vm=el?.__vue__;let v=vm;
 while(v&&!Array.isArray(v.tableData))v=v.$parent;if(!v)throw Error('document list');
 return v.tableData.map(r=>({name:r.fileName,segments:r.segmentNum??null,status:r.stateName||r.state||'',
     id:String(r.id??''),resource_type:r.fileType||''}));"""
_FAQ = r"""return shownAll('.el-table__body-wrapper tbody tr').map(row=>{
 const tab=row.closest('.el-table'),h=[...(tab?.querySelectorAll('.el-table__header-wrapper th')||[])];
 const col=h.findIndex(cell=>txt(cell)==='问答'),qa=row.cells[col];
 if(!qa)throw Error('问答列未找到');
 return {cells:[...row.cells].map(e=>txt(e)),qa_cell:txt(qa)};});"""
_SEG = """return shownAll('.slice-card').map(el=>({id:el.id,text:txt(el.querySelector('.slice-card__body'))}));"""
_PAGER = r"""const pager=one(shownAll('.el-pagination'));
 const page=pager?.querySelector('.el-pager .active,.el-pager .is-active');
 const next=pager?.querySelector('.btn-next');
 const raw=txt(pager?.querySelector('.el-pagination__total'));
 return {current:page?Number(txt(page)):1,total:raw.match(/\d+/)?.[0]??null,
 more:!!next&&!next.disabled&&!next.classList.contains('disabled')};"""


def validate_text(s, name, limit, allow_empty=False):
    if (
        not isinstance(s, str)
        or not allow_empty
        and not s.strip()
        or "\x00" in s
        or len(s.encode("utf-16-le")) // 2 > limit
    ):
        raise XxtError(f"{name}无效或超过 {limit} 字。")
    return s


class Workbench:
    def __init__(self, api, c):
        self.api = api
        self.c = c
        self.origin = ""

    def open(self):
        url = (
            "https://"
            + M1
            + "/course/isNewCourse?"
            + urlencode(
                {
                    "courseId": numeric(self.c.id),
                    "cpi": numeric(self.c.cpi),
                    "v": 6,
                    "edit": "true",
                }
            )
        )
        self.api.b.navigate(url)
        pre = """const u=new URL(location.href);
          if(u.origin!==%s || (u.searchParams.get('courseid')||u.searchParams.get('courseId'))!==%s)return false;
        """ % (json.dumps("https://" + M2), json.dumps(str(self.c.id)))
        app = """const frames=[...document.querySelectorAll('iframe')].map(f=>f.contentDocument).filter(Boolean);
          const apps=frames.flatMap(d=>[...d.querySelectorAll('.application-name')]).filter(e=>
            e.textContent.trim()==='AI知识库' && e.getClientRects().length);"""
        if not self.api.wait_for(pre + "return !!document.querySelector('iframe');"):
            raise XxtError("无法打开选定课程的教师首页。")
        available = self.api.here(pre + app + "return apps.length===1;")
        if not available:
            self.api.here(
                pre
                + "const e=[...document.querySelectorAll('p')].find(x=>x.innerText==='首页' && x.offsetWidth);if(e)e.click();return !!e;",
                retry_safe=False,
            )
        if not self.api.wait_for(pre + app + "return apps.length===1;"):
            raise XxtError("当前课程首页没有可用的 AI知识库。")
        if not self.api.here(
            pre + app + "if(apps.length!==1)return false;apps[0].click();return true;",
            retry_safe=False,
        ):
            raise XxtError("无法打开课程 AI知识库。")
        link = self.api.wait_for(
            pre
            + """const a=[...document.querySelectorAll('iframe')].map(f=>f.src).filter(s=>{
          const u=new URL(s,location.href);return u.origin===%s && u.pathname==='/v1/front/goCourseKnowledgeBase';});
          return a.length===1 && a[0];"""
            % json.dumps("https://" + ROBOT)
        )
        if not isinstance(link, str):
            raise XxtError("课程未提供唯一的知识库入口。")
        u = urlsplit(link)
        if (
            u.scheme != "https"
            or u.netloc != ROBOT
            or u.path != "/v1/front/goCourseKnowledgeBase"
        ):
            raise XxtError("知识库入口与课程不匹配。")
        self.api.b.navigate(link)
        origin = self.api.wait_for(r"""return location.protocol==='https:' && /(^|\.)chaoxing\.com$/.test(location.hostname)
          && location.pathname.startsWith('/scopeLink/') && document.body.innerText.includes('我的知识库') && location.origin;""")
        if not isinstance(origin, str) or not re.fullmatch(
            r"https://(?:[a-z0-9-]+\.)+chaoxing\.com", origin
        ):
            raise XxtError("课程 AI 知识库工作台未加载。")
        self.origin = origin
        self.js(
            "return !!exact('button','新增知识库') && !shownAll('.el-loading-mask').length && "
            "(shownAll('.lib-card').length>0 || /共\\s*0\\s*条/.test(document.body.innerText));",
            wait=True,
        )

    def js(self, body, data=None, *, wait=False, action=False):
        if not self.origin:
            raise XxtError("工作台未打开。")
        script = (
            "if(location.origin!=="
            + json.dumps(self.origin)
            + "||!location.pathname.startsWith('/scopeLink/'))return false;const arg="
            + json.dumps(data, ensure_ascii=False)
            + ";"
            + _DOM
            + body
        )
        result = (
            self.api.wait_for(script)
            if wait
            else self.api.here(script, retry_safe=not action)
        )
        if result is False or result is None:
            raise XxtError("工作台页面未及时返回，或控件、目标已变化。请重新读取核对。")
        return result

    def click(self, expression, data=None):
        # Split UI readiness from the non-retried click.
        self.js("return !!(" + expression + ");", data, wait=True)
        self.js(
            "const e=("
            + expression
            + ");if(!e||e.disabled)return false;e.click();return true;",
            data,
            action=True,
        )

    def faq(self):
        self.click(
            "one(shownAll('a,span,p').filter(e=>!e.childElementCount && txt(e)==='问答库'))"
        )
        self.js(
            "return !!exact('button','添加问答') && !!document.querySelector('.el-table');",
            wait=True,
        )

    def documents(self, lib):
        self.click("libraryCard(arg)?.querySelector('.lib-desc-title')", lib)
        self.js(
            "return !!exact('button','新增文件') && !!document.querySelector('.el-table');",
            wait=True,
        )

    def rows(self, kind):
        query = {"libraries": _LIB, "documents": _DOC, "faq": _FAQ, "segments": _SEG}[
            kind
        ]
        return self.js(query)

    def page(self, kind, number=1, find=None):
        if not isinstance(number, int) or not 1 <= number <= 1000:
            raise XxtError("页码须在 1 至 1000 之间。")
        while True:
            pager = self.js(_PAGER)
            self.js("return !shownAll('.el-loading-mask').length;", wait=True)
            rows = self.rows(kind)
            if not isinstance(rows, list) or not isinstance(pager, dict):
                raise XxtError("读取课程知识库分页失败。")
            if not rows and (pager["total"] is None or int(pager["total"]) != 0):
                raise XxtError("列表行尚未完整读取，请稍后重试。")
            if find is not None:
                matches = [r for r in rows if find(r)]
                if matches:
                    if len(matches) != 1:
                        raise XxtError("同一页上有多个匹配项。")
                    return matches[0]
            elif pager["current"] == number:
                return {
                    "page": number,
                    "total": int(pager["total"])
                    if pager["total"] is not None
                    else None,
                    "has_more": pager["more"],
                    "items": rows,
                }
            if not pager["more"]:
                if find is not None:
                    return None
                raise XxtError("该页不存在。")
            current = pager["current"]
            if not isinstance(current, int) or current >= 1000:
                raise XxtError("无法继续核对分页。")
            self.click("one(shownAll('.el-pagination .btn-next'))")
            self.js(
                "const p=one(shownAll('.el-pagination .el-pager .active,.el-pagination .el-pager .is-active'));"
                "return Number(txt(p))===arg && !shownAll('.el-loading-mask').length;",
                current + 1,
                wait=True,
            )
            # Element pagination highlights the next page before an async data load is complete.
            self.js(
                "const rows=(()=>{"
                + {"libraries": _LIB, "documents": _DOC, "faq": _FAQ, "segments": _SEG}[
                    kind
                ]
                + "})();return JSON.stringify(rows)!==JSON.stringify(arg);",
                rows,
                wait=True,
            )

    def library(self, lib):
        row = self.page("libraries", find=lambda r: r["id"] == lib)
        if not row:
            raise XxtError("课程知识库 ID 不存在。")
        return row

    def document(self, lib, name):
        self.library(lib)
        self.documents(lib)
        row = self.page("documents", find=lambda r: r["name"] == name)
        if not row:
            raise XxtError("该知识库中没有指定文件。")
        return row

    def segments(self, lib, name):
        self.document(lib, name)
        self.click(
            """(()=>{const rows=shownAll('.el-table__body-wrapper tbody tr').filter(e=>
          [...e.cells].some(td=>txt(td).split(/\\n/).map(s=>s.trim()).includes(arg)));return exact('a,span','编辑',one(rows)||document.createElement('div'))})()""",
            name,
        )
        self.js(
            "return location.pathname.endsWith('/doceditor') && document.body.innerText.split('返回上一级')[1]?.trim().split('\\n')[0]===arg && !!document.querySelector('.slice-card');",
            name,
            wait=True,
        )


def faq_lines(row):
    return [line.strip() for line in row["qa_cell"].splitlines() if line.strip()]


def faq_match(row, title):
    lines = faq_lines(row)
    return bool(
        lines and lines[0].removeprefix("问：").removeprefix("问题：").strip() == title
    )


def faq_has_answer(row, answer, question):
    if not faq_match(row, question):
        return False
    body = " ".join(faq_lines(row)[1:]).removeprefix("答案：").removeprefix("答：")
    return " ".join(body.split()) == " ".join(answer.split())


def synced(old, new):
    if not new or old != new:
        raise XxtError("与预演状态不一致，请重新读取后预演。")


def register_assistant_authoring(
    tool, client, check_write, dry, check_upload_path, upload_preview_digest
):
    def open_(course, write=False):
        api = client()
        c = api.ctx(check_write(course).id if write else course)
        w = Workbench(api, c)
        w.open()
        return w

    @tool("read", "按页读取本课程 AI助教问答库，返回原生表格各行内容。")
    def list_assistant_faq(course: str, page: int = 1) -> dict:
        w = open_(course)
        w.faq()
        return w.page("faq", page)

    @tool(
        "write",
        "在课程 AI助教问答库新增一条问答，保留同题原答案，核对提交后的完整答案。",
    )
    def add_assistant_faq(
        course: str,
        question: str,
        answer: str,
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        q = validate_text(question, "问题", 500)
        if "\n" in q or "\r" in q:
            raise XxtError("问题需在一行内填写。")
        a = validate_text(answer, "答案", 10000)
        w = open_(course, True)
        w.faq()
        found = w.page("faq", find=lambda r: faq_match(r, q))
        if found and not faq_has_answer(found, a, q):
            raise XxtError("已有同名问题且答案不同。")
        stamp = digest([q, a, found])
        if not confirm:
            return dry(
                w.c,
                "新增课程 AI助教问答",
                bind={"source_digest": stamp},
                question=q,
                answer=a,
                exists=bool(found),
            )
        synced(stamp, source_digest)
        if found:
            return {"ok": True, "created": False, "question": q}
        w.click("exact('button','添加问答')")
        editor = """const form=one(shownAll('.el-form').filter(f=>f.querySelector('.el-form-item input[type=text]')));
          const e=form?.querySelector('.el-form-item input[type=text]');
          const ed=Object.values(window.UE?.instants||{}).find(i=>i.isReady&&i.body?.isConnected);"""
        w.js(editor + "return !!e && !!ed;", wait=True)
        w.js(
            editor
            + """if(!e||!ed)return false;e.value=arg[0];e.dispatchEvent(new Event('input',{bubbles:true}));e.blur();
          const p=document.createElement('p');p.textContent=arg[1];ed.setContent(p.outerHTML,false);
          ed.fireEvent('contentChange');ed.fireEvent('blur');return e.value===arg[0]&&ed.getContentTxt()===arg[1];""",
            [q, a],
            action=True,
        )
        w.click("exact('button','确定',dialog||document)")
        w.js("return !dialog && !!exact('button','添加问答');", wait=True)
        w.open()
        w.faq()
        result = w.page("faq", find=lambda r: faq_match(r, q))
        if not result or not faq_has_answer(result, a, q):
            return {
                "ok": False,
                "write_outcome": "unknown",
                "question": q,
                "error": "问答提交后未能完整回读，请先查问答库再重试。",
            }
        return {"ok": True, "created": True, "question": q}

    @tool("read", "按页读取课程 AI 知识库原生 ID、名称和置顶状态。")
    def list_assistant_libraries(course: str, page: int = 1) -> dict:
        return open_(course).page("libraries", page)

    @tool("read", "按页读取课程 AI 知识库中的文档、处理状态及分片数量。")
    def list_assistant_documents(course: str, library_id: str, page: int = 1) -> dict:
        w = open_(course)
        w.library(library_id)
        w.documents(library_id)
        return w.page("documents", page)

    @tool("read", "从原生文档编辑页按页读取知识库分片 ID、正文和总数。")
    def read_assistant_document_segments(
        course: str, library_id: str, filename: str, page: int = 1
    ) -> dict:
        w = open_(course)
        w.segments(library_id, filename)
        return w.page("segments", page)

    @tool(
        "write",
        "在指定课程 AI 知识库内上传经预演校验的文档，保留同名文件，核对文件列表。",
    )
    def upload_assistant_document(
        course: str,
        library_id: str,
        file_path: str,
        confirm: bool = False,
        file_sha256: str = "",
    ) -> dict:
        src = check_upload_path(file_path)
        if not 0 < src.stat().st_size <= MAX_BYTES:
            raise XxtError("文件为空或超过 1GB。")
        name = safe_name(src.name)
        w = open_(course, True)
        w.library(library_id)
        w.documents(library_id)
        if w.page("documents", find=lambda r: r["name"] == name):
            raise XxtError("知识库已有同名文件。")
        if not confirm:
            fp = upload_preview_digest(src)
            return dry(
                w.c,
                "上传 AI 知识库文件",
                bind={"file_path": str(src), "file_sha256": fp["sha256"]},
                library_id=library_id,
                filename=name,
                **fp,
            )
        tmp, snap, meta = w.api._snapshot(str(src), file_sha256)
        try:
            w.js("return popup(exact('button','新增文件'));", action=True)
            w.click("exact('li','本地上传')")
            w.js(
                "return !!dialog && !!dialog.querySelector('.el-upload-btn-dropdown button');",
                wait=True,
            )
            w.js(
                "return popup(dialog?.querySelector('.el-upload-btn-dropdown button'));",
                action=True,
            )
            selector = w.js(
                """const b=exact('li','选择文件');if(!b||b!==b.parentElement.firstElementChild
              || !/^dropdown-menu-[A-Za-z0-9_-]+$/.test(b.parentElement.id))return false;
              return '#'+b.parentElement.id+' li:first-child';""",
                wait=True,
            )
            w.api.b.upload_selector(selector, str(snap))
            w.js(
                "return !!dialog && txt(dialog).includes(arg) && txt(dialog).includes('上传成功');",
                meta["name"],
                wait=True,
            )
            w.click("exact('button','完成',dialog||document.createElement('div'))")
            w.js("return !dialog;", wait=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        w.open()
        row = w.document(library_id, name)
        return {"ok": True, "file": row, "sha256": file_sha256}

    @tool(
        "write",
        "新增课程 AI 知识库，或按 ID 修改名称和描述。保留解析和分片策略，回读编辑框核对。",
    )
    def save_assistant_library(
        course: str,
        name: str,
        description: str = "",
        library_id: str = "",
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        name = validate_text(name, "知识库名称", 100)
        description = validate_text(description, "知识库描述", 350, allow_empty=True)
        w = open_(course, True)
        conflict = w.page(
            "libraries", find=lambda r: r["name"] == name and r["id"] != library_id
        )
        if conflict:
            raise XxtError("课程内已有同名知识库。")
        w.open()
        fields = """const title=dialog?.querySelector('input[placeholder="请输入知识库名称"]'),desc=dialog?.querySelector('textarea');"""

        def form(target):
            if target:
                w.library(target)
                library_menu(w, target, "设置")
            else:
                w.click("exact('button','新增知识库')")
            return w.js(
                fields + "return !!title && !!desc && [title.value,desc.value];",
                wait=True,
            )

        before = form(library_id)
        stamp = digest([library_id, before, name, description])
        if not confirm:
            return dry(
                w.c,
                "编辑课程 AI 知识库" if library_id else "新增课程 AI 知识库",
                bind={"source_digest": stamp},
                before=before,
                name=name,
                description=description,
            )
        synced(stamp, source_digest)
        if before != [name, description] or not library_id:
            w.js(
                fields
                + """if(!title||!desc||title.value!==arg[0][0]||desc.value!==arg[0][1])return false;
              for(const [el,value] of [[title,arg[1]],[desc,arg[2]]]){
                el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));}
              return title.value===arg[1]&&desc.value===arg[2];""",
                [before, name, description],
                action=True,
            )
            w.click("exact('button','完成',dialog||document.createElement('div'))")
            w.js("return !dialog;", wait=True)
        w.open()
        row = w.page(
            "libraries",
            find=lambda r: (
                r["name"] == name and (not library_id or r["id"] == library_id)
            ),
        )
        if not row:
            raise XxtError("知识库提交后未能回读，请核对。")
        after = form(row["id"])
        return {
            "ok": after == [name, description],
            "library_id": row["id"],
            "name": after[0],
            "description": after[1],
        }

    @tool("write", "设置课程 AI 知识库是否置顶，并重新读取知识库卡片核对。")
    def set_assistant_library_pinned(
        course: str,
        library_id: str,
        pinned: bool,
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        w = open_(course, True)
        row = w.library(library_id)
        stamp = digest([row, pinned])
        if not confirm:
            return dry(
                w.c,
                "设置课程 AI 知识库置顶",
                bind={"source_digest": stamp},
                library=row["name"],
                before=row["pinned"],
                after=pinned,
            )
        synced(stamp, source_digest)
        if row["pinned"] != pinned:
            library_menu(w, library_id, "置顶" if pinned else "取消置顶")
            w.js(
                "const e=libraryCard(arg[0]);return !!e && txt(e).includes('已置顶')===arg[1];",
                [library_id, pinned],
                wait=True,
            )
            w.open()
            row = w.library(library_id)
        return {"ok": row["pinned"] == pinned, "library": row}

    @tool(
        "write",
        "按知识库、文件及原生分片 ID 替换一个分片的正文，对比原文并重新打开编辑器核对。",
    )
    def edit_assistant_document_segment(
        course: str,
        library_id: str,
        filename: str,
        segment_id: str,
        text: str,
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        text = validate_text(text, "分片正文", 100000)
        w = open_(course, True)
        editor = """const card=one(shownAll('.slice-card').filter(e=>e.id===arg));
          let el=card?.querySelector('pre[contenteditable=true]');while(el&&!el.__vue__)el=el.parentElement;
          let vm=el?.__vue__;while(vm&&!vm.vditor)vm=vm.$parent;"""

        def editing():
            w.segments(library_id, filename)
            row = w.page("segments", find=lambda r: r["id"] == segment_id)
            if not row:
                raise XxtError("指定的文档分片未找到。")
            w.js(
                """const e=one(shownAll('.slice-card').filter(el=>el.id===arg))?.querySelector('.slice-card__body');
              if(!e)return false;e.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));return true;""",
                segment_id,
                action=True,
            )
            return w.js(
                editor + "return vm?.vditor && {text:vm.vditor.getValue()};",
                segment_id,
                wait=True,
            )["text"]

        before = editing()
        stamp = digest([library_id, filename, segment_id, before, text])
        if not confirm:
            return dry(
                w.c,
                "修改课程知识库文档分片",
                bind={"source_digest": stamp},
                filename=filename,
                segment_id=segment_id,
                before=before,
                after=text,
            )
        synced(stamp, source_digest)
        if before != text:
            editvars = editor.replace("e.id===arg", "e.id===arg[0]")
            w.js(
                editvars
                + """const parent=vm?.$parent;
              if(!parent?.isQuickEditing||parent.readonly||!parent.fnExitQuickEditAndSave||vm.vditor.getValue()!==arg[1])return false;
              vm.vditor.setValue(arg[2]);parent.editorContent=arg[2];await parent.fnExitQuickEditAndSave();return true;""",
                [segment_id, before, text],
                action=True,
            )
            w.open()
            before = editing()
        return {"ok": before == text, "segment_id": segment_id}

    @tool(
        "write",
        "在选定课程的 AI 实践库中新建未发布的情景对话草稿，回读角色、对话要求与评分标准。",
    )
    def create_course_practice_draft(
        course: str,
        name: str,
        requirement: str,
        ai_role: str,
        student_role: str,
        dialogue: str,
        opening: str,
        criteria: list[dict],
        confirm: bool = False,
    ) -> dict:
        c = client().ctx(check_write(course).id)
        patch = practice_fields(
            name, requirement, ai_role, student_role, dialogue, opening, criteria
        )
        api = client()
        if practice_by_name(api, c, name):
            raise XxtError("课程 AI 实践库已有同名条目。")
        if not confirm:
            return dry(c, "新增课程 AI 实践草稿", practice=patch)
        q = urlencode(
            {"courseid": numeric(c.id), "cpi": numeric(c.cpi), "__from": "aiWorkbench"}
        )
        api.b.navigate(
            "https://" + M2 + "/mooc2-ans/ai-evaluate/v2/editor/select-task-type?" + q
        )
        guard = "if(location.origin!==" + json.dumps("https://" + M2) + ")return false;"
        button = "const leaves=[...document.querySelectorAll('*')].filter(e=>e.offsetWidth&&!e.childElementCount&&e.innerText==='情景对话');"
        if not api.wait_for(guard + button + "return leaves.length===1;"):
            raise XxtError("情景对话创建页未加载。")
        if not api.here(
            guard
            + button
            + "if(leaves.length!==1)return false;leaves[0].click();return true;",
            retry_safe=False,
        ):
            raise XxtError("未能选择情景对话。")
        vm = (
            guard
            + "const cid="
            + json.dumps(c.id)
            + ",cpi="
            + json.dumps(c.cpi)
            + """;let el=[...document.querySelectorAll('*')].find(
          e=>e.offsetWidth&&!e.childElementCount&&e.innerText==='保存');while(el&&!el.__vue__)el=el.parentElement;
          let v=el?.__vue__;while(v&&!v.$options.methods?.doSave)v=v.$parent;
          if(!v || String(v.courseId)!==cid || String(v.cpi)!==cpi || v.libraryUuid || v.blockOpenPlatformSave())return false;"""
        )
        if not api.wait_for(vm + "return !!v.form?.sceneChat;"):
            raise XxtError("本课程 AI 实践草稿编辑器未就绪。")
        result = api.here(
            vm
            + "const patch="
            + json.dumps(patch, ensure_ascii=False)
            + """;
          v.form.title=patch.title;v.form.requirement=patch.requirement;Object.assign(v.form.sceneChat,patch.sceneChat);
          if(!v.validateForm(false))return {ok:false};
          const base='/mooc2-ans/ai-evaluate/v2/editor/';
          const r=await J(base+'save',POST({courseid:cid,cpi,libraryUuid:'',isPublish:'false',data:JSON.stringify(v.form)}));
          if(!r?.status || typeof r.data!=='string')return {ok:false};
          const back=await J(base+'load-data?'+new URLSearchParams({courseid:cid,cpi,libraryUuid:r.data}));
          const f=back?.data,eq=(x,y)=>JSON.stringify(x)===JSON.stringify(y);
          const same=!!f && f.title===patch.title && f.requirement===patch.requirement &&
             Object.keys(patch.sceneChat).every(k=>eq(f.sceneChat?.[k],patch.sceneChat[k]));
          return {ok:!!back?.status&&same,practice_id:r.data};""",
            retry_safe=False,
        )
        if not isinstance(result, dict) or not result.get("ok"):
            raise XxtError("AI 实践草稿未能完整回读。请先查实践库再重试。")
        return {**result, "name": name, "published": False}


def library_menu(w, lib_id, title):
    w.js(
        "const b=libraryCard(arg)?.querySelector('[aria-controls]');return popup(b);",
        lib_id,
        action=True,
    )
    w.click(
        """(()=>{const b=libraryCard(arg[0])?.querySelector('[aria-controls]'),m=b&&document.getElementById(b.getAttribute('aria-controls'));
      return m && exact('li',arg[1],m);})()""",
        [lib_id, title],
    )


def practice_fields(
    name, requirement, ai_role, student_role, dialogue, opening, criteria
):
    for value, label, maxlen, optional in (
        (name, "名称", 50, False),
        (requirement, "任务要求", 2000, False),
        (ai_role, "智能体角色", 30, False),
        (student_role, "学生角色", 30, False),
        (dialogue, "对话要求", 5000, False),
        (opening, "开场白", 1000, True),
    ):
        validate_text(value, label, maxlen, optional)
    if not criteria or not isinstance(criteria, list):
        raise XxtError("需提供评分标准。")
    rows = []
    for entry in criteria:
        if not isinstance(entry, dict):
            raise XxtError("评分标准格式无效。")
        dimension = validate_text(entry.get("dimension"), "评分维度", 20)
        description = validate_text(entry.get("description"), "评分说明", 500)
        score = entry.get("score")
        if type(score) is not int or not 0 <= score <= 100:
            raise XxtError("每个维度的分值须在 0 到 100 之间。")
        rows.append(
            {"dimension": dimension, "description": description, "score": score}
        )
    return {
        "title": name,
        "requirement": requirement,
        "sceneChat": {
            "aiCharacter": ai_role,
            "userCharacter": student_role,
            "chatPrompt": dialogue,
            "prologueContent": opening,
            "scoreStandards": rows,
        },
    }


def practice_by_name(api, c, name):
    # Same native root library listing used by list_practices, with the editor's name filter.
    q = urlencode(
        {
            "courseid": numeric(c.id),
            "cpi": numeric(c.cpi),
            "isTrash": "false",
            "types": "",
            "ps": 50,
            "name": name,
            "folderId": 0,
        }
    )
    for page in range(1, 1001):
        result = api.on(
            M2,
            "return await J("
            + json.dumps(
                "/mooc2-ans/ai-evaluate/v2/library/list?" + q + "&pn=" + str(page)
            )
            + ");",
        )
        d = (
            result.get("data")
            if isinstance(result, dict) and result.get("status") is True
            else None
        )
        if not isinstance(d, dict) or not isinstance(d.get("list"), list):
            raise XxtError("课程 AI 实践库未能读取。")
        for row in d["list"]:
            if not isinstance(row, dict) or not (row.get("title") or row.get("name")):
                raise XxtError("实践库未返回可核对的条目名称。")
            if row.get("name") == name or row.get("title") == name:
                return True
        if len(d["list"]) < 50:
            return False
    raise XxtError("课程 AI 实践分页超出可核对范围。")
