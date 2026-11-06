"""Chapters, materials (资料), grades/export, downloads."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path

from .xxt import BASE_PAGE, M1, M2, STAT, XxtBase, XxtError, _best


class CourseOps(XxtBase):
    # ================================================================ chapters
    def chapters(self, course: str) -> list[dict]:
        c = self.course(course)
        j = self.on(M1, f"return await J('/mooc-ans/edit/get-knowledge-list?courseId={c.id}&cpi={c.cpi}');")
        if (not isinstance(j, dict) or not isinstance(j.get("data"), list)
                or j.get("success") is False or j.get("result") is False):
            raise XxtError("章节列表返回无效或服务端报错；不能视为空列表，请稍后核查。")
        out: list[dict] = []
        seen: set[str] = set()

        def walk(nodes, prefix, parent):
            if nodes is None:
                return
            if not isinstance(nodes, list):
                raise XxtError("章节树子节点格式异常；未返回不完整列表。")
            for i, n in enumerate(nodes, 1):
                if (not isinstance(n, dict) or n.get("id") is None
                        or isinstance(n.get("id"), bool) or not str(n.get("id")).strip()
                        or not isinstance(n.get("title"), str) or not n["title"].strip()):
                    raise XxtError("章节树节点缺少有效 ID 或标题；未返回不完整列表。")
                chapter_id = str(n["id"])
                if chapter_id in seen:
                    raise XxtError("章节树中存在重复 ID；未返回不完整列表。")
                seen.add(chapter_id)
                num = f"{prefix}{i}"
                out.append({"chapter_id": chapter_id, "number": num, "title": n.get("title"), "layer": n.get("layer"), "parent_id": parent})
                walk(n.get("children"), num + ".", chapter_id)
        walk(j["data"], "", "0")
        return out

    def create_chapter(self, course: str, title: str, parent: str = "") -> dict:
        c = self.course(course)
        chs = self.chapters(c.id)
        if parent:
            p = _best(chs, parent, id_keys=("chapter_id", "number"))
            pid, layer = p["chapter_id"], int(p["layer"]) + 1
        else:
            p, pid, layer = None, "0", 1
        if layer > 7:
            raise XxtError("章节不能超过7层")
        r = self.on(M1, f"""
            const f=new FormData(); f.append('courseid','{c.id}'); f.append('name',{json.dumps(title)}); f.append('parentid','{pid}'); f.append('layer','{layer}'); f.append('mooc2','1');
            return await J('/mooc-ans/edit/createchapter',{{method:'POST',body:f}});""", retry_safe=False)
        nid = str((r or {}).get("id", ""))
        hit = [x for x in self.chapters(c.id) if x["chapter_id"] == nid]
        return {"ok": bool(hit), "chapter": hit[0] if hit else None, "parent": p["title"] if p else "(顶层)", "server": r}

    def delete_chapter(self, course: str, chapter: str) -> dict:
        c = self.course(course)
        chs = self.chapters(c.id)
        ch = _best(chs, chapter, id_keys=("chapter_id", "number"))
        kids = [x for x in chs if x["number"].startswith(ch["number"] + ".")]
        r = self.on(M1, f"const f=new FormData(); f.append('courseid','{c.id}'); f.append('nodeid','{ch['chapter_id']}'); return await J('/mooc-ans/edit/deletechapter',{{method:'POST',body:f}});", retry_safe=False)
        ok = not [x for x in self.chapters(c.id) if x["chapter_id"] == ch["chapter_id"]]
        return {"ok": ok, "deleted": f"{ch['number']} {ch['title']}", "also_deleted_children": len(kids), "server": r}

    def find_chapter(self, course: str, chapter: str) -> dict:
        c = self.course(course)
        chs = self.chapters(c.id)
        ch = _best(chs, chapter, id_keys=("chapter_id", "number"))
        return {**ch, "children": [x for x in chs if x["number"].startswith(ch["number"] + ".")]}

    # ================================================================ materials
    def materials(self, course: str) -> list[dict]:
        c = self.ctx(course)
        return self.on(M2, f"""
            const d=D(await F('/mooc2-ans/coursedata?{self.q(c)}&v=6'));
            return [...d.querySelectorAll('ul.dataBody_td[id]')].map(u=>{{const li=[...u.querySelectorAll(':scope>li')].map(T).filter(x=>x&&x.length<40);
              return {{material_id:u.id,title:u.getAttribute('dataname'),type:u.getAttribute('type'),info:li.slice(-4)}}}});
        """)

    def upload_material(self, course: str, file_path: str) -> dict:
        c = self.ctx(course)
        src = Path(file_path).expanduser()
        if not src.is_file():
            raise XxtError(f"文件不存在: {src}")
        bad = set('`~!@#$%^&*+<>?:"{},\\;[]/')
        name = "".join("-" if ch in bad else ch for ch in src.name)
        up_path = src
        if name != src.name:
            up_path = Path(tempfile.mkdtemp()) / name
            shutil.copy(src, up_path)
        before = {m["material_id"] for m in self.materials(c.id)}
        self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/coursedata?{self.q(c)}&v=6", settle=1.0)
        self.b.click_selector("a.popLocalBnt", settle=1.5)
        self.b.upload_label(r'link "选择本地文件"', [str(up_path)])
        for _ in range(max(5, int(self.cfg.t_upload // 3))):
            time.sleep(3)
            new = [m for m in self.materials(c.id) if m["material_id"] not in before]
            if new:
                return {"ok": True, "material": new[0], "renamed_to": name if name != src.name else None}
        raise XxtError("上传后没有在资料列表中看到新文件，请人工检查")

    def delete_material(self, course: str, material: str) -> dict:
        c = self.ctx(course)
        m = _best(self.materials(c.id), material, id_keys=("material_id",))
        r = self.on(M2, f"return await J('/mooc2-ans/coursedata/batchDelete?dataId={m['material_id']}&courseId={c.id}',{{method:'POST'}});", retry_safe=False)
        ok = not [x for x in self.materials(c.id) if x["material_id"] == m["material_id"]]
        return {"ok": ok, "deleted": m["title"], "server": r}

    # ================================================================ grades
    _COLS = [("video", "章节任务点"), ("ceyan", "章节测验"), ("work", "作业"), ("test", "考试"), ("aiEvaluate", "AI实践"),
             ("pbl", "分组任务(PBL)"), ("attend", "签到"), ("active", "课程积分"), ("bbs", "讨论")]

    def grades(self, course: str, cls: str = "") -> dict:
        c = self.ctx(course)
        clz = self.resolve_class(c, cls)
        r = self.on(STAT, f"""
            const base='clazzid={clz}&courseid={c.id}&cpi={c.cpi}&ut=t&pEnc=';
            const init=await J('/stat2/score-data/initTable?'+base);
            if(!init||init.status===false||!init.weight||typeof init.weight!=='object'||Array.isArray(init.weight)) return {{valid:false}};
            const rows=[]; let p=1, total=null;
            while(true){{
              const j=await J('/stat2/score-data/scoreList?'+base+'&pageNo='+p+'&sw=&order=loginName&sortType=0&groupId=-1&planId=-1&withoutWeight=0');
              const rawTotal=j?.pageInfo?.totalPage;
              if(!j||j.status===false||!Array.isArray(j.data)||rawTotal===null||rawTotal===undefined||
                 !/^\\d+$/.test(String(rawTotal))) return {{valid:false}};
              const pages=Number(rawTotal);
              if(!Number.isSafeInteger(pages)||pages>50||(pages===0&&j.data.length)||
                 (total!==null&&total!==pages)) return {{valid:false}};
              total=pages; rows.push(...j.data);
              if(p>=Math.max(total,1)) break;
              p++;
            }}
            return {{valid:true,weight:init.weight,rows}};
        """)
        if (not isinstance(r, dict) or r.get("valid") is not True or not isinstance(r.get("weight"), dict)
                or not isinstance(r.get("rows"), list) or any(not isinstance(x, dict) for x in r["rows"])):
            raise XxtError("成绩读取结果格式异常；未将其视为无成绩。")
        w = r["weight"]
        # A numerical zero is an explicit weight, not a missing field.
        present = lambda key: key in w and w[key] is not None
        weights = {zh: w[k] for k, zh in self._COLS if present(k)}
        students = []
        for x in r.get("rows", []):
            s = {"name": x.get("userName"), "student_no": x.get("loginName"), "person_id": x.get("personId"), "综合成绩": x.get("score")}
            for k, zh in self._COLS:
                if present(k):
                    s[zh] = x.get(k)
            students.append(s)
        return {"course": c.name, "clazz_id": clz, "weights_percent": weights, "count": len(students), "students": students}

    def export_grades(self, course: str, cls: str = "", out_dir: str = "") -> dict:
        c = self.ctx(course)
        clz = self.resolve_class(c, cls)
        t0 = time.time() * 1000 - 5000
        r = self.on(STAT, f"return await J('/stat2/teach-data/export?clazzid={clz}&courseid={c.id}&cpi={c.cpi}&ut=t&pEnc=&seltables=6&type=1&exportType=0&fr=stat2');", retry_safe=False)
        item = None
        for _ in range(40):
            time.sleep(3)
            lst = self.on(M2, f"const j=await J('/mooc2-ans/tcm/downloadcenter?courseId={c.id}&cpi={c.cpi}&pageNum=1&pageSize=20&view=json&order=down'); return (j.data||{{}}).list||[];")
            fresh = [x for x in (lst or []) if (x.get("createTime") or 0) >= t0 and x.get("type") == "score"]
            if fresh and fresh[0].get("status") == 1 and fresh[0].get("downloadUrl"):
                item = fresh[0]
                break
        if not item:
            raise XxtError("导出任务已提交，但 2 分钟内下载中心没有生成文件；稍后可在 课程管理→下载中心 下载。")
        res = self.fetch_export(item["downloadUrl"], f"{c.name}-{item.get('fileName', '成绩')}.xlsx", out_dir)
        res.update({"job": {"id": item.get("id"), "name": item.get("fileName")}, "server": r})
        return res

    def fetch_export(self, url: str, filename: str, out_dir: str = "") -> dict:
        """Download a URL with the browser's cookies into out_dir (anchor + bsk download)."""
        d = Path(out_dir).expanduser() if out_dir else self.cfg.download_dir
        d.mkdir(parents=True, exist_ok=True)
        out = d / re.sub(r'[\\/:*?"<>|\s]+', "_", filename)
        self.b.navigate(BASE_PAGE[M2], settle=0.2)
        self.here(f"let a=document.getElementById('__xxt_dl'); if(!a){{a=document.createElement('a'); a.id='__xxt_dl'; a.textContent='download'; a.style.cssText='position:fixed;top:10px;left:10px;z-index:99999;font-size:24px;background:#fff;padding:8px'; document.body.appendChild(a);}} a.href={json.dumps(url)}; return true;")
        self.b.download_selector("#__xxt_dl", str(out))
        return {"ok": out.exists(), "path": str(out), "bytes": out.stat().st_size if out.exists() else 0}

    def download_center(self, course: str) -> list[dict]:
        c = self.course(course)
        lst = self.on(M2, f"const j=await J('/mooc2-ans/tcm/downloadcenter?courseId={c.id}&cpi={c.cpi}&pageNum=1&pageSize=20&view=json&order=down'); return (j.data||{{}}).list||[];")
        return [{"id": x.get("id"), "name": x.get("fileName"), "type": x.get("type"), "status": "完成" if x.get("status") == 1 else x.get("status"),
                 "created": time.strftime("%Y-%m-%d %H:%M", time.localtime((x.get("createTime") or 0) / 1000))} for x in lst or []]
