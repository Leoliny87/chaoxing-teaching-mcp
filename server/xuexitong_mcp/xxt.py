"""学习通 domain client: course resolution/context cache and every teacher operation.

Strategy (fast path first):
  * Reads use same-origin fetch() executed inside the page (one sync + one evaluate),
    parsing HTML with DOMParser or reading the JSON endpoints the pages themselves use.
  * Writes go through the real UI when the site has a complex form (notice, assignment,
    exam, topic, activities, upload) and through the page's own endpoint when the UI is
    just a confirm dialog around one request (delete, remind, end activity...).
  * Every write is verified afterwards by re-reading the list (verify-after-write).
"""
from __future__ import annotations

import datetime as _dt
import difflib
import html as _h
import json
import re
import shutil
import tempfile
import time
import urllib.parse as up
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bsk import Bsk, BskError, JsError
from .config import Config

M2 = "mooc2-ans.chaoxing.com"
M1 = "mooc1.chaoxing.com"
NOTICE = "notice.chaoxing.com"
GROUP = "groupweb.chaoxing.com"
ML = "mobilelearn.chaoxing.com"
STAT = "stat2-ans.chaoxing.com"

# light same-origin pages used as a fetch() base for each host
BASE_PAGE = {
    M2: "https://mooc2-ans.chaoxing.com/mooc2-ans/js/ServerHost.js",
    M1: "https://mooc1.chaoxing.com/mooc-ans/js/ServerHost.js",
    NOTICE: "https://notice.chaoxing.com/res/js/domain.js",
    GROUP: "https://groupweb.chaoxing.com/res/js/common/template-web.js",
    ML: "https://mobilelearn.chaoxing.com/favicon.ico",
    STAT: "https://stat2-ans.chaoxing.com/favicon.ico",
}

JS_PRELUDE = r"""
const F=async(u,o)=>{const r=await fetch(u,Object.assign({credentials:'include'},o||{}));if(!r.ok) throw Error('请求失败，HTTP '+r.status);return await r.text();};
const J=async(u,o)=>{const t=await F(u,o);try{return JSON.parse(t)}catch(e){try{return JSON.parse(t.replace(/(\w+):/g,'"$1":'))}catch(e2){throw Error('响应不是有效 JSON')}}};
const POST=(obj)=>({method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:new URLSearchParams(obj).toString()});
const D=(h)=>new DOMParser().parseFromString(h,'text/html');
const T=(e)=>e?(e.textContent||'').replace(/\s+/g,' ').trim():'';
"""

ACTIVE_STATUS = {"0": "未开始", "1": "进行中", "2": "已结束"}

SIGN_TYPES = {  # name -> typebar id
    "普通": 0, "normal": 0, "手势": 3, "gesture": 3, "位置": 4, "location": 4,
    "二维码": 2, "qrcode": 2, "qr": 2, "签到码": 5, "码": 5, "code": 5,
}

# gesture grid coordinates on the 120x120 canvas (1..9, row-major)
_G = {1: (20, 18), 2: (59, 18), 3: (99, 18), 4: (20, 59), 5: (59, 59), 6: (99, 59), 7: (20, 99), 8: (59, 99), 9: (99, 99)}


class XxtError(RuntimeError):
    pass


class NeedsHuman(XxtError):
    pass


@dataclass
class Course:
    id: str
    name: str
    cpi: str
    role: str = "1"          # 1 = 我教的(创建/管理), 2 = 团队教师
    info: str = ""
    clazz_id: str = ""
    enc: str = ""
    t: str = ""
    classes: list[dict] = field(default_factory=list)
    bbsid: str = ""
    ctx_time: float = 0.0

    def brief(self) -> dict:
        return {"course_id": self.id, "name": self.name, "role": "主讲" if self.role == "1" else "团队教师", "info": self.info[:80]}


def _now_plus(days: int = 7) -> str:
    return (_dt.datetime.now() + _dt.timedelta(days=days)).replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def norm_time(s: str | None, default_days: int = 7) -> str:
    """Accept '2099-01-01 22:00', '2099-01-01', '+3d', '3天', '2h', '' -> 'YYYY-MM-DD HH:MM:SS'."""
    if not s:
        return _now_plus(default_days)
    s = s.strip()
    m = re.fullmatch(r"\+?(\d+)\s*(d|天|h|小时|m|分钟)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = _dt.timedelta(days=n) if unit in ("d", "天") else _dt.timedelta(hours=n) if unit in ("h", "小时") else _dt.timedelta(minutes=n)
        return (_dt.datetime.now() + delta).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%m-%d %H:%M"):
        try:
            d = _dt.datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                d = d.replace(hour=23, minute=59)
            if fmt == "%m-%d %H:%M":
                d = d.replace(year=_dt.datetime.now().year)
            return d.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise XxtError(f"无法识别的时间格式: {s}（请用 2099-01-01 22:00 或 +3d）")


def _best(items: list[dict], query: str, key: str = "title", id_keys: tuple[str, ...] = ("id",)) -> dict:
    """Pick one item by id (exact) or title (exact > contains > fuzzy). Raises on ambiguity."""
    q = str(query).strip()
    if not q:
        raise XxtError("请提供名称或ID")
    id_matches = [it for it in items if any(it.get(k) is not None and not isinstance(it.get(k), bool)
                                            and str(it.get(k)) == q for k in id_keys)]
    if len(id_matches) == 1:
        return id_matches[0]
    if len(id_matches) > 1:
        raise XxtError(f"ID「{q}」匹配到多项，无法确定目标；请先核对列表。")
    exact = [it for it in items if str(it.get(key, "")).strip() == q]
    if len(exact) == 1:
        return exact[0]
    show = lambda lst: json.dumps([{k: it.get(k) for k in id_keys + (key,)} for it in lst[:10]], ensure_ascii=False)
    if len(exact) > 1:
        raise XxtError(f"有 {len(exact)} 项同名「{q}」，请改用ID: " + show(exact))
    sub = [it for it in items if q.lower() in str(it.get(key, "")).lower()]
    if len(sub) == 1:
        return sub[0]
    if len(sub) > 1:
        raise XxtError(f"「{q}」匹配到多项，请说得更具体或用ID: " + show(sub))
    names = [str(it.get(key, "")) for it in items]
    close = difflib.get_close_matches(q, names, n=3, cutoff=0.45)
    # never auto-pick a fuzzy (difflib) match: a wrong pick could delete/remind the wrong item
    raise XxtError(f"找不到「{q}」。" + (f"你是不是指: {close}" if close else ""))


def _safe_id(v: Any) -> str:
    """IDs that get spliced into page JS / URLs must be plain tokens."""
    s = str(v)
    if not re.fullmatch(r"[0-9A-Za-z_\-]{1,64}", s):
        raise XxtError(f"意外的 ID 格式，已拒绝: {s[:40]!r}")
    return s


def _html(text: str, allow_html: bool = False) -> str:
    """Plain text -> <p> paragraphs. Raw HTML is escaped unless the caller explicitly allows it
    (content may come from an LLM that read untrusted pages; don't let it post <a>/<img>/<script>)."""
    text = text or ""
    if allow_html and re.search(r"<(p|br|div|img|a|b|strong)\b", text, re.I):
        return text
    return "".join(f"<p>{_h.escape(line) or '<br/>'}</p>" for line in text.split("\n"))


# ---------------------------------------------------------------- read_page URL policy
READ_HOSTS = frozenset({
    "mooc1.chaoxing.com", "mooc1-1.chaoxing.com", "mooc2-ans.chaoxing.com", "i.mooc.chaoxing.com",
    "notice.chaoxing.com", "groupweb.chaoxing.com", "mobilelearn.chaoxing.com", "stat2-ans.chaoxing.com",
    "fanyapbl.fy.chaoxing.com",
})
# GET endpoints that change state. Matched case-insensitively against path AND query.
_WRITE_HINT = re.compile(
    r"(?i:delete|setdel|remove|urge|create|save|publish|submit|export|logout|update|recycle|restore|upload|rename|finish|reply|batch)"
    r"|(?-i:(?:del|set|add|end|start|stop|send|move)[A-Z_])"
    r"|(?i:(?:^|/)(?:add|del|end|start|stop|send|move)(?:[/?]|$))")


def check_read_url(url: str, final: bool = False) -> str:
    """Strict allowlist for read_page. Returns the normalised URL or raises XxtError."""
    raw = str(url or "").strip()
    if not raw or any(ch in raw for ch in "\\\t\r\n ") or any(ord(ch) < 0x20 or ord(ch) > 0x7e for ch in raw):
        raise XxtError("网址包含不允许的字符（反斜杠/空白/非 ASCII）")
    u = up.urlsplit(raw)
    if u.scheme.lower() != "https":
        raise XxtError("只允许 https 网址")
    if "@" in u.netloc or u.username or u.password:
        raise XxtError("网址里不允许出现用户名/@")
    if u.port not in (None, 443):
        raise XxtError("不允许自定义端口")
    host = (u.hostname or "").lower()
    if host not in READ_HOSTS:
        raise XxtError(f"只允许打开这些学习通域名：{sorted(READ_HOSTS)}（收到 {host or '空'}）")
    if not final and _WRITE_HINT.search(u.path + "?" + u.query):
        raise XxtError("该网址看起来会修改数据，read_page 不允许打开")
    return up.urlunsplit(("https", host, u.path, u.query, ""))


class XxtBase:
    def __init__(self, cfg: Config, bsk: Bsk | None = None):
        self.cfg = cfg
        self.b = bsk or Bsk(cfg)
        self._courses: list[Course] = []
        self._courses_time = 0.0
        self.fid = cfg.fid

    # ================================================================ plumbing
    def on(self, host: str, body: str, *, retry_safe: bool = True, timeout: float | None = None) -> Any:
        """Run JS `body` (async function body, may use F/J/POST/D/T helpers) on an origin of `host`."""
        js = JS_PRELUDE + f"if(location.host!=={json.dumps(host)}) return {{__wo:location.host}};\n" + body
        # Same-origin fetch only needs an origin, not the current UI page. The
        # new Vue pages (mooc2-ans-vue) keep re-rendering, so BrowserSkill
        # rejects an evaluate there (document_changed / observation_changed).
        # Always run from the host's static base page, whose document is stable.
        if self.b.url != BASE_PAGE[host]:
            # A static JS/CSS file has no UI to become ready; the observation
            # readiness check only adds failure modes here (e.g. an unresponsive frame).
            self.b.navigate(BASE_PAGE[host], settle=0.2, readiness=False)
        for _ in range(2):
            r = self.b.eval(js, retry_safe=retry_safe, timeout=timeout)
            if isinstance(r, dict) and "__wo" in r:
                self.b.navigate(BASE_PAGE[host], settle=0.2, readiness=False)
                continue
            return r
        raise XxtError(f"无法切换到 {host}")

    def here(self, body: str, *, retry_safe: bool = True) -> Any:
        return self.b.eval(JS_PRELUDE + body, retry_safe=retry_safe)

    def wait_for(self, js_cond: str, timeout: float = 15, interval: float = 1.0) -> Any:
        """Poll until JS body returns a truthy value.

        Only a page-script exception (element/global not there yet) means "keep
        waiting". Every BrowserSkill error -- timeout, control not ready, denied,
        stale receipt -- propagates at once: polling past it would issue further
        browser commands after the controller reported a problem.
        """
        t0 = time.time()
        last = None
        while time.time() - t0 < timeout:
            try:
                last = self.here(js_cond)
                if last:
                    return last
            except JsError:
                pass
            time.sleep(interval)
        return last

    # ================================================================ courses
    def courses(self, refresh: bool = False) -> list[Course]:
        if self._courses and not refresh and time.time() - self._courses_time < self.cfg.course_list_ttl:
            return self._courses
        self.b.navigate("https://mooc2-ans.chaoxing.com/mooc2-ans/visit/interaction?moocDomain=https://mooc1-1.chaoxing.com/mooc-ans", settle=0.5)
        data = self.wait_for("""
            const cs=[...document.querySelectorAll('div.course[id^=c_]')];
            if(!cs.length) return null;
            return cs.map(e=>({id:e.querySelector('.courseId')?.value,cpi:e.querySelector('.curPersonId')?.value,
              role:e.querySelector('.role')?.value,
              name:((e.querySelector('.course-name')||e.querySelector('.course-info h3')||{}).innerText||'').replace(/置顶/g,'').trim().split('\\n')[0].trim(),
              info:T(e.querySelector('.course-info'))}));
        """, timeout=20)
        if not data:
            u = self.b.href() or ""
            if "passport" in u or "login" in u:
                raise NeedsHuman("学习通未登录：请在浏览器里手动登录学习通（需要人工完成验证码/扫码）。")
            raise XxtError("课程列表为空或页面未加载")
        prev = {c.id: c for c in self._courses}
        out = []
        for d in data:
            if not d.get("id"):
                continue
            c = prev.get(str(d["id"])) or Course(id=str(d["id"]), name="", cpi="")
            c.name = d["name"] or c.name
            c.cpi = str(d.get("cpi") or self.cfg.cpi or c.cpi)
            c.role = str(d.get("role") or "1")
            c.info = d.get("info") or ""
            out.append(c)
        self._courses = out
        self._courses_time = time.time()
        return self._courses

    def course(self, q: str | int) -> Course:
        q = str(q).strip()
        cs = self.courses()
        items = [{"id": c.id, "title": c.name, "role": c.role, "_c": c} for c in cs]
        try:
            it = _best(items, q)
        except XxtError:
            mine = [i for i in items if i["title"] == q and i["role"] == "1"]
            if len(mine) == 1:   # duplicates differ by role: prefer the course I own
                it = mine[0]
            else:
                dup = [i for i in items if i["title"] == q] or [i for i in items if q.lower() in i["title"].lower()]
                if len(dup) > 1:
                    lst = "; ".join(f"{i['id']}（{i['_c'].info[:40]}）" for i in dup[:12])
                    raise XxtError(f"「{q}」对应 {len(dup)} 门课程，请用课程ID指定：{lst}")
                raise
        return it["_c"]

    def ctx(self, q: str | int, refresh: bool = False) -> Course:
        """Course context: clazzId, enc, t (signed params), class list. Cached."""
        c = self.course(q)
        if c.enc and not refresh and time.time() - c.ctx_time < self.cfg.course_ctx_ttl:
            return c
        # A refresh must not leave the old context usable if navigation or a
        # subsequent class lookup fails or is denied.
        c.classes = []
        c.enc = ""
        c.ctx_time = 0.0
        url = self.b.navigate(f"https://mooc1.chaoxing.com/course/isNewCourse?courseId={c.id}&cpi={c.cpi}&v=6&edit=true", settle=0.3)
        if "clazzId=" not in url:
            url = self.b.href()
        qs = dict(up.parse_qsl(up.urlparse(url).query))
        c.clazz_id = qs.get("clazzId") or qs.get("clazzid") or ""
        c.enc = qs.get("enc", "")
        c.t = qs.get("t", "")
        c.cpi = qs.get("cpi", c.cpi)
        if not c.clazz_id:
            raise XxtError(f"无法打开课程 {c.name}（{url}）")
        try:
            cls = self.on(M2, f"""
                const d=D(await F('/mooc2-ans/tcm/clazz-manage?courseid={c.id}&clazzid={c.clazz_id}&v=0&cpi={c.cpi}'));
                return [...d.querySelectorAll('li.changeclazzlistli[data]')].map(l=>({{clazz_id:l.getAttribute('data'),name:T(l.querySelector('p'))||T(l)}}));
            """)
            # Observed: right after a class is deleted the list can come back empty
            # once. Never guess a single default class: publish/sign-in targets are
            # resolved from this list.
            if not cls or any(not x.get("clazz_id") for x in cls):
                c.enc = ""
                c.ctx_time = 0.0
                raise XxtError("班级列表读取为空或不完整；请稍后重试 open_course。")
            c.classes = cls
        except BskError:
            # Any browser error (denied, timeout, control not ready): do not
            # fall back to a guessed single-class list -- publish targets are
            # resolved from it. Leave no partially refreshed context usable.
            c.classes = []
            c.enc = ""
            c.ctx_time = 0.0
            raise
        except JsError:
            c.classes = []
            c.enc = ""
            c.ctx_time = 0.0
            raise XxtError("班级列表页面脚本出错；没有使用猜测的班级。")
        c.ctx_time = time.time()
        return c

    def q(self, c: Course, clazz: bool = True, enc: bool = True) -> str:
        s = f"courseid={c.id}&cpi={c.cpi}&ut=t"
        if clazz:
            s += f"&clazzid={c.clazz_id}"
        if enc:
            s += f"&enc={c.enc}&t={c.t}"
        return s

    def resolve_class(self, c: Course, cls: str | None) -> str:
        if not cls:
            return c.clazz_id
        it = _best([{"id": x["clazz_id"], "title": x["name"]} for x in c.classes], cls)
        return it["id"]

    def _select_classes_js(self, c: Course, classes: list[str] | None) -> str:
        if not classes:
            raise XxtError("未指定发放班级，拒绝默认选择全部班级。")
        ids = [self.resolve_class(c, x) for x in classes]
        return f"""
            document.getElementById('choosepublish').click();
            await new Promise(r=>setTimeout(r,600));
            const want={json.dumps(ids)};
            if(!want.length || new Set(want).size!==want.length) throw Error('班级选择无效');
            const rows=[...document.querySelectorAll('a.classData[data], a.classitem[data]')].map(a=>({{
              id:a.getAttribute('data'), ck:a.parentElement?.querySelector('.class_check')
            }}));
            if(!rows.length || rows.some(r=>!r.id || !r.ck) || new Set(rows.map(r=>r.id)).size!==rows.length ||
                want.some(id=>!rows.some(r=>r.id===id))) throw Error('班级列表不完整或不唯一，停止发放');
            const state=ck=>{{
              const signals=[];
              const native=ck.matches('input[type="checkbox"]')?ck:ck.querySelector('input[type="checkbox"]');
              if(native) signals.push(Boolean(native.checked));
              const aria=ck.getAttribute('aria-checked');
              if(aria==='true'||aria==='false') signals.push(aria==='true');
              if(ck.classList.contains('checked')) signals.push(true);
              if(ck.classList.contains('unchecked')) signals.push(false);
              if(signals.length<2 || signals.some(x=>x!==signals[0])) throw Error('班级勾选状态证据不足或互相矛盾，停止发放');
              return signals[0];
            }};
            // Inspect every control before any click; do not guess from substring /checked/.
            const prior=rows.map(r=>state(r.ck));
            rows.forEach((r,i)=>{{if(prior[i]!==want.includes(r.id)) r.ck.click();}});
            if(rows.some(r=>state(r.ck)!==want.includes(r.id))) throw Error('实际勾选班级与预演不一致，停止发放');
            const confirm=document.getElementById('confirmchoose');
            if(!confirm) throw Error('找不到班级选择确认控件');
            confirm.click();
        """


def make_client(cfg: Config):
    """Compose the full client (mixins live in ops_*.py to keep files small)."""
    from .ops_activity import ActivityOps
    from .ops_content import ContentOps
    from .ops_course import CourseOps
    from .ops_notice import NoticeOps
    from .ops_v3 import V3Ops
    from .ops_write import WriteOps
    from .ops_create import CreateOps
    from .ops_upload import UploadOps
    from .ops_task import TaskOps
    from .ops_student import StudentOps
    from .ops_review import ReviewOps
    from .ops_active import ActiveOps
    from .ops_class import ClassOps
    from .ops_stu_active import StudentActiveOps
    from .ops_settings import SettingsOps
    from .ops_manage import ManageOps
    from .ops_classadmin import ClassAdminOps
    from .ops_bank import BankOps
    from .ops_reads import ReadOps
    from .ops_stu_more import StudentMoreOps
    from .ops_paper import PaperOps
    from .ops_import import ImportOps
    from .ops_chapter2 import ChapterInsertOps

    class Xxt(NoticeOps, CreateOps, UploadOps, TaskOps, StudentOps, StudentActiveOps, StudentMoreOps, ReviewOps, ActiveOps, ClassOps, ClassAdminOps, BankOps, ReadOps, SettingsOps, ManageOps, PaperOps, ImportOps, ChapterInsertOps,
              WriteOps, V3Ops,
              ContentOps,
              CourseOps,
              ActivityOps):
        pass
    return Xxt(cfg)
