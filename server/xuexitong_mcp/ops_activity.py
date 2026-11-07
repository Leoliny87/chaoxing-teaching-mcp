"""教学活动 (签到/选人/抢答/投票...), inbox, page tools, health check."""
from __future__ import annotations

import datetime as _dt
from dataclasses import replace
import json
import re
import time
from pathlib import Path
from typing import Any

from .bsk import BskError, FIXED_HOMEPAGE
from .privacy import safe_browser_error_details, safe_error_text
from .xxt import (ACTIVE_STATUS, BASE_PAGE, ML, NOTICE, SIGN_TYPES, _G, Course, XxtBase, XxtError, _best, _safe_id)


_ATYPE = {2: "签到", 4: "抢答", 11: "选人", 14: "问卷", 42: "随堂练习", 43: "投票", 45: "通知", 5: "主题讨论", 23: "评分", 35: "分组任务", 17: "直播",
          44: "资料", 46: "学生反馈", 47: "计时器", 49: "白板", 64: "AI实践", 80: "抽签"}


class ActivityOps(XxtBase):
    def _act_list_url(self, c: Course) -> str:
        return (f"https://mobilelearn.chaoxing.com/page/active/activeList?courseId={c.id}&clazzId={c.clazz_id}&cpi={c.cpi}"
                f"&ut=t&fid={self.fid}&showInvitecode=1&newVersion=1&classId={c.clazz_id}")

    def activities(self, course: str, status: str = "", limit: int = 50, *, class_id: str = "") -> list[dict]:
        c = self.ctx(course)
        if class_id:
            matches = [x for x in c.classes if str(x.get("clazz_id", "")) == str(class_id)]
            if len(matches) != 1:
                raise XxtError("目标班级不存在或不唯一，停止读取活动列表。")
            c = replace(c, clazz_id=_safe_id(class_id))
        result = self.on(ML, f"""
            const j=await J('/v2/apis/active/pcActivelist?fid={self.fid}&courseId={c.id}&classId={c.clazz_id}&types=&userid=&groupId=&_='+Date.now());
            const raw=j?.data?.activeList;
            if(j?.result!==1||!Array.isArray(raw)) return {{valid:false}};
            const items=raw.map(a=>{{
              if(!a||typeof a!=='object'||!/^\\d+$/.test(String(a.activeId??''))||
                 !/^\\d+$/.test(String(a.activeType??''))||!/^\\d+$/.test(String(a.status??''))||
                 typeof a.typeTitle!=='string'||typeof a.title!=='string') return null;
              let notice_id='';
              if(Number(a.activeType)===45&&String(a.classId)==={json.dumps(c.clazz_id)}){{
                try{{const content=JSON.parse(a.content);
                  if(content&&typeof content==='object'&&!Array.isArray(content)&&typeof content.idCode==='string'&&/^[A-Fa-f0-9]{{32}}$/.test(content.idCode))
                    notice_id=content.idCode.toUpperCase();
                }}catch{{}}
              }}
              return {{activity_id:String(a.activeId),title:a.typeTitle,type:a.title,active_type:a.activeType,status:String(a.status),
                 start:a.startTime,end:a.endTime,...(notice_id?{{notice_id,class_id:String(a.classId)}}:{{}})}};
            }});
            return {{valid:items.every(Boolean),items}};
        """)
        if not isinstance(result, dict) or result.get("valid") is not True or not isinstance(result.get("items"), list):
            raise XxtError("活动列表响应失败或结构不完整；不能视为空列表。")
        lst = result["items"]
        out = []
        for a in lst:
            a["status_name"] = ACTIVE_STATUS.get(a["status"], a["status"])
            a["type"] = _ATYPE.get(int(a.get("active_type") or 0), a["type"])
            if status and status not in (a["status"], a["status_name"]):
                continue
            out.append(a)
        return out[:limit]

    def _find_activity(self, c: Course, a: str) -> dict:
        return _best(self.activities(c.id, limit=1000, class_id=c.clazz_id), a, id_keys=("activity_id",))

    def _activity_class(self, course: str, class_id: str) -> Course:
        """Resolve the exact previewed class ID again without changing cached defaults."""
        if not class_id:
            raise XxtError("发起活动必须明确指定一个班级 ID。")
        c = self.ctx(course, refresh=True)
        matches = [x for x in c.classes if str(x.get("clazz_id", "")) == str(class_id)]
        if len(matches) != 1:
            raise XxtError("预演的班级已不存在或不唯一，停止发起活动。")
        return replace(c, clazz_id=_safe_id(class_id))

    def _open_add_activity(self, c: Course, kind: str):
        self.b.navigate(self._act_list_url(c), settle=1.5)
        self.wait_for("return document.readyState==='complete' && !!document.querySelector('.add-activate-icon')", timeout=15)
        if not self.here("return !!window.__xxtNoAppGuard"):
            raise XxtError("教学活动页未检测到 no-app-popup 防护扩展（jsbridge 会卡住 bsk）。请先按 README 加载扩展。")
        self.b.click_selector(".add-activate-icon", settle=1.5)
        self.b.click_label(r'(?:button|link) "' + re.escape(kind) + r'"', settle=2.5)

    def _started(self, c: Course, title: str, before: set[str]) -> dict:
        url = ""
        url_id = ""
        for _ in range(8):
            url = self.b.href()
            m = re.search(r"activeId=(\d+)", url or "")
            if m and "activeList" not in url:
                url_id = m.group(1)
                break
            time.sleep(1)
        for _ in range(3):
            new = [a for a in self.activities(c.id, limit=1000, class_id=c.clazz_id) if a["activity_id"] not in before and a["title"] == title]
            if url_id:
                new = [a for a in new if a["activity_id"] == url_id]
            if len(new) == 1:
                return {"activity_id": new[0]["activity_id"], "status": new[0]["status_name"], "page": url}
            if len(new) > 1:
                raise XxtError("出现多个同名新活动，无法确认目标；请人工检查，不要重复创建。")
            time.sleep(1.5)
        raise XxtError("点击了“立即开始”，但不能核实新活动 ID、标题及班级，请人工检查（不要重复创建）")

    # ---------------------------------------------------------------- 签到
    def start_checkin(self, course: str, title: str, sign_type: str = "普通", code: str = "", gesture: str = "", address: str = "", class_id: str = "") -> dict:
        c = self._activity_class(course, class_id)
        st = (sign_type or "普通").replace("签到", "").strip().lower() or "普通"
        if st not in SIGN_TYPES:
            raise XxtError(f"签到类型必须是 普通/手势/位置/二维码/签到码，收到: {sign_type}")
        bar = SIGN_TYPES[st]
        if bar == 5 and not re.fullmatch(r"\d{4,8}", code or ""):
            raise XxtError("签到码签到需要 4-8 位数字签到码 code")
        if bar == 3:
            gesture = re.sub(r"\D", "", gesture or "")
            if len(gesture) < 4 or len(set(gesture)) != len(gesture) or "0" in gesture:
                raise XxtError("手势签到需要至少4个不重复的点，例如 gesture='12369'（九宫格1-9，从左上开始按行编号）")
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=c.clazz_id)}
        self._open_add_activity(c, "签到")
        if not self.wait_for("return !!document.getElementById('signTitle')", timeout=10):
            raise XxtError("签到表单未出现")
        self.here(f"""const t=document.getElementById('signTitle'); t.focus(); t.value={json.dumps(title)}; ['input','keyup','change'].forEach(n=>t.dispatchEvent(new Event(n,{{bubbles:true}})));
                     document.getElementById('typebar{bar}').click(); return true;""", retry_safe=False)
        time.sleep(1.2)
        location = ""
        if bar == 5:
            self.b.fill_label(r'textbox "(Number code|[^"]*签到码[^"]*)"', code)
        elif bar == 3:
            pts = [_G[int(ch)] for ch in gesture]
            r = self.here(f"""
                const c=[...document.querySelectorAll('canvas.main-c')].find(e=>e.offsetParent); if(!c) return 'no canvas';
                const r=c.getBoundingClientRect(); const P={json.dumps(pts)}; const pts=[];
                for(let i=0;i<P.length-1;i++){{for(let k=0;k<=20;k++){{pts.push([P[i][0]+(P[i+1][0]-P[i][0])*k/20,P[i][1]+(P[i+1][1]-P[i][1])*k/20])}}}}
                const ev=(t,p)=>c.dispatchEvent(new MouseEvent(t,{{bubbles:true,cancelable:true,clientX:r.x+p[0],clientY:r.y+p[1],buttons:1,view:window}}));
                ev('mousedown',pts[0]); pts.forEach(p=>ev('mousemove',p)); ev('mouseup',pts[pts.length-1]); return 'ok';""", retry_safe=False)
            if r != "ok":
                raise XxtError(f"手势绘制失败: {r}")
        elif bar == 4:
            location = self._pick_location(address)
        self.b.click_selector("#signin_begin", settle=3)
        info = self._started(c, title, before)
        out = {"ok": True, "title": title, "sign_type": sign_type, **info}
        if bar == 4:
            out["location"] = location
        if code:
            out["code"] = code
        if gesture:
            out["gesture"] = gesture
        return out

    def _pick_location(self, address: str) -> str:
        """Turn on 指定签到地点. Default location = the school's (pre-filled by 学习通).
        With `address`, try the map picker search (best effort)."""
        on = self.here("const i=document.getElementById('ifopenAddress'); return i?i.checked:null;")
        if on is None:
            raise XxtError("找不到“指定签到地点”开关")
        if not on:
            self.b.click_selector("#ifopenAddress-div", settle=1.5)
        self.b.sync()
        ref_line = next((ln for ln in self.b.obs_text.splitlines() if re.search(r'@e\d+ button "定位', ln)), "")
        loc = re.search(r'button "定位\s*([^"]*)"', ref_line)
        loc_text = loc.group(1).strip() if loc else ""
        if address:
            self.b.click_label(r'button "定位', settle=3)
            try:
                self.b.fill_label(r'textbox "(Address detail|[^"]*(地址|搜索)[^"]*)"', address)
                time.sleep(3)
                ctx, _ = self.b.sync()
                lines = [ln for ln in self.b.obs_text.splitlines() if re.search(r'@e\d+ (button|listitem|link) "[^"]{4,}"', ln) and address[:2] in ln and "定位" not in ln]
                if lines:
                    self.b.run(["click", re.search(r"@e\d+", lines[0]).group(0), "--context", ctx])
                    time.sleep(1.5)
                self.b.click_label(r'(link|button) "确定"', settle=1.5)
            except BskError as e:
                raise XxtError(f"地图选点失败（{safe_error_text(e)}）。可以不传 address，使用默认的学校位置。")
            self.b.sync()
            ref_line = next((ln for ln in self.b.obs_text.splitlines() if re.search(r'@e\d+ button "定位', ln)), "")
            loc = re.search(r'button "定位\s*([^"]*)"', ref_line)
            loc_text = loc.group(1).strip() if loc else loc_text
        return loc_text

    def checkin_status(self, course: str, activity: str) -> dict:
        c = self.ctx(course)
        a = self._find_activity(c, activity)
        self.b.navigate(f"https://mobilelearn.chaoxing.com/page/sign/endSign?activeId={a['activity_id']}&classId={c.clazz_id}&courseId={c.id}&cpi={c.cpi}&showOnScreenShare=true&returnType=1&fid={self.fid}", settle=2)
        self.wait_for("return /已签/.test(document.body.innerText)", timeout=12)
        js = """
            const tx=document.body.innerText; const m1=tx.match(/已签\\s*\\(?(\\d+)\\)?/), m2=tx.match(/未签\\s*\\(?(\\d+)\\)?/), m3=tx.match(/签到率\\s*([\\d.]+%)/);
            const i=tx.indexOf('状态筛选'); const tail=i>=0?tx.slice(i+4,i+1500):'';
            return {signed:m1&&m1[1],unsigned:m2&&m2[1],rate:m3&&m3[1],list:tail.split('\\n').map(s=>s.trim()).filter(Boolean).slice(0,80)};"""
        s1 = self.here(js)
        return {"activity": a["title"], "activity_id": a["activity_id"], "status": a["status_name"], "signed": s1.get("signed"),
                "unsigned": s1.get("unsigned"), "rate": s1.get("rate"), "visible_list": s1.get("list"), "signed_list": None, "unsigned_list": None,
                "note": "已签及未签名单均未核实；当前可见列表含义及筛选切换尚未验证。"}

    def activity_page(self, course: str, activity: str) -> dict:
        c = self.ctx(course)
        a = self._find_activity(c, activity)
        t = int(a.get("active_type") or 0)
        path = {2: "/page/sign/endSign", 11: "/page/selectperson/selectPerson", 4: "/page/answer/teaQuickAnswer",
                43: "/page/qvote/qvoteStatistics", 14: "/page/quiz/quizStatistics", 42: "/page/quiz/quizStatisticsPage"}.get(t)
        if not path:
            return {"activity": a, "note": "该类型活动没有已知的统计页，请在学习通里查看"}
        self.b.navigate(f"https://mobilelearn.chaoxing.com{path}?activeId={a['activity_id']}&classId={c.clazz_id}&courseId={c.id}&cpi={c.cpi}&fid={self.fid}&showOnScreenShare=true&returnType=1" + ("&viewType=2" if t == 14 else ""), settle=2.5)
        txt = self.here("return document.body.innerText.replace(/\\n{2,}/g,'\\n').slice(0,3000)")
        return {"activity": a["title"], "activity_id": a["activity_id"], "type": a["type"], "status": a["status_name"], "page_text": txt}

    def end_activity(self, course: str, activity: str, class_id: str = "") -> dict:
        c = self._activity_class(course, class_id)
        a = self._find_activity(c, activity)
        if a["status"] != "1":
            raise XxtError(f"活动当前状态为「{a['status_name']}」，不再是进行中；未提交结束。")
        self.b.navigate(self._act_list_url(c), settle=1.5)
        if not self.wait_for("return typeof app!=='undefined' && typeof app.endActive==='function'", timeout=15):
            raise XxtError("活动列表未加载")
        self.here(f"app.endActive({json.dumps(_safe_id(a['activity_id']))},{json.dumps(_safe_id(a['active_type']))}); return true;", retry_safe=False)
        now = []
        for _ in range(4):
            time.sleep(1.5)
            now = [x for x in self.activities(c.id, limit=1000, class_id=c.clazz_id) if x["activity_id"] == a["activity_id"]]
            if now and now[0]["status"] == "2":
                break
        return {"ok": bool(now and now[0]["status"] == "2"), "activity": a["title"], "status": now[0]["status_name"] if now else "?"}

    def delete_activity(self, course: str, activity: str) -> dict:
        c = self.ctx(course)
        a = self._find_activity(c, activity)
        self.b.navigate(self._act_list_url(c), settle=1.5)
        if not self.wait_for("return typeof app!=='undefined' && typeof app.deleteActive==='function'", timeout=15):
            raise XxtError("活动列表未加载")
        self.here(f"app.deleteActive({json.dumps(_safe_id(a['activity_id']))}); return true;", retry_safe=False)
        still = [1]
        for _ in range(4):
            time.sleep(1.5)
            still = [x for x in self.activities(c.id, limit=1000) if x["activity_id"] == a["activity_id"]]
            if not still:
                break
        return {"ok": not still, "deleted": a["title"], "note": "已移入活动回收站，可还原"}

    # ---------------------------------------------------------------- 选人 / 抢答 / 投票
    def pick_student(self, course: str, title: str, count: int = 1, class_id: str = "") -> dict:
        c = self._activity_class(course, class_id)
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=c.clazz_id)}
        self._open_add_activity(c, "选人")
        self.b.fill_label(r'textbox "请输入选人事由"', title)
        if count and int(count) != 1:
            self.b.fill_label(r'spinbutton', str(int(count)))
        self.b.click_label(r'link "立即开始"', settle=3)
        info = self._started(c, title, before)
        # the activity now exists: never raise from here on (a retry would create a duplicate)
        picked, note = "", ""
        try:
            self.b.click_label(r'button "[^"]*(开始选人|继续选人)"', settle=3.5)
            for _ in range(5):
                picked = self.here("const m=document.body.innerText.match(/选中[:：]\\s*([^\\n]+)/); return m?m[1].trim():'';") or ""
                if picked:
                    break
                time.sleep(1)
        except BskError as e:
            if e.code == "permission_denied":
                return {"ok": False, "title": title, **info, "activity_created": True, "picked": None,
                        "error": "选人活动已创建，开始选人返回权限拒绝，选人结果未确认；不要重复创建或点击，先查看该活动状态。"}
            note = f"选人活动已创建，但自动点击“开始选人”失败（{e}）。可在活动页手动点击，或用 activity_result 查看。"
        except XxtError as e:
            note = f"选人活动已创建，但自动点击“开始选人”失败（{e}）。可在活动页手动点击，或用 activity_result 查看。"
        out = {"ok": True, "title": title, **info, "picked": picked}
        if note:
            out["note"] = note
        return out

    def start_quick_answer(self, course: str, content: str, class_id: str = "") -> dict:
        c = self._activity_class(course, class_id)
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=c.clazz_id)}
        self._open_add_activity(c, "抢答")
        self.b.fill_label(r'textbox "请输入抢答内容"', content)
        self.b.click_label(r'link "立即开始"', settle=3)
        return {"ok": True, "content": content, **self._started(c, content, before)}

    def start_vote(self, course: str, content: str, options: str = "选A/选B/选C/选D", class_id: str = "") -> dict:
        c = self._activity_class(course, class_id)
        presets = ["赞同/反对", "正确/错误", "选A/选B", "选A/选B/选C/选D"]
        if options not in presets:
            raise XxtError(f"options 只能是 {presets}")
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=c.clazz_id)}
        self._open_add_activity(c, "投票")
        self.b.fill_label(r'textbox "请输入投票内容"', content)
        self.b.click_label(r'button "%s"$' % re.escape(options), settle=1.2)
        self.b.click_label(r'link "立即开始"', settle=3)
        return {"ok": True, "content": content, "options": options, **self._started(c, content, before)}

    # ================================================================ inbox
    def inbox(self, limit: int = 20, unread_only: bool = False) -> list[dict]:
        r = self.on(NOTICE, """
            const j=await J('/mobile/notice/getNoticeList?type=2&tag=');
            if(!Array.isArray(j?.notices?.list)) return {valid:false};
            return {valid:true,items:j.notices.list.map(x=>({id:x.idCode,title:x.title,from:x.createrName,time:x.completeTime,read:!!x.isread,content:(x.content||'').slice(0,300)}))};""")
        if not isinstance(r, dict) or r.get("valid") is not True or not isinstance(r.get("items"), list):
            raise XxtError("收件箱响应失败或结构不完整；不能视为空列表。")
        items = [x for x in r["items"] if not unread_only or not x["read"]]
        return items[:limit]

    # ================================================================ page tools
    def read_page(self, url: str = "", max_chars: int = 4000, with_refs: bool = False) -> dict:
        from .xxt import check_read_url
        if url:
            # Merely opening a seemingly read-only page can initialise server
            # state. Host/keyword checks cannot establish that navigation is safe.
            raise XxtError("通用页面自动导航已暂停：无法确认目标页面不会自动创建或修改数据。请先人工打开并核实当前页面。")
        # re-check where we actually are (redirects, or the current page when url == "")
        here = self.b.href() or ""
        try:
            check_read_url(here, final=True)
        except XxtError:
            raise XxtError("页面跳转到了白名单以外的网址，已停止读取")
        info = self.here(f"return {{url:location.href,title:document.title,text:document.body?document.body.innerText.replace(/\\n{{2,}}/g,'\\n').slice(0,{int(max_chars)}):''}};")
        if with_refs:
            self.b.sync()
            lines = [ln.strip()[:160] for ln in self.b.obs_text.splitlines() if "@e" in ln][:200]
            info["interactive"] = "\n".join(lines)
        return info

    def screenshot(self, full_page: bool = False) -> str:
        d = self.cfg.download_dir / "screenshots"
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"xxt-{_dt.datetime.now():%Y%m%d-%H%M%S}.png"
        return self.b.screenshot(str(out), full_page=full_page)

    # ================================================================ health
    def health(self) -> dict:
        res: dict[str, Any] = {}
        step = "doctor"
        try:
            doc = self.b.doctor()
            bad = [d.get("name") + ": " + str(d.get("detail")) for d in doc if isinstance(d, dict) and not d.get("ok")]
            res["bsk_doctor"] = "ok" if not bad else bad
            if any("extension connected" in b for b in bad):
                res["ok"] = False
                res["hint"] = "Chrome 里的 BrowserSkill 扩展没有连接：请确认 Chrome 已打开，点击一下扩展图标或刷新任意页面让它重新连接（不需要重启 Chrome）。"
                return res
        except BskError as e:
            res["bsk_doctor"] = f"失败: {safe_error_text(e)}"
            res["browser_error"] = safe_browser_error_details(e, health_step=step)
            self.b.preserve_tab = True
            res["ok"] = False
            return res
        pol = Path("/etc/opt/chrome/policies/managed/xuexitong.json")
        try:
            pj = json.loads(pol.read_text())
            res["chrome_policy"] = {"present": True, "url_blocklist": len(pj.get("URLBlocklist", [])), "forced_languages": pj.get("ForcedLanguages")}
        except (OSError, ValueError):
            res["chrome_policy"] = {"present": False, "hint": "未安装全局 Chrome 策略；可单独检查防弹窗扩展与浏览器语言。"}
        try:
            step = "session"
            self.b.ensure_session(renew_idle_readonly=True)
            # Report only that control is bound; session/tab handles stay internal.
            res["session"] = {"bound": isinstance(self.b.session, str) and isinstance(self.b.tab, int)}
            step = "login"
            lg = self.on(NOTICE, "const r=await fetch('/mobile/notice/getNoticeList?type=2&tag=&lastValue=',{credentials:'include'}); if(!r.ok) return {ok:false,http_status:r.status}; const t=await r.text(); try{const j=JSON.parse(t); return {ok:Array.isArray(j?.notices?.list)}}catch(e){return {ok:false,url:r.url}}")
            res["login"] = "已登录" if isinstance(lg, dict) and lg.get("ok") else f"未登录或登录已过期，请在 Chrome 中手动登录学习通（{lg}）"
            if res["login"] == "已登录" and getattr(self.b, "_login_handoff", False):
                self.b.preserve_tab = False
                self.b._login_handoff = False
            step = "guard_navigation"
            # HTML page on mobilelearn; 'load' can hang on this page, so only wait for DOMContentLoaded
            self.b.navigate(f"https://mobilelearn.chaoxing.com/page/active/activeList?courseId=0&clazzId=0&cpi=0&ut=t&fid={self.fid}",
                            wait="domcontentloaded", settle=1.0)
            step = "guard_read"
            g = self.here("return {guard:!!window.__xxtNoAppGuard, lang:navigator.language}")
            res["guard_extension"] = bool(g.get("guard"))
            res["browser_language"] = g.get("lang")
            step = "courses"
            cs = self.courses(refresh=True)
            res["courses"] = len(cs)
            step = "language_read"
            sample = self.here("return document.body.innerText.slice(0,300)") or ""
            res["ui_language"] = "中文" if re.search(r"(我教的课|我学的课|新建课程)", sample) else ("English" if re.search(r"Teaching|Learning|New Create", sample) else "未知")
        except BskError as e:
            res["error"] = f"BskError: {safe_error_text(e)}"
            if e.code != "login_required":
                self.b.preserve_tab = True
                self.b._login_handoff = False
            res["browser_error"] = safe_browser_error_details(e, health_step=step)
            if e.code == "login_required":
                res.update(login="未登录", needs_human=True, login_url=FIXED_HOMEPAGE,
                           hint="请本人在固定 local_browser / example-browser-id Profile 手动登录学习通；不要提交密码到聊天，也不要切换浏览器实例或自动重试。")
                if isinstance(self.b.session, str) and isinstance(self.b.tab, int):
                    res["session"] = {"bound": True}
        except Exception as e:  # report, don't raise
            res["error"] = safe_error_text(e)
        res["ok"] = (res.get("bsk_doctor") == "ok" and res.get("guard_extension") is True
                     and res.get("login") == "已登录" and res.get("ui_language") == "中文"
                     and isinstance(res.get("courses"), int) and "error" not in res)
        return res
