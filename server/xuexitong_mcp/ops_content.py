"""Students, notices, assignments, exams, discussions."""
from __future__ import annotations

import json
import re
import time
import urllib.parse as up

from .xxt import (BASE_PAGE, GROUP, M2, NOTICE, Course, XxtBase, XxtError, _best, _html, _safe_id, norm_time)


class ContentOps(XxtBase):
    # ================================================================ students
    def students(self, course: str, cls: str = "") -> dict:
        c = self.ctx(course)
        clz = self.resolve_class(c, cls)
        rows = self.on(M2, f"""
            const out=[];
            for(let p=1;p<=50;p++){{
              const d=D(await F('/mooc2-ans/tcm/clazz-student?courseid={c.id}&clazzid={clz}&cpi={c.cpi}&pageNum='+p+'&pageShowNum=100&schoolStatus=0&v=0'));
              const trs=[...d.querySelectorAll('tr')].filter(t=>t.querySelectorAll('td').length>=8);
              trs.forEach(t=>{{const td=t.querySelectorAll('td');out.push({{person_id:T(td[1]),name:T(td[2]),student_no:T(td[3]),college:T(td[4]),major:T(td[5]),class:T(td[6]),joined:T(td[7])}})}});
              if(trs.length<100) break;
            }}
            return out;
        """)
        cname = next((x["name"] for x in c.classes if x["clazz_id"] == clz), "")
        return {"course": c.name, "class": cname, "clazz_id": clz, "count": len(rows), "students": rows}

    # ================================================================ notices
    def notices(self, course: str, limit: int = 30) -> list[dict]:
        return ContentOps.notice_inventory(self, course, limit)["items"]

    def notice_inventory(self, course: str, limit: int = 200, *, full_content: bool = False) -> dict:
        """Bounded traversal with truthful completeness, not an atomic snapshot."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise XxtError("通知查询 limit 必须是 1 到 1000 的整数。")
        c = self.course(course)
        result = self.on(NOTICE, f"""
            const out=[], ids=new Set(), normalIds=new Set(), topIds=new Set(), cursors=new Set(); let last='', pages=0, requests=0, end=false, protocolEnd=false, reason='page_cap';
            for(let i=0;i<10;i++){{
              const j=await J('/pc/course/notice/getNoticeList',POST({{courseId:'{c.id}',lastValue:last,kw:''}}));
              requests++;
              const n=j?.notices;
              if(j?.status!==true) return {{valid:false}};
              const validRow=x=>x&&typeof x==='object'&&x.idCode!=null&&String(x.idCode).trim()&&typeof x.title==='string'&&
                (x.content==null||typeof x.content==='string')&&(x.receiverArray==null||(Array.isArray(x.receiverArray)&&x.receiverArray.every(r=>r&&typeof r.name==='string')));
              const add=x=>{{const id=String(x.idCode);ids.add(id);out.push({{notice_id:id,uuid:x.uuid||'',title:x.title,time:x.completeTime||'',
                read:(x.count_read||0)+'/'+(x.count_all||0),to:(x.receiverArray||[]).map(r=>r.name).join(','),
                receivers:(x.receiverArray||[]).map(r=>({{course_id:String(r.courseId||''),class_id:String(r.clazzId||''),name:r.name,type:r.type}})),
                send_tag:x.sendTag,content:(x.content||''){'' if full_content else '.slice(0,200)'}}});}};
              if(j.topNotices!=null){{
                if(!Array.isArray(j.topNotices)||j.topNotices.some(x=>!validRow(x)))return {{valid:false}};
                for(const x of j.topNotices){{const id=String(x.idCode);if(!ids.has(id))add(x);topIds.add(id);}}
              }}
              // Observed live response and courseNotice.util.js both use a
              // successful absent notices object as the pagination terminator.
              const allowedKeys=['status','draftDataCount','notices','topIdCodes','topNotices','isXueYinCourse'];
              if(n==null&&Object.keys(j).every(k=>allowedKeys.includes(k))){{protocolEnd=true;reason='client_protocol_end';break;}}
              if(j?.status!==true||!n||!Array.isArray(n.list)) return {{valid:false}};
              const l=n.list;
              if(l.some(x=>!validRow(x))) return {{valid:false}};
              pages++;
              for(const x of l){{
                const id=String(x.idCode);
                if(normalIds.has(id)) return {{valid:false}};
                normalIds.add(id);
                if(!topIds.has(id))add(x);
              }}
              if(n.lastPage===1||n.lastPage==='1'){{end=true;reason='explicit_end';break;}}
              if(out.length>={limit}){{reason='item_limit';break;}}
              if(!l.length){{reason='empty_page_without_end';break;}}
              const next=n.lastGetId;
              if((typeof next!=='string'&&typeof next!=='number')||!String(next).trim()){{reason='missing_cursor';break;}}
              if(cursors.has(String(next))||String(next)===String(last)){{reason='repeated_cursor';break;}}
              cursors.add(String(next)); last=next;
            }}
            const truncated=out.length>{limit}, items=out.slice(0,{limit});
            return {{valid:true,items,pagination:{{pages_read:pages,requests,returned_count:items.length,
              explicit_end_reached:end,client_protocol_end:protocolEnd,complete:(end||protocolEnd)&&!truncated,stop_reason:truncated?'item_limit':reason,
              items_truncated:truncated,max_pages:10,requested_limit:{limit},snapshot_consistency:'not_guaranteed'}}}};
        """)
        if (not isinstance(result, dict) or result.get("valid") is not True or not isinstance(result.get("items"), list)
                or not isinstance(result.get("pagination"), dict)):
            raise XxtError("通知列表响应失败或结构不完整；不能视为空列表。")
        return {"course_id": c.id, "items": result["items"], "pagination": result["pagination"]}

    def publish_notice(self, course: str, title: str, content: str) -> dict:
        c = self.course(course)
        self.b.adopt_new_tab(f"https://notice.chaoxing.com/pc/course/notice/richtextNotice?courseId={c.id}")
        ok = self.wait_for("return typeof UE!=='undefined' && Object.keys(UE.instants||{}).length>0 && !!document.querySelector('.sendNotice')", timeout=20)
        if not ok:
            raise XxtError("通知编辑页未加载")
        st = self.here(f"""
            const t=[...document.querySelectorAll('input')].find(e=>e.placeholder&&e.placeholder.indexOf('请输入标题')>=0);
            if(!t) return 'no title';
            t.focus(); t.value={json.dumps(title)}; ['input','keyup','change'].forEach(n=>t.dispatchEvent(new Event(n,{{bubbles:true}})));
            const u=Object.values(UE.instants)[0]; u.setContent({json.dumps(_html(content))}); try{{u.fireEvent('contentChange')}}catch(e){{}}
            return 'ok';
        """)
        if st != "ok":
            raise XxtError(f"通知表单填写失败: {st}")
        self.b.click_selector(".sendNotice", settle=2.5)
        for _ in range(6):   # verify-after-write
            hit = [n for n in self.notices(c.id, limit=10) if n["title"] == title]
            if hit:
                return {"ok": True, "notice": hit[0]}
            time.sleep(1.5)
        raise XxtError("点击了“发送”，但通知列表中没有找到该通知，请人工检查（不要重复发送）")

    def delete_notice(self, course: str, notice: str) -> dict:
        c = self.course(course)
        n = _best(self.notices(c.id, limit=100), notice, id_keys=("notice_id",))
        nid = _safe_id(n["notice_id"])
        r = self.on(NOTICE, f"return await J('/pc/course/notice/delNoitce',POST({{noticeId:{json.dumps(nid)},sendTag:'1'}}));", retry_safe=False)
        still = [x for x in self.notices(c.id, limit=100) if x["notice_id"] == n["notice_id"]]
        return {"ok": not still, "deleted": n["title"], "server": r}

    # ================================================================ assignments
    def assignments(self, course: str) -> list[dict]:
        c = self.ctx(course)
        return self.on(M2, f"""
            const d=D(await F('/mooc2-ans/work/list?{self.q(c)}'));
            return [...d.querySelectorAll('.taskList li[id^=work]')].map(li=>{{
              const v=(li.querySelector('.list_li_tit')?.getAttribute('onclick')||'').match(/viewWork\\('([^']*)','([^']*)','([^']*)'\\)/)||[];
              const cnt=T(li.querySelector('.piyuePcon'));
              return {{id:li.id.replace('work',''),title:T(li.querySelector('.list_li_tit')),class:T(li.querySelector('.list_class')),
                time:T(li.querySelector('.list_li_time')).replace('作答时间：',''),library_id:v[1]||'',relation_id:v[2]||'',clazz_id:v[3]||'',
                pending:(cnt.match(/(\\d+)\\s*待批/)||[])[1],submitted:(cnt.match(/(\\d+)\\s*已交/)||[])[1],unsubmitted:(cnt.match(/(\\d+)\\s*未交/)||[])[1]}};
            }});
        """)

    def _find_assignment(self, c: Course, a: str) -> dict:
        return _best(self.assignments(c.id), a, id_keys=("id", "relation_id", "library_id"))

    def assignment_library_first_page(self, course: str) -> dict:
        """Read the first visible library page. Never treat it as a full inventory when paginated."""
        c = self.ctx(course)
        self.b.navigate(f"https://{M2}/mooc2-ans/work/library?{self.q(c)}&from=resource",
                        wait="domcontentloaded", settle=0.5)
        result = self.wait_for("""
            const root=document.querySelector('#datalist');
            const pages=document.querySelector('#pages');
            const total=document.querySelector('#totalPage');
            const size=document.querySelector('#pageSize');
            if(!root || !pages || !total || !size) return null;
            const ints=[pages.value,total.value,size.value];
            if(ints.some(x=>!/^\\d+$/.test(x))) return null;
            const current=Number(pages.value), count=Number(total.value), pageSize=Number(size.value);
            if(current!==1 || count<1 || pageSize<1) return null;
            const rows=[...root.querySelectorAll('ul.dataBody_td')];
            // The empty-page marker has not been verified on the live site.
            // Do not turn a partially loaded page into a false empty result.
            if(!rows.length) return null;
            const text=e=>e?(e.textContent||'').replace(/\\s+/g,' ').trim():'';
            const items=rows.map(r=>{
              const name=r.querySelector('.dataBody_name a');
              const when=r.querySelector('.dataBody_time');
              const id=r.getAttribute('data')||'';
              return {id:/^[A-Za-z0-9_-]{1,80}$/.test(id)?id:null,
                type_code:r.getAttribute('type'), title:text(name),
                questions:text(r.querySelector('.dataHead_questionNum')),
                score:text(r.querySelector('.dataHead_score')),
                creator:text(r.querySelector('.dataBody_read')),
                created_at:when?[...when.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ').replace(/\\s+/g,' ').trim():''};
            });
            const incomplete=items.some(x=>!x.id||!x.title);
            return {page:current,total_pages:count,page_size:pageSize,items,
              visible_count:items.length,parse_incomplete:incomplete,
              has_more:current<count,complete:current===1&&count<=1&&!incomplete,
              note:'只读取当前第一页；未自动翻页、未读取草稿或回收站。'};
        """, timeout=20)
        if not isinstance(result, dict):
            raise XxtError("作业库未加载或分页标记无效；未将它当作空列表。")
        return result

    def create_assignment(self, course: str, title: str, questions: list[str], end_time: str | None, publish: bool = True,
                          classes: list[str] | None = None) -> dict:
        c = self.ctx(course)
        end = norm_time(end_time)
        qs = [q for q in (questions or []) if str(q).strip()] or [title]
        self.b.adopt_new_tab(f"https://mooc2-ans.chaoxing.com/mooc2-ans/work/goToWorkEditor?courseid={c.id}&clazzid={c.clazz_id}&mooc=1&workid=&built=1&from=")
        if not self.wait_for("return !!document.getElementById('title') && typeof saveWork==='function' && !!document.querySelector('span.addQuestionBtn')", timeout=20):
            raise XxtError("作业编辑器未加载")
        self.here(f"const t=document.getElementById('title'); t.value={json.dumps(title)}; t.dispatchEvent(new Event('change',{{bubbles:true}})); return true;")
        for i, qtext in enumerate(qs):
            n0 = self.here("return typeof UE==='undefined'?0:Object.values(UE.instants).filter(u=>u.key==='content'&&u.container&&u.container.offsetParent).length;")
            self.here("const b=[...document.querySelectorAll('span.addQuestionBtn')].find(e=>e.innerText.trim()==='简答题'); b.click(); return true;", retry_safe=False)
            # UEditor is lazy-loaded with the first question
            if not self.wait_for("return typeof UE!=='undefined' && Object.values(UE.instants).filter(u=>u.key==='content'&&u.container&&u.container.offsetParent&&u.isReady).length>%d" % int(n0 or 0), timeout=15, interval=0.7):
                raise XxtError(f"第 {i + 1} 题编辑器没有出现")
            ok = self.here(f"""
                const ins=Object.values(UE.instants).filter(u=>u.key==='content'&&u.container&&u.container.offsetParent);
                const u=ins[ins.length-1]; if(!u) return 'no editor'; u.setContent({json.dumps(_html(str(qtext)))}); try{{u.fireEvent('contentChange')}}catch(e){{}}
                const done=[...document.querySelectorAll('a.jb_btn')].filter(e=>e.offsetParent&&e.innerText.trim()==='完成'&&/saveAnswerQuestion/.test(e.getAttribute('onclick')||''));
                if(!done.length) return 'no 完成'; done[done.length-1].click(); return 'ok';
            """, retry_safe=False)
            if ok != "ok":
                raise XxtError(f"第 {i + 1} 题录入失败: {ok}")
            time.sleep(1.5)
        self.here("saveWork(1); return true;", retry_safe=False)
        url = ""
        for _ in range(15):
            time.sleep(1)
            url = self.b.href()
            if "library/setting" in url:
                break
        lib = dict(up.parse_qsl(up.urlparse(url).query)).get("workLibraryId", "")
        if not lib:
            raise XxtError(f"保存作业后没有进入发放设置页（{url}）。作业可能已保存到作业库，请人工检查。")
        res = {"ok": True, "title": title, "library_id": lib, "questions": len(qs), "published": False}
        if publish:
            res.update(self._publish_work_setting(c, end, classes, title))
        else:
            res["note"] = "已保存到作业库（未发放）。用 publish_assignment(library_id=...) 发放。"
        return res

    def _publish_work_setting(self, c: Course, end: str, classes: list[str] | None, title: str) -> dict:
        if not self.wait_for("return !!document.getElementById('choosepublish') && typeof checkQuestion==='function'", timeout=20):
            raise XxtError("发放设置页未加载")
        st = self.here(self._select_classes_js(c, classes) + f"""
            const e=document.getElementById('endTime'); e.value={json.dumps(end)}; try{{endTimeChanged()}}catch(x){{}}
            return {{to:T(document.querySelector('.selectClass')),start:document.getElementById('startTime')?.value,end:e.value}};
        """, retry_safe=False)
        if not st or not st.get("to"):
            raise XxtError("没有选中发放对象（班级）")
        self.here("checkQuestion(); return true;", retry_safe=False)
        hit = []
        for _ in range(5):
            time.sleep(2)
            hit = [a for a in self.assignments(c.id) if a["title"] == title]
            if hit:
                break
        return {"published": bool(hit), "assignment": hit[0] if hit else None, "to": st.get("to"), "start": st.get("start"), "end": st.get("end")}

    def publish_assignment(self, course: str, library_id: str, title: str, end_time: str | None, classes: list[str] | None = None) -> dict:
        c = self.ctx(course)
        self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/work/library/setting?courseid={c.id}&cpi={c.cpi}&workLibraryId={library_id}&fromCreate=1&from=")
        r = self._publish_work_setting(c, norm_time(end_time), classes, title)
        r["ok"] = r["published"]
        return r

    def submissions(self, course: str, assignment: str) -> dict:
        c = self.ctx(course)
        a = self._find_assignment(c, assignment)
        clz = a.get("clazz_id") or c.clazz_id
        res = self.on(M2, f"""
            const one=async(s)=>{{const d=D(await F('/mooc2-ans/work/mark-list?courseid={c.id}&clazzid={clz}&workid={a['relation_id']}&cpi={c.cpi}&submit='+s+'&status=0&groupId=0&evaluation=0&sort=0&order=0&unEval=&search=&from=&topicid=0&pages=1&size=500'));
              return [...d.querySelectorAll('ul.dataBody_td')].map(u=>{{const li=[...u.querySelectorAll('li')].map(T);return {{person_id:u.id,name:T(u.querySelector('.py_name'))||li[1],cells:li.slice(2,-1)}}}});}};
            return {{submitted:await one(true),unsubmitted:await one(false)}};
        """)
        return {"assignment": a["title"], "id": a["id"], "submitted_count": len(res["submitted"]), "unsubmitted_count": len(res["unsubmitted"]), **res}

    def remind_assignment(self, course: str, assignment: str) -> dict:
        c = self.ctx(course)
        a = self._find_assignment(c, assignment)
        clz = a.get("clazz_id") or c.clazz_id
        r = self.on(M2, f"return await J('/mooc2-ans/work/urge?courseid={c.id}&clazzid={clz}&cpi={c.cpi}&workid={a['relation_id']}&whole=true');", retry_safe=False)
        return {"ok": bool(isinstance(r, dict) and r.get("status")), "assignment": a["title"], "server": r}

    def delete_assignment(self, course: str, assignment: str) -> dict:
        c = self.ctx(course)
        a = self._find_assignment(c, assignment)
        r = self.on(M2, f"return await J('/mooc2-ans/work/delete?courseid={c.id}&classid=0&id={a['id']}&recycle=1&cpi={c.cpi}');", retry_safe=False)
        still = [x for x in self.assignments(c.id) if x["id"] == a["id"]]
        return {"ok": not still, "deleted": a["title"], "note": "已移入作业回收站，可还原", "server": r}

    # ================================================================ exams
    def exams(self, course: str) -> list[dict]:
        """Every class's exams (the list page only shows the class named in clazzid)."""
        c = self.ctx(course)
        us = [f"/mooc2-ans/exam/test?courseid={c.id}&clazzid={x['clazz_id']}&cpi={c.cpi}&ut=t&enc={c.enc}&t={c.t}" for x in c.classes] or \
             [f"/mooc2-ans/exam/test?{self.q(c)}"]
        return self.on(M2, f"""
            const out=[], seen=new Set();
            for(const u of {json.dumps(us)}){{ const d=D(await F(u));
              for(const l of d.querySelectorAll('li[data]')){{ if(!l.querySelector('.list_li_tit')||seen.has(l.getAttribute('data'))) continue; seen.add(l.getAttribute('data'));
                const cnt=T(l.querySelector('.piyuePcon'));
                out.push({{id:l.getAttribute('data'),paper_id:l.querySelector('.list_li_content')?.getAttribute('data'),title:T(l.querySelector('.list_li_tit')),
                 class:T(l.querySelector('.list_class')),time:T([...l.querySelectorAll('.list_li_time')].pop()).replace('考试时间：',''),
                 pending:(cnt.match(/(\\d+)\\s*待批/)||[])[1],submitted:(cnt.match(/(\\d+)\\s*已交/)||[])[1],unsubmitted:(cnt.match(/(\\d+)\\s*未交/)||[])[1]}}); }} }}
            return out;
        """)

    def papers(self, course: str) -> list[dict]:
        c = self.ctx(course)
        return self.on(M2, f"""
            const d=D(await F('/mooc2-ans/exam/paperlist?clazzid=-1&courseid={c.id}&ut=t&cpi={c.cpi}&topicid=0'));
            return [...d.querySelectorAll('ul.dataBody_td[data]')].filter(u=>u.getAttribute('type')=='1').map(u=>{{const li=u.querySelectorAll(':scope>li');
              const a=u.querySelector('.rename_title'), oc=a?(a.getAttribute('onclick')||''):'';
              const par=/paperLibLookPaper\\(\\s*\\d+\\s*,\\s*\\d+\\s*,\\s*'1'\\s*\\)/.test(oc), n=(T(u.querySelector('.random')).match(/(\\d+)\\s*套/)||[])[1];
              return {{paper_id:u.getAttribute('data'),title:T(a),questions:T(li[2]),score:T(li[3]),published:T(li[6]),created:(T(u.querySelector('.dataBody_time'))||'').slice(0,11),
                parallel:par?Number(n||0):null,unfinished:!!u.querySelector('.incomplete')}}}});
        """)

    def create_exam(self, course: str, title: str, questions: list[dict]) -> dict:
        """questions: [{"type":"判断","stem":"...","answer":"对","score":5}, {"type":"简答","stem":"..."}]"""
        c = self.ctx(course)
        pid = self.on(M2, f"return (await J('/mooc2-ans/exam/createAnEmptyPaper?_='+Date.now()+'&courseid={c.id}&clazzid={c.clazz_id}&pid=0&parallelpaper=0')).paperId;", retry_safe=False)
        if not pid:
            raise XxtError("创建空试卷失败")
        self.b.adopt_new_tab(f"https://mooc2-ans.chaoxing.com/mooc2-ans/exam/create-exampaper?courseid={c.id}&clazzid={c.clazz_id}&paperid={pid}&isCustomPaper=false&cpi={c.cpi}&ut=t")
        if not self.wait_for("return !!document.getElementById('examPaperTitle') && typeof saveFinish==='function'", timeout=20):
            raise XxtError("试卷编辑器未加载")
        self.here(f"const t=document.getElementById('examPaperTitle'); t.value={json.dumps(title)}; ['input','change','blur'].forEach(n=>t.dispatchEvent(new Event(n,{{bubbles:true}}))); try{{$(t).trigger('blur')}}catch(e){{}} return true;")
        for i, qd in enumerate(questions):
            qt = str(qd.get("type", "判断"))
            btn = "判断题" if (qt.startswith("判断") or qt.lower() in ("tf", "judge")) else "简答题"
            self.here(f"const b=[...document.querySelectorAll('span')].find(e=>e.offsetParent&&e.innerText.trim()==={json.dumps(btn)}); b.click(); return true;", retry_safe=False)
            time.sleep(1.5)
            ans = str(qd.get("answer", "对"))
            score = qd.get("score")
            score_js = ("const sc=[...document.querySelectorAll('input#score')].filter(e=>e.offsetParent).pop(); if(sc){sc.value=%s; sc.dispatchEvent(new Event('change',{bubbles:true}));}" % json.dumps(str(score))) if score else ""
            ok = self.here(f"""
                const ins=Object.values(UE.instants).filter(u=>u.key==='content'&&u.container&&u.container.offsetParent);
                const u=ins[ins.length-1]; if(!u) return 'no editor'; u.setContent({json.dumps(_html(str(qd.get('stem', ''))))}); try{{u.fireEvent('contentChange')}}catch(e){{}}
                if({json.dumps(btn)}==='判断题'){{const opts=[...document.querySelectorAll('a.num_option')].filter(e=>e.offsetParent);
                  const idx=(/^(对|正确|true|t|a|√|是)$/i.test({json.dumps(ans)}))?0:1; if(opts.length>=2) opts[opts.length-2+idx].click();}}
                {score_js}
                const sv=[...document.querySelectorAll('a.savebtn, a.jb_btn')].filter(e=>e.offsetParent&&e.innerText.trim()==='完成'&&!/saveFinish/.test(e.getAttribute('onclick')||''));
                if(!sv.length) return 'no save'; sv[sv.length-1].click(); return 'ok';
            """, retry_safe=False)
            if ok != "ok":
                raise XxtError(f"第 {i + 1} 题录入失败: {ok}")
            time.sleep(1.8)
        msg = self.here("saveFinish(); await new Promise(r=>setTimeout(r,1500)); const p=[...document.querySelectorAll('*')].find(e=>e.offsetParent&&/确认完成创建/.test(e.innerText||'')&&e.children.length<2); return p?p.innerText:'';", retry_safe=False)
        self.b.click_selector("a.confirmHref", settle=3)
        ps = [p for p in self.papers(c.id) if str(p["paper_id"]) == str(pid)]
        if not ps:
            raise XxtError(f"试卷 {pid} 没有出现在试卷库，请人工检查")
        return {"ok": True, "paper_id": str(pid), "title": ps[0]["title"], "questions": ps[0]["questions"], "score": ps[0]["score"], "confirm_text": msg}

    def publish_exam(self, course: str, paper: str, end_time: str | None, limit_minutes: int = 60, classes: list[str] | None = None) -> dict:
        c = self.ctx(course)
        p = _best(self.papers(c.id), paper, id_keys=("paper_id",))
        before = {e["id"] for e in self.exams(c.id)}
        self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/exam/test/topublish?taskid=0&clazzid=-1&courseid={c.id}&ut=t&cpi={c.cpi}&paperid={p['paper_id']}&score={p.get('score') or ''}")
        if not self.wait_for("return !!document.getElementById('choosepublish') && typeof publishpaper==='function'", timeout=20):
            raise XxtError("考试发布页未加载")
        end = norm_time(end_time)
        st = self.here(self._select_classes_js(c, classes) + f"""
            const e=document.getElementById('endTime'); e.value={json.dumps(end)};
            const lt=document.getElementById('limitTime'); if(lt){{lt.value={json.dumps(str(limit_minutes))}; lt.dispatchEvent(new Event('change',{{bubbles:true}}));}}
            return {{to:T(document.querySelector('.selectClass')),end:e.value,limit:lt&&lt.value}};
        """, retry_safe=False)
        if not st or not st.get("to"):
            raise XxtError("没有选中发放对象（班级）")
        cf = self.here("publishpaper(); await new Promise(r=>setTimeout(r,1500)); const p=[...document.querySelectorAll('*')].find(e=>e.offsetParent&&/确认发布考试/.test(e.innerText||'')&&e.children.length<2); return p?p.innerText:'';", retry_safe=False)
        if not cf:
            raise XxtError("没有出现发布确认框（可能有必填项未填）")
        self.here("publishpaper(true); return true;", retry_safe=False)
        new = []
        for _ in range(5):
            time.sleep(2)
            new = [e for e in self.exams(c.id) if e["id"] not in before]
            if new:
                break
        return {"ok": bool(new), "exam": new[0] if new else None, "to": st.get("to"), "end": st.get("end"), "limit_minutes": st.get("limit"), "confirm_text": cf}

    def delete_exam(self, course: str, exam: str, delete_paper: bool = False) -> dict:
        c = self.ctx(course)
        e = _best(self.exams(c.id), exam, id_keys=("id", "paper_id"))
        r = self.on(M2, f"return await J('/mooc2-ans/exam/test/delete-test?id={e['id']}&courseid={c.id}&clazzid={c.clazz_id}&ut=t&cpi={c.cpi}&recyle=1');", retry_safe=False)
        out = {"deleted_exam": e["title"], "server": r}
        if delete_paper and e.get("paper_id"):
            out["paper"] = self._del_paper(c, e["paper_id"])
        out["ok"] = not [x for x in self.exams(c.id) if x["id"] == e["id"]]
        return out

    def _del_paper(self, c: Course, pid: str):
        return self.on(M2, f"return await J('/mooc2-ans/exam/deletepaper?courseid={c.id}&clazzid={c.clazz_id}&cpi={c.cpi}&ut=t&status=2',POST({{courseid:'{c.id}',clazzid:'{c.clazz_id}',cpi:'{c.cpi}',ut:'t',status:'2',paperids:'{pid}'}}));", retry_safe=False)

    def delete_paper(self, course: str, paper: str) -> dict:
        c = self.ctx(course)
        p = _best(self.papers(c.id), paper, id_keys=("paper_id",))
        r = self._del_paper(c, p["paper_id"])
        return {"ok": not [x for x in self.papers(c.id) if x["paper_id"] == p["paper_id"]], "deleted_paper": p["title"], "server": r}

    def exam_marklist(self, course: str, exam: str) -> dict:
        c = self.ctx(course)
        e = _best(self.exams(c.id), exam, id_keys=("id", "paper_id"))
        self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/exam/test/marklist?clazzid={c.clazz_id}&courseid={c.id}&ut=&cpi={c.cpi}&id={e['id']}&paperId={e['paper_id']}&reviewclassid=0&prePageNum=1&prePageSize=12&topicid=0&perspectiveType=0")
        rows_js = """
            const by={};
            document.querySelectorAll('.layui-table-box tr[data-index]').forEach(r=>{const i=r.getAttribute('data-index'); const o=by[i]||(by[i]={});
              r.querySelectorAll('td[data-field]').forEach(td=>{const f=td.getAttribute('data-field'); const v=T(td); if(!/^\\d+$/.test(f)&&!td.classList.contains('layui-hide')&&v&&!o[f]) o[f]=v;});});
            return Object.keys(by).sort((a,b)=>a-b).map(k=>by[k]).filter(o=>Object.keys(o).length);"""
        self.wait_for("return /共\\d+名学生/.test(document.body.innerText)", timeout=15)
        head = self.here("const tx=document.body.innerText; const m=tx.match(/共(\\d+)名学生/); const s=tx.match(/已交\\s*(\\d+)/); const u=tx.match(/未交\\s*(\\d+)/); return {total:m&&m[1],submitted:s&&s[1],unsubmitted:u&&u[1]};")
        sub = self.here(rows_js)
        return {"exam": e["title"], "exam_id": e["id"], "paper_id": e["paper_id"], **(head or {}), "visible_rows": sub, "submitted_rows": None, "unsubmitted_rows": None,
                "grading_note": "已交及未交名单均未核实；当前可见列表含义及筛选切换尚未验证。逐题打分请在批阅页人工完成。"}

    # ================================================================ discussions
    def _bbsid(self, c: Course) -> str:
        if c.bbsid:
            return c.bbsid
        # The new course shell (fanyav3) returns the discussion entry, bbsid
        # included, from coursemanagev3/base-info. The old UI's iframe/app-card
        # scraping no longer exists after isNewCourse redirects to the Vue shell.
        url = self.shell_info(c).get("discuss_url") or ""
        m = re.search(r"[?&]bbsid=([0-9A-Fa-f]{16,64})(?:&|$)", url)
        if not m:
            raise XxtError("课程信息中没有讨论区入口（课程可能未开启讨论）")
        c.bbsid = m.group(1)
        return c.bbsid

    def topics(self, course: str, limit: int = 50) -> list[dict]:
        c = self.ctx(course)
        bbs = self._bbsid(c)
        result = self.on(GROUP, f"""
            const j=await J('/course/topic/{bbs}/getTopicList?folder_uuid=&page=1&pageSize={int(limit)}&kw=&courseId={c.id}&isSetTop=&selectedStartTime=&selectedEndTime=&selectedType=0&learnSilverStartTime=&learnSilverEndTime=&lastAuxValue=');
            // Observed 2026-11: an empty forum answers status:true with NO datas field
            // (keys: update_time,userAuth,member,folder_list,poff,circle,status).
            // Only that exact success shape counts as an empty list.
            if(j?.status===true && j.datas===undefined && j.userAuth && Array.isArray(j.folder_list)) return {{valid:true,items:[]}};
            if(!Array.isArray(j?.datas) || j?.status===false || j?.success===false) return {{valid:false}};
            if(j.datas.some(x=>!x || !x.uuid || typeof x.title!=='string')) return {{valid:false}};
            return {{valid:true,items:j.datas.map(x=>({{topic_id:x.uuid,id:String(x.id),title:x.title,content:(x.content||'').slice(0,200),author:x.createrName,replies:x.reply_count,reads:x.readPersonCount,time:x.ftime}}))}};
        """)
        if not isinstance(result, dict) or result.get("valid") is not True or not isinstance(result.get("items"), list):
            raise XxtError("讨论列表响应失败或结构不完整；不能视为空列表。")
        return result["items"]

    def create_topic(self, course: str, title: str, content: str) -> dict:
        c = self.ctx(course)
        bbs = self._bbsid(c)
        self.b.navigate(f"https://groupweb.chaoxing.com/course/topic/topicList?courseid={c.id}&clazzid={c.clazz_id}&cpi={c.cpi}&bbsid={bbs}&supportAI=true", settle=1.0)
        if not self.wait_for("return typeof UE!=='undefined'&&Object.keys(UE.instants||{}).length>0&&!!document.querySelector('.edit_btn .jb_btn')", timeout=20):
            raise XxtError("讨论编辑器未加载")
        st = self.here(f"""
            const t=[...document.querySelectorAll('input')].find(e=>e.offsetParent&&e.placeholder==='请输入标题'); if(!t) return 'no title';
            t.focus(); t.value={json.dumps(title)}; ['input','keyup','change'].forEach(n=>t.dispatchEvent(new Event(n,{{bubbles:true}})));
            const u=Object.values(UE.instants)[0]; u.setContent({json.dumps(_html(content))}); try{{u.fireEvent('contentChange')}}catch(e){{}}
            await new Promise(r=>setTimeout(r,400));
            const b=document.querySelector('.edit_btn .jb_btn'); if(/disable/.test(b.className)) return 'button disabled'; b.click(); return 'ok';
        """, retry_safe=False)
        if st != "ok":
            raise XxtError(f"发布讨论失败: {st}")
        hit = []
        for _ in range(4):
            time.sleep(2)
            hit = [t for t in self.topics(c.id) if t["title"] == title]
            if hit:
                break
        if not hit:
            raise XxtError("点击了“发布”，但话题列表里没有找到，请人工检查（不要重复发布）")
        # leave the editor page (it would raise beforeunload later). The write is already verified,
        # so this is the one place where accepting a beforeunload is allowed.
        self.b.navigate(BASE_PAGE[GROUP], settle=0.2, allow_leave=True)
        return {"ok": True, "topic": hit[0]}

    def delete_topic(self, course: str, topic: str) -> dict:
        c = self.ctx(course)
        bbs = self._bbsid(c)
        t = _best(self.topics(c.id, 200), topic, id_keys=("topic_id", "id"))
        r = self.on(GROUP, f"return await J('/pc/topic/{bbs}/{t['topic_id']}/deleteTopic?_t='+Date.now());", retry_safe=False)
        return {"ok": bool(isinstance(r, dict) and r.get("status")), "deleted": t["title"], "server": r}
