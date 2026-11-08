"""章节编辑器里的「智能编写」和「AI 校正」（from ananas2/assets/Home-*.js and mooc-ans/js/courselist/aiDocCorrection.js,
probed on the test course, 2026-11-08).  Everything runs on mooc1 (the editor's origin).

智能编写   t/enc from GET /mooc-ans/edit/get-course-info -> data.aiInfo.aiWriting {aiTime, aiEnc, aiWritingChapterEnc,
           aiWritingArticleEnc}; userId = data.userInfo.uid.
           POST /ai-ans/ai/chapter/writing JSON {userId, content, writingType, t, articleTheme, articleType, hostName,
           botType (1 = 联网搜索), enc} -> an SSE stream of "data:{...}" chunks (OpenAI style choices[0].message.content
           or {type:"text", content}); with 联网搜索 the text is followed by "[textEnd]" and a JSON list of sources
           [{siteName, title, url}].
             writingType "chapter" (= 大纲):  content "<文章主题> 帮我生成一篇 <主题><类型名></文章主题>
                                              <目录结构>a;b;</目录结构><文章字数>n</文章字数>",  enc aiWritingChapterEnc
             writingType "article" (= 正文):  content "<文章主题>…</文章主题><目录结构><大纲></目录结构>
                                              <年级或对象>…</年级或对象><文章字数>n</文章字数><写作风格>a;</写作风格>",
                                              enc aiWritingArticleEnc
           The page then pastes the rendered markdown into the open card ("加入章节").
           Custom choices: GET /mooc-ans/ai/chapter-writing/get?courseId&cpi&uid&t&enc(aiEnc) -> data[{id, type
           (1 文章类型 / 2 目录结构 / 3 写作风格), optionName, optionDescription}]; POST …/save {type, courseId, cpi, uid,
           t, enc, optionName[, optionDescription]} -> {id}; POST …/delete {id, courseId, cpi, uid, t, enc}.
AI 校正    text: POST /mooc-ans/edit/ai-correction {courseId, knowledgeId, cardId, cpi, content (≤1000 chars of the
           card's plain text, one request per slice), batchnum (ms timestamp), type 0} -> a task; GET
           /mooc-ans/edit/ai-check-result?courseId&knowledgeId&cardId&cpi -> {checkStatus (-1 never, 0 running,
           3 stopped/none, else done), data[{type, wrongWord, correctWord}]}, where wrongWord / correctWord are a
           snippet with the word in <span class="ai-error"> / <span class="ai-correct">; GET …/ai-check-stop stops it.
           The page applies a fix by replacing the word in the text node whose neighbouring characters match the
           snippet, then saves the card.
           documents (inserted 文档 of the card): t/enc = #aiDocCheckTime/#aiDocCheckEnc of GET
           /mooc-ans/edit/chapters/<course>/<chapter>?classId&cpi&newMooc=true&mooc2=1; POST
           /mooc-ans/edit/ai-doc-correction {objectIds, t, enc} starts; POST …/ai-doc-correction-result {objectIds, t,
           type, enc} -> data[{objectId, checkStatus 0 未开始 / 1 通过 / 2 可优化 / 3 进行中 / 4 失败}]; GET
           …/ai-doc-correction-data?objectId&t&enc -> data[{type, wrongWord, correctWord}] (read only).
"""
from __future__ import annotations

import hashlib
import html as _h
import json
import re
import time

from .ops_write import card_attachments
from .xxt import M1, XxtBase, XxtError, _safe_id  # noqa: F401

ARTICLE_TYPES = {"通用文章": 1, "课程思政": 2, "实验设计方案": 3, "实验报告": 4, "教学反思": 5, "工作总结": 6,
                 "师德师风心得": 7, "培训心得": 8, "实习报告": 9}
# 目录结构 -> the article types that pre-select it (pindex in the page)
SECTIONS = {"引言": (1,), "结尾": (1, 8, 9), "案例背景": (2,), "案例目标": (2,), "实施过程": (2,), "案例具体内容": (2,),
            "实验目的": (3, 4), "实验设计": (3,), "实验方法": (3,), "实验步骤": (3, 4), "教学目标": (5,), "教学实施": (5,),
            "教学效果": (5,), "目标与计划": (6,), "工作贡献": (6,), "个人能力与成长": (6,), "工作中的问题与改进": (6,),
            "自我评价与展望": (6,), "师德实践": (7,), "挑战与应对": (7,), "总结与展望": (7,), "学习反思": (8,), "个人成长": (8,),
            "实习目的与意义": (9,), "实习成果": (9,)}
STYLES = ("智能匹配", "专业严谨", "生动有趣", "通俗易懂", "情感共鸣", "个性化")
OPTION_KINDS = {"文章类型": 1, "目录结构": 2, "写作风格": 3}
CHECK_TYPES = {"punct": "符号标点", "idiom": "成语检查", "spell": "拼写检查", "gramm": "语法检查", "collocation": "搭配检查",
               "places": "地名检查", "organization": "机构名检查", "leader": "领导人姓名检查", "time": "时间检查"}
DOC_STATUS = {0: "未开始", 1: "通过", 2: "可优化", 3: "进行中", 4: "失败"}


def default_sections(type_no: int | None) -> list[str]:
    if not type_no:
        return ["引言"]
    return [k for k, v in SECTIONS.items() if type_no in v]


def outline_prompt(theme: str, sections: list[str], words: int) -> str:
    s = "".join(f"{x};" for x in sections)
    return f"<文章主题>{theme}</文章主题>" + (f"<目录结构>{s}</目录结构>" if s else "") + f"<文章字数>{int(words)}</文章字数>"


def article_prompt(theme: str, outline: str, audience: str, words: int, styles: list[str]) -> str:
    return (f"<文章主题>{theme}</文章主题>" + (f"<目录结构>{outline}</目录结构>" if outline else "")
            + (f"<年级或对象>{audience}</年级或对象>" if audience else "") + f"<文章字数>{int(words)}</文章字数>"
            + f"<写作风格>{''.join(f'{x};' for x in styles) or '智能匹配;'}</写作风格>")


_INLINE = [(re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"), (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"<em>\1</em>"),
           (re.compile(r"`([^`]+)`"), r"<code>\1</code>")]


def _inline(s: str) -> str:
    out, pos = [], 0
    for m in re.finditer(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", s):
        out.append(_inline_plain(s[pos:m.start()]))
        out.append(f'<a href="{_h.escape(m.group(2), quote=True)}" target="_blank">{_inline_plain(m.group(1))}</a>')
        pos = m.end()
    out.append(_inline_plain(s[pos:]))
    return "".join(out)


def _inline_plain(s: str) -> str:
    s = _h.escape(s, quote=False)
    for rx, rep in _INLINE:
        s = rx.sub(rep, s)
    return s


def md_html(md: str) -> str:
    """The small markdown subset the writing model answers in -> chapter HTML (headings, paragraphs, lists, quotes,
    tables, rules, bold/italic/code, http(s) links).  Everything else is escaped text."""
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    lst: list[str] = []
    kind = ""

    def flush():
        nonlocal lst, kind
        if lst:
            out.append(f"<{kind}>" + "".join(f"<li>{x}</li>" for x in lst) + f"</{kind}>")
            lst, kind = [], ""

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        st = ln.strip()
        if not st:
            flush()
        elif m := re.match(r"^(#{1,6})\s+(.*)$", st):
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2).strip())}</h{n}>")
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", st):
            flush()
            out.append("<hr>")
        elif st.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(_inline(lines[i].strip()[1:].strip()))
                i += 1
            out.append("<blockquote><p>" + "<br>".join(q) + "</p></blockquote>")
            continue
        elif st.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", lines[i + 1].strip()):
            flush()
            cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]  # noqa: E731
            head = cells(st)
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            t = "<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"
            out.append(t)
            continue
        elif m := re.match(r"^([-*+])\s+(.*)$", st):
            if kind not in ("", "ul"):
                flush()
            kind = "ul"
            lst.append(_inline(m.group(2)))
        elif m := re.match(r"^\d+[.)]\s+(.*)$", st):
            if kind not in ("", "ol"):
                flush()
            kind = "ol"
            lst.append(_inline(m.group(1)))
        else:                     # the model puts one paragraph per line
            flush()
            out.append(f"<p>{_inline(st)}</p>")
        i += 1
    flush()
    return "".join(out)


def check_item(raw: dict, index: int) -> dict | None:
    """One AI 校正 hit: wrongWord is a snippet with the word in <span class="ai-error">; the fix is the
    <span class="ai-correct"> part of correctWord (or the whole correctWord when it has no span)."""
    w = str(raw.get("wrongWord") or "")
    m = re.search(r'<span class="ai-error">(.*?)</span>', w, re.S)
    if not m:
        return None
    snippet = _h.unescape(re.sub(r"<[^>]+>", "", w))
    word = _h.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
    cw = str(raw.get("correctWord") or "")
    mc = re.search(r'<span class="ai-correct">(.*?)</span>', cw, re.S)
    right = _h.unescape(re.sub(r"<[^>]+>", "", mc.group(1) if mc else cw))
    pos = len(_h.unescape(re.sub(r"<[^>]+>", "", w[:m.start()])))
    return {"index": index, "type": CHECK_TYPES.get(str(raw.get("type")), str(raw.get("type") or "")), "context": snippet,
            "wrong": word, "suggestion": right, "before": snippet[pos - 1:pos] if pos > 0 else "",
            "after": snippet[pos + len(word):pos + len(word) + 1]}


# Port of the editor's replace (Te): replace `wrong` in the text node whose neighbouring characters (looking into the
# previous / next sibling, or the parent's siblings, at a node edge) equal before/after.  Nodes are walked in order.
APPLY_JS = r"""
const box=document.createElement('div'); box.innerHTML=SRC; const done=[];
const prevCh=(n)=>{ if(n.previousSibling&&n.previousSibling.textContent!==''){const t=n.previousSibling.textContent;return t[t.length-1]}
   if(n.parentNode&&n.parentNode.previousSibling&&n.parentNode.previousSibling.textContent!==''){const t=n.parentNode.previousSibling.textContent;return t[t.length-1]} return ''};
const nextCh=(n)=>{ if(n.nextSibling&&n.nextSibling.textContent!==''){return n.nextSibling.textContent[0]}
   if(n.parentNode&&n.parentNode.nextSibling&&n.parentNode.nextSibling.textContent!==''){return n.parentNode.nextSibling.textContent[0]} return ''};
const walk=(n,f)=>{ if(f.hit) return; if(n.nodeType===3){ const s=n.textContent; let k=0;
     while((k=s.indexOf(f.wrong,k))!==-1){ let b=k===0?prevCh(n):s[k-1]; let a=(k+f.wrong.length>=s.length)?nextCh(n):s[k+f.wrong.length];
       b=(b||'').replace(/ /g,' '); a=a||'';
       if(b===f.before&&a===f.after){ n.textContent=s.slice(0,k)+f.suggestion+s.slice(k+f.wrong.length); f.hit=true; return } k++ } }
   else if(n.nodeType===1){ for(const ch of [...n.childNodes]) walk(ch,f) } };
for(const f of FIXES.slice().reverse()){ f.hit=false; walk(box,f); done.push({index:f.index,applied:f.hit}) }
return {html:box.innerHTML, done:done.reverse()};
"""


class ChapterAiOps(XxtBase):
    # ------------------------------------------------------------------ 智能编写
    def _ai_ctx(self, c) -> str:
        return """
            const ci=(await J('/mooc-ans/edit/get-course-info?courseId=%s&clazzId=%s')).data||{};
            const W=(ci.aiInfo||{}).aiWriting||{}; const UID=String((ci.userInfo||{}).uid||'');
            if(!W.aiEnc||!UID) return {stage:'enc'};
        """ % (_safe_id(c.id), _safe_id(c.clazz_id))

    def ai_writing_options(self, course: str) -> dict:
        c = self.ctx(course)
        r = self.on(M1, self._ai_ctx(c) + """
            return {stage:'done', j:await J('/mooc-ans/ai/chapter-writing/get?courseId=%s&cpi=%s&uid='+UID+'&t='+W.aiTime+'&enc='+W.aiEnc)};
        """ % (_safe_id(c.id), _safe_id(c.cpi)))
        j = (r or {}).get("j") if isinstance(r, dict) else None
        if not isinstance(j, dict) or j.get("status") is not True:
            raise XxtError(f"读取智能编写选项失败（{(r or {}).get('stage')}）。")
        names = {v: k for k, v in OPTION_KINDS.items()}
        custom = [{"option_id": str(x.get("id")), "kind": names.get(x.get("type"), str(x.get("type"))), "name": x.get("optionName"),
                   **({"description": x.get("optionDescription")} if x.get("optionDescription") else {})} for x in j.get("data") or []]
        return {"article_types": list(ARTICLE_TYPES), "sections": {k: [n for n, v in ARTICLE_TYPES.items() if v in t] for k, t in SECTIONS.items()},
                "styles": list(STYLES), "custom": custom}

    def save_ai_writing_option(self, course: str, kind: str, name: str, description: str = "") -> dict:
        c = self.ctx(course)
        before = {x["option_id"] for x in self.ai_writing_options(c.id)["custom"]}
        extra = "fd.append('optionDescription',%s);" % json.dumps(description, ensure_ascii=False) if OPTION_KINDS[kind] == 1 else ""
        r = self.on(M1, self._ai_ctx(c) + """
            const fd=new FormData(); fd.append('type','%d'); fd.append('courseId','%s'); fd.append('cpi','%s'); fd.append('uid',UID);
            fd.append('t',String(W.aiTime)); fd.append('enc',W.aiEnc); fd.append('optionName',%s); %s
            return {stage:'done', j:await J('/mooc-ans/ai/chapter-writing/save',{method:'POST',body:fd})};
        """ % (OPTION_KINDS[kind], _safe_id(c.id), _safe_id(c.cpi), json.dumps(name, ensure_ascii=False), extra), retry_safe=False)
        j = (r or {}).get("j") if isinstance(r, dict) else None
        after = [x for x in self.ai_writing_options(c.id)["custom"] if x["option_id"] not in before]
        ok = isinstance(j, dict) and j.get("status") is True and len(after) == 1 and after[0]["name"] == name and after[0]["kind"] == kind
        return {"ok": ok, "option": after[0] if after else None,
                **({} if ok else {"write_outcome": "unknown" if after or (isinstance(j, dict) and j.get("status")) else "not_written",
                                  "error": f"保存后核对不一致（{str((j or {}).get('msg') or '')[:40]}）。"})}

    def delete_ai_writing_option(self, course: str, option_id: str) -> dict:
        c = self.ctx(course)
        r = self.on(M1, self._ai_ctx(c) + """
            const fd=new FormData(); fd.append('id','%s'); fd.append('courseId','%s'); fd.append('cpi','%s'); fd.append('uid',UID);
            fd.append('t',String(W.aiTime)); fd.append('enc',W.aiEnc);
            return {stage:'done', j:await J('/mooc-ans/ai/chapter-writing/delete',{method:'POST',body:fd})};
        """ % (_safe_id(option_id), _safe_id(c.id), _safe_id(c.cpi)), retry_safe=False)
        j = (r or {}).get("j") if isinstance(r, dict) else None
        left = {x["option_id"] for x in self.ai_writing_options(c.id)["custom"]}
        ok = isinstance(j, dict) and j.get("status") is True and option_id not in left
        return {"ok": ok, **({} if ok else {"write_outcome": "unknown", "error": f"删除后核对不一致（{str((j or {}).get('msg') or '')[:40]}）。"})}

    def _ai_write(self, c, writing_type: str, content: str, topic: str, type_no: int | None, web: bool) -> dict:
        enc = "aiWritingChapterEnc" if writing_type == "chapter" else "aiWritingArticleEnc"
        r = self.on(M1, self._ai_ctx(c) + """
            const pick=o=>{if(!o||typeof o!=='object')return null; if(o.type==='text'&&typeof o.content==='string')return o.content;
               const m=o.choices&&o.choices[0]&&o.choices[0].message; return m&&typeof m.content==='string'?m.content:null};
            const body={userId:UID,content:%s,writingType:%s,t:String(W.aiTime),articleTheme:%s,hostName:location.hostname,botType:%d,enc:W[%s]};
            if(%s) body.articleType=%s;
            const r=await fetch('/ai-ans/ai/chapter/writing',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            const raw=await r.text(); let text='',ended=false,after='',bad=0;
            for(const part of raw.split('data:')){ const p=part.trim(); if(!p) continue;
              if(p.startsWith('[textEnd]')){ended=true; after+=p.slice(9); continue}
              if(ended){after+=p; continue}
              if(p.startsWith('{')){ try{const v=pick(JSON.parse(p)); if(v!=null) text+=v}catch(e){bad++} } }
            return {stage:'done',http:r.status,text,after,bad,raw:text?'':raw.slice(0,200)};
        """ % (json.dumps(content, ensure_ascii=False), json.dumps(writing_type), json.dumps(topic, ensure_ascii=False), 1 if web else 0,
               json.dumps(enc), "true" if type_no else "false", json.dumps(str(type_no or ""))), timeout=300, retry_safe=False)
        if not isinstance(r, dict) or r.get("stage") != "done" or r.get("http") != 200 or not str(r.get("text") or "").strip():
            raise XxtError(f"智能编写没有返回内容（{(r or {}).get('stage')} {(r or {}).get('http')} {str((r or {}).get('raw') or '')[:80]}）。")
        sources = []
        if r.get("after"):
            try:
                sources = [{"site": x.get("siteName") or "", "title": x.get("title") or x.get("filename") or "", "url": x.get("url") or ""}
                           for x in json.loads(r["after"]) if isinstance(x, dict)]
            except ValueError:
                pass
        return {"text": str(r["text"]).strip(), "sources": sources}

    def ai_write_preview(self, course: str, topic: str, article_type: str, sections: list[str], outline: str, audience: str,
                         words: int, styles: list[str], web_search: bool) -> dict:
        c = self.ctx(course)
        opts = self.ai_writing_options(c.id)
        custom = {(x["kind"], x["name"]) for x in opts["custom"]}
        if article_type not in ARTICLE_TYPES and ("文章类型", article_type) not in custom:
            raise XxtError(f"文章类型只能是：{'、'.join(ARTICLE_TYPES)}，或自定义类型 {[n for k, n in custom if k == '文章类型']}。")
        type_no = ARTICLE_TYPES.get(article_type)
        secs = sections or default_sections(type_no)
        bad = [x for x in secs if x not in SECTIONS and ("目录结构", x) not in custom]
        bad_style = [x for x in styles if x not in STYLES and ("写作风格", x) not in custom]
        if bad or bad_style:
            raise XxtError(f"没有这些目录结构 / 写作风格：{bad + bad_style}（get_ai_writing_options 可查）。")
        theme = f" 帮我生成一篇 {topic}{article_type}"
        made_outline = not outline.strip()
        if made_outline:
            outline = self._ai_write(c, "chapter", outline_prompt(theme, secs, words), topic, type_no, web_search)["text"]
        art = self._ai_write(c, "article", article_prompt(theme, outline.strip(), audience, words, styles or ["智能匹配"]), topic, type_no, web_search)
        html = md_html(art["text"])
        if not html:
            raise XxtError("智能编写返回的内容为空。")
        return {"outline": outline.strip(), "outline_generated": made_outline, "article_markdown": art["text"], "html": html,
                "sources": art["sources"], "chars": len(re.sub(r"<[^>]+>", "", html)),
                "digest": hashlib.sha256(html.encode("utf-8")).hexdigest()}

    # ------------------------------------------------------------------ AI 校正
    def _card_params(self, c, chapter_id: str, card_id: str) -> str:
        return f"courseId={_safe_id(c.id)}&knowledgeId={_safe_id(chapter_id)}&cardId={_safe_id(card_id)}&cpi={_safe_id(c.cpi)}"

    def _text_result(self, c, chapter_id: str, card_id: str) -> dict:
        r = self.on(M1, "return await J('/mooc-ans/edit/ai-check-result?%s');" % self._card_params(c, chapter_id, card_id))
        if not isinstance(r, dict) or r.get("status") is not True:
            raise XxtError(f"读取 AI 校正结果失败（{str((r or {}).get('msg') or '')[:60]}）。")
        st = r.get("checkStatus")
        items = [x for x in (check_item(d, i) for i, d in enumerate(r.get("data") or []) if isinstance(d, dict)) if x]
        label = {-1: "未检测", 0: "检测中", 3: "已停止或无结果"}.get(st, "已完成")
        return {"check_status": st, "status": label, "items": items}

    def _doc_keys(self, c, chapter_id: str) -> str:
        return """
            const h=await (await fetch('/mooc-ans/edit/chapters/%s/%s?classId=%s&cpi=%s&newMooc=true&mooc2=1',{credentials:'include'})).text();
            const dd=new DOMParser().parseFromString(h,'text/html'); const gv=id=>{const e=dd.getElementById(id);return e?e.value:''};
            const DT=gv('aiDocCheckTime'), DE=gv('aiDocCheckEnc'); if(!DT||!DE) return {stage:'enc'};
            const post=async(u,o)=>{const fd=new FormData(); for(const k in o) fd.append(k,o[k]); return await J(u,{method:'POST',body:fd})};
        """ % (_safe_id(c.id), _safe_id(chapter_id), _safe_id(c.clazz_id), _safe_id(c.cpi))

    def _card_docs(self, c, chapter_id: str, card_id: str) -> list[dict]:
        cur = self._read_card(c, chapter_id, card_id)
        if cur is None:
            raise XxtError("指定的章节卡片不存在。")
        return [{"object_id": str(a.get("objectid") or a.get("objectId")), "name": a.get("name") or a.get("title") or ""}
                for a in card_attachments(cur.get("description") or "") if a.get("module") == "insertdoc" and (a.get("objectid") or a.get("objectId"))][:50]

    def ai_check(self, course: str, chapter_id: str, card_id: str, kind: str, start: bool, wait: int) -> dict:
        c = self.ctx(course)
        if kind == "文本":
            if start:
                cur = self._read_card(c, chapter_id, card_id)
                if cur is None:
                    raise XxtError("指定的章节卡片不存在。")
                r = self.on(M1, """
                    const box=document.createElement('div'); box.innerHTML=%s; box.querySelectorAll('iframe,script,style').forEach(e=>e.remove());
                    const text=box.textContent; if(!text.trim()) return {stage:'empty'}; if(text.length>100000) return {stage:'big'};
                    const bn=String(Date.now()); let ok=0, msg='';
                    for(let i=0;i<text.length;i+=1000){ const fd=new FormData(); fd.append('courseId','%s'); fd.append('knowledgeId','%s');
                      fd.append('cardId','%s'); fd.append('cpi','%s'); fd.append('content',text.slice(i,i+1000)); fd.append('batchnum',bn); fd.append('type','0');
                      const j=await J('/mooc-ans/edit/ai-correction',{method:'POST',body:fd}); if(j&&j.status) ok++; else msg=String((j||{}).msg||'') }
                    return {stage:'done',chunks:Math.ceil(text.length/1000),ok,msg,chars:text.length};
                """ % (json.dumps(cur.get("description") or "", ensure_ascii=False), _safe_id(c.id), _safe_id(chapter_id), _safe_id(card_id),
                       _safe_id(c.cpi)), retry_safe=False)
                if not isinstance(r, dict) or r.get("stage") != "done" or not r.get("ok"):
                    raise XxtError({"empty": "这一页没有文字可检测。", "big": "内容超过 10 万字，平台不支持检测。"}.get(
                        (r or {}).get("stage"), f"没能开始检测（{str((r or {}).get('msg') or '')[:60]}）。"))
            res = self._text_result(c, chapter_id, card_id)
            t0 = time.time()
            while res["check_status"] == 0 and time.time() - t0 < wait:
                time.sleep(min(10, max(1, wait - (time.time() - t0))))
                res = self._text_result(c, chapter_id, card_id)
            return {"kind": kind, "card_id": card_id, **res,
                    **({"note": "平台还在检测；稍后再用 start=false 读取结果。"} if res["check_status"] == 0 else {})}
        docs = self._card_docs(c, chapter_id, card_id)
        if not docs:
            return {"kind": kind, "card_id": card_id, "documents": [], "note": "这一页没有插入的文档。"}
        ids = ",".join(_safe_id(d["object_id"]) for d in docs)
        names = {d["object_id"]: d["name"] for d in docs}

        def status(tp: int) -> dict:
            r = self.on(M1, self._doc_keys(c, chapter_id) + "return {stage:'done', j:await post('/mooc-ans/edit/ai-doc-correction-result',{objectIds:'%s',t:DT,type:'%d',enc:DE})};"
                        % (ids, tp))
            j = (r or {}).get("j") if isinstance(r, dict) else None
            if not isinstance(j, dict) or j.get("status") is not True:
                raise XxtError(f"读取文档校正状态失败（{(r or {}).get('stage')}）。")
            return {str(x.get("objectId")): int(x.get("checkStatus") or 0) for x in j.get("data") or [] if isinstance(x, dict)}

        st = status(0)
        if start:
            todo = ",".join(o for o, s in st.items() if s in (0, 4))
            if todo:
                r = self.on(M1, self._doc_keys(c, chapter_id) + "return {stage:'done', j:await post('/mooc-ans/edit/ai-doc-correction',{objectIds:'%s',t:DT,enc:DE})};" % todo,
                            retry_safe=False)
                j = (r or {}).get("j") if isinstance(r, dict) else None
                if not isinstance(j, dict) or j.get("status") is not True:
                    raise XxtError(f"没能开始文档校正（{str((j or {}).get('msg') or '')[:60]}）。")
            st = status(2)
        t0 = time.time()
        while any(s == 3 for s in st.values()) and time.time() - t0 < wait:
            time.sleep(min(10, max(1, wait - (time.time() - t0))))
            st = status(2)
        out = []
        for oid, s in st.items():
            d = {"object_id": oid, "name": names.get(oid, ""), "status": DOC_STATUS.get(s, str(s))}
            if s == 2:
                r = self.on(M1, self._doc_keys(c, chapter_id) + "return {stage:'done', j:await J('/mooc-ans/edit/ai-doc-correction-data?objectId=%s&t='+DT+'&enc='+DE)};"
                            % _safe_id(oid))
                j = (r or {}).get("j") if isinstance(r, dict) else None
                d["items"] = [x for x in (check_item(v, i) for i, v in enumerate((j or {}).get("data") or []) if isinstance(v, dict)) if x]
                d["note"] = "文档的修改要在原文件里改好后重新上传替换。"
            out.append(d)
        return {"kind": kind, "card_id": card_id, "documents": out,
                **({"note": "平台还在检测；稍后再用 start=false 读取结果。"} if any(s == 3 for s in st.values()) else {})}

    def ai_check_stop(self, course: str, chapter_id: str, card_id: str) -> dict:
        c = self.ctx(course)
        r = self.on(M1, "return await J('/mooc-ans/edit/ai-check-stop?%s');" % self._card_params(c, chapter_id, card_id), retry_safe=False)
        res = self._text_result(c, chapter_id, card_id)
        return {"ok": isinstance(r, dict) and r.get("status") is True and res["check_status"] != 0, **res}

    def ai_fix_preview(self, course: str, chapter_id: str, card_id: str, indexes: list[int]) -> dict:
        c = self.ctx(course)
        res = self._text_result(c, chapter_id, card_id)
        if res["check_status"] == 0:
            raise XxtError("平台还在检测这一页，结果出来后再替换。")
        items = {x["index"]: x for x in res["items"]}
        if not items:
            raise XxtError("这一页没有 AI 校正的修改建议；先用 ai_check_chapter(start=true) 检测。")
        pick = [items[i] for i in indexes] if indexes else list(items.values())
        if indexes and any(i not in items for i in indexes):
            raise XxtError(f"没有这些建议编号：{[i for i in indexes if i not in items]}。")
        cur = self._read_card(c, chapter_id, card_id)
        if cur is None:
            raise XxtError("指定的章节卡片不存在。")
        src = cur.get("description") or ""
        r = self.on(M1, "const SRC=%s; const FIXES=%s;" % (json.dumps(src, ensure_ascii=False), json.dumps(
            [{k: x[k] for k in ("index", "wrong", "suggestion", "before", "after")} for x in pick], ensure_ascii=False)) + APPLY_JS)
        if not isinstance(r, dict) or "html" not in r:
            raise XxtError("没能在正文里套用修改。")
        applied = [d["index"] for d in r.get("done") or [] if d.get("applied")]
        if not applied:
            raise XxtError("这些建议在正文里都找不到对应文字（正文可能已改过）；请重新检测。")
        new = str(r["html"])
        if len(card_attachments(new)) != len(card_attachments(src)):
            raise XxtError("套用修改后插入项数量变了；没有处理。")
        return {"html": new, "source_digest": hashlib.sha256(src.encode("utf-8")).hexdigest(), "applied": applied,
                "not_found": [x["index"] for x in pick if x["index"] not in applied],
                "changes": [{k: x[k] for k in ("index", "type", "wrong", "suggestion", "context")} for x in pick if x["index"] in applied]}

    def ai_fix_apply(self, course: str, chapter_id: str, card_id: str, html: str, source_digest: str) -> dict:
        c = self.course(course)
        cur = self._read_card(c, chapter_id, card_id)
        if cur is None:
            raise XxtError("指定的章节卡片不存在；没有修改。")
        src = cur.get("description") or ""
        if hashlib.sha256(src.encode("utf-8")).hexdigest() != source_digest:
            return {"ok": False, "write_outcome": "not_written", "error": "预演之后这一页正文被改过了；没有覆盖，请重新预演。"}
        atts = card_attachments(src)
        r = self._save_card(c, chapter_id, card_id, cur.get("title") or "", html, atts)
        back = self._read_card(c, chapter_id, card_id)
        body = (back or {}).get("description") or ""
        norm = lambda s: re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", _h.unescape(s)))  # noqa: E731
        ok = r.get("http") == 200 and back is not None and norm(body) == norm(html) and len(card_attachments(body)) == len(atts)
        return {"ok": ok, "card_id": card_id,
                **({} if ok else {"write_outcome": "unknown", "error": "保存后读回不一致；请用 read_chapter_content 核查，不要重复提交。"})}
