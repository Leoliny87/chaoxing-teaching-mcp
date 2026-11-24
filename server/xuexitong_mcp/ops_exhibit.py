"""Teacher authoring of the native virtual hall linked by a course portal."""

import base64
import hashlib
import json
import math
import re
from urllib.parse import parse_qs, urlsplit

from .xxt import M1, XxtError, _safe_id

VR = "vr.chaoxing.com"
TRANSFORM = tuple(
    axis + dim for axis in ("position", "rotate", "scale") for dim in "XYZ"
)
MEDIA = ("imgFileId", "audioFileId", "videoFileId")
LAYOUT = {
    "fontSize": "size",
    "textWidth": "width",
    "textAlign": "align",
    "webScreenshot": "webScreenshot",
    "ktxFileId": "ktxFileId",
}
ANCHORS = ("hotspotPos", "hotspotRot")
PROPS = (
    set(LAYOUT)
    | set(ANCHORS)
    | set(TRANSFORM)
    | set(MEDIA)
    | {"text", "audioName", "name", "title", "webScreenshot"}
)
SCENE_FIELDS = {"name", "title", "cover", "navOrder", "sceneOrder", "duration"}


def portal_editor(cl, c):
    cid = _safe_id(c.id)
    cl.b.navigate(
        f"https://{M1}/course-ans/courseportal/edithomeprotal?courseId={cid}&customTemplate=true"
    )
    if not cl.wait_for(
        "return location.host==='mooc1.chaoxing.com' && document.querySelector('#courseId')?.value==="
        + json.dumps(cid)
    ):
        raise XxtError("课程门户编辑器与目标课程不符。")


def hall_id(url):
    u = urlsplit(url)
    route, _, qs = u.fragment.partition("?")
    ids = parse_qs(qs).get("id", [])
    if (
        u.scheme != "https"
        or u.netloc != VR
        or u.path not in ("", "/")
        or route != "/showEditSpace"
        or len(ids) != 1
    ):
        raise XxtError("门户没有提供有效的原生展厅编辑入口。")
    try:
        identifier = base64.b64decode(ids[0], validate=True).decode("ascii")
        if not re.fullmatch(r"[1-9][0-9]*", identifier):
            raise ValueError("invalid identifier")
        return identifier
    except (ValueError, UnicodeError):
        raise XxtError("展厅标识无效。") from None


def open_hall(cl, c, public=False):
    portal_editor(cl, c)
    cl.here("if(typeof showVirtualDiv==='function')showVirtualDiv();return true")
    url = cl.wait_for(
        "return document.querySelector('#visualShowRoomEditUrl')?.value || false"
    )
    if not url:
        raise XxtError("这门课程没有展厅编辑入口。")
    hid = hall_id(url)
    if public:
        key = base64.b64encode(hid.encode()).decode()
        url = f"https://{VR}/#/showCustomerSpace?id={key}"
    cl.b.navigate(url, readiness=False)
    if not cl.wait_for(
        """return location.host==='vr.chaoxing.com' && ['/api/hall/prop/detailList','/api/hall/scene/list'].every(p=>performance.getEntriesByType('resource').some(r=>new URL(r.name).pathname===p))"""
    ):
        raise XxtError("展厅资源尚未加载。")
    return hid


READ = """
const resources=performance.getEntriesByType('resource');
const read=async path=>{
    const ref=resources.find(item=>{const u=new URL(item.name);return u.origin===location.origin && u.pathname===path && u.searchParams.get('hallId')===hid});
    if(!ref)throw Error('本展厅数据入口不可用');
    const data=await J(ref.name,{cache:'no-store'});
    if(!Array.isArray(data.result)||data.result.some(row=>String(row.hallId)!==hid))throw Error('展厅资源归属不一致');
    return data.result;
};
const props=await read('/api/hall/prop/detailList'),scenes=await read('/api/hall/scene/list');
"""


def valid_patch(kind, fields):
    allowed = SCENE_FIELDS if kind == "station" else PROPS
    if kind not in ("station", "prop") or not fields or set(fields) - allowed:
        raise XxtError("展厅对象或修改字段不受支持。")
    for key, value in fields.items():
        if key in ANCHORS:
            if (
                not isinstance(value, dict)
                or set(value) != {"x", "y", "z"}
                or any(
                    type(v) not in (int, float)
                    or not math.isfinite(v)
                    or abs(v) > 10000
                    for v in value.values()
                )
            ):
                raise XxtError("热点坐标须提供有限的 x、y、z。")
        elif key in ("fontSize", "textWidth"):
            if type(value) is not int or not 1 <= value <= 4096:
                raise XxtError("文字字号或宽度无效。")
        elif key == "textAlign":
            if value not in ("left", "center", "right"):
                raise XxtError("文字对齐方式无效。")
        elif key == "ktxFileId":
            if value != "":
                raise XxtError("纹理缓存只支持清空。")
        elif key in (*MEDIA, "cover", "webScreenshot"):
            if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
                raise XxtError("媒体需指定超星文件对象 ID。")
        elif key in TRANSFORM:
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or abs(value) > 10000
                or (key.startswith("scale") and value <= 0)
            ):
                raise XxtError("展板坐标、朝向或缩放无效。")
        elif key in ("navOrder", "sceneOrder", "duration"):
            if type(value) is not int or not 0 <= value <= 86400:
                raise XxtError("站点次序或时长无效。")
        elif (
            not isinstance(value, str)
            or len(value) > (10000 if key == "text" else 250)
            or re.search("[<>\x00]", value)
        ):
            raise XxtError("展板文字应是纯文本。")


def fingerprint(row):
    return hashlib.sha256(
        json.dumps(
            row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def summarise(row, kind):
    if kind == "station":
        fields = {k: row.get(k) for k in SCENE_FIELDS}
    else:
        a = row.get("hallPropAttr") or {}
        fields = {k: row.get(k) for k in TRANSFORM}
        fields.update({k: a.get(k) for k in (*MEDIA, "title", "name", "audioName")})
        cfg = json.loads(a.get("textCfg") or "{}")
        fields.update(text=a.get("content"))
        fields.update({k: cfg.get(v) for k, v in LAYOUT.items()})
        for k in ("textWidth", "fontSize"):
            if str(fields[k]).isdigit():
                fields[k] = int(fields[k])
        for k in ANCHORS:
            if a.get(k):
                fields[k] = {
                    axis: float(value) for axis, value in json.loads(a[k]).items()
                }
    return {"id": str(row["id"]), "revision": fingerprint(row), "fields": fields}


def state(cl, hid):
    return cl.here(
        "const hid=" + json.dumps(hid) + ";" + READ + "return {props,scenes}"
    )


def one(rows, object_id):
    matches = [r for r in rows if str(r["id"]) == str(object_id)]
    if len(matches) != 1:
        raise XxtError("对象不属于本展厅或标识不唯一。")
    return matches[0]


def apply_fields(row, kind, patch):
    if kind == "station":
        row.update(patch)
        return
    attr = row["hallPropAttr"]
    cfg = json.loads(attr.get("textCfg") or "{}")
    for key, value in patch.items():
        if key in TRANSFORM:
            row[key] = value
        elif key == "text":
            if row["propType"] not in (3, 4) or (
                "htmlContent" in cfg and cfg["htmlContent"] != attr.get("content")
            ):
                raise XxtError("仅可直接替换纯文本展板，富文本请使用展厅编辑器。")
            attr["content"] = value
            if "htmlContent" in cfg:
                cfg["htmlContent"] = value
        elif key in LAYOUT:
            cfg[LAYOUT[key]] = str(value) if key == "textWidth" else value
        elif key in ANCHORS:
            attr[key] = json.dumps(value, separators=(",", ":"))

        else:
            attr[key] = value
            if key == "imgFileId":
                cfg["ktxFileId"] = ""
    if cfg != json.loads(attr.get("textCfg") or "{}"):
        attr["textCfg"] = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))


def register_exhibit(tool, client, check_write, dry):
    @tool(
        "read",
        "读取本课虚拟展厅的原生展板、配图、配音、变换和导览站点，返回 ID 和修订摘要。",
    )
    def get_course_exhibit(
        course: str,
        kind: str = "prop",
        page: int = 1,
        size: int = 40,
        public: bool = True,
    ):
        if kind not in ("prop", "station") or not 1 <= size <= 100 or page < 1:
            raise XxtError("kind 需为 prop 或 station，页码从 1 开始，每页 1–100 项。")
        cl = client()
        hid = open_hall(cl, cl.course(course), public)
        rows = state(cl, hid)["scenes" if kind == "station" else "props"]
        return {
            "hall_id": hid,
            "total": len(rows),
            "items": [
                summarise(r, kind) for r in rows[(page - 1) * size : page * size]
            ],
        }

    @tool(
        "write",
        "按原生 ID 调整单个展板的文字、媒体、坐标、朝向、大小或导览站点。先读取修订摘要，保存后从参观端核对。",
    )
    def edit_course_exhibit_item(
        course: str,
        kind: str,
        object_id: str,
        revision: str,
        fields: dict,
        confirm: bool = False,
    ):
        valid_patch(kind, fields)
        c, cl = check_write(course), client()
        hid = open_hall(cl, c)
        key = "scenes" if kind == "station" else "props"
        orig = one(state(cl, hid)[key], _safe_id(object_id))
        if fingerprint(orig) != revision:
            raise XxtError("对象已变化，请重新读取。")
        row = json.loads(json.dumps(orig))
        apply_fields(row, kind, fields)
        if not confirm:
            return dry(
                c, "调整虚拟展厅对象", hall_id=hid, object_id=object_id, fields=fields
            )
        if row != orig:
            js = "const hid=%s,old=%s,next=%s;" % tuple(
                map(json.dumps, (hid, orig, row))
            )
            cl.here(
                js
                + READ
                + _SAVE_GUARD
                + ("const list=scenes;" if kind == "station" else "const list=props;")
                + "const stored=list.find(x=>String(x.id)===String(old.id));if(!same(stored,old))throw Error('对象已变化');"
                + (
                    "const result=await mod.saveSceneSelect([next]);"
                    if kind == "station"
                    else "const result=await mod.saveMaterials([next]);"
                )
                + _RECEIPT,
                retry_safe=False,
            )
        if open_hall(cl, c, public=True) != hid:
            raise XxtError("展厅入口已变更。")
        actual = one(state(cl, hid)[key], object_id)
        fields_now = summarise(actual, kind)["fields"]
        return {
            "ok": all(fields_now.get(k) == v for k, v in fields.items()),
            "object_id": object_id,
            "revision": fingerprint(actual),
        }

    @tool(
        "write",
        "在本课程指定展板下方增加独立配图，复用同展厅的样板、朝向和缩放，按展板局部坐标偏移，自动检查重复。",
    )
    def add_exhibit_panel_image(
        course: str,
        panel_id: str,
        sample_image_id: str,
        image_object_id: str,
        title: str,
        offset_x: float,
        offset_y: float,
        offset_z: float,
        confirm: bool = False,
        source_revision: str = "",
    ):
        c, cl = check_write(course), client()
        valid_patch(
            "prop",
            {
                "imgFileId": image_object_id,
                "title": title,
                "positionX": offset_x,
                "positionY": offset_y,
                "positionZ": offset_z,
            },
        )
        hid = open_hall(cl, c)
        rows = state(cl, hid)["props"]
        panel, sample = (one(rows, _safe_id(i)) for i in (panel_id, sample_image_id))
        if (
            panel["id"] == sample["id"]
            or not all(
                r.get("propType") == 2 and r.get("propId") == 23
                for r in (sample, panel)
            )
            or not sample["hallPropAttr"].get("imgFileId")
            or panel["rotateX"]
            or panel["rotateZ"]
        ):
            raise XxtError("请选择本展厅内的竖直展板及独立图片样板。")
        angle = panel["rotateY"]
        pos = [
            round(
                panel["positionX"]
                + offset_x * math.cos(angle)
                + offset_z * math.sin(angle),
                5,
            ),
            round(panel["positionY"] + offset_y, 5),
            round(
                panel["positionZ"]
                - offset_x * math.sin(angle)
                + offset_z * math.cos(angle),
                5,
            ),
        ]
        row = {
            k: sample[k]
            for k in (
                "propId",
                "propType",
                "scaleX",
                "scaleY",
                "scaleZ",
                "modelFaceCamera",
                "focus",
            )
        }
        row.update(zip(("positionX", "positionY", "positionZ"), pos))
        row.update(
            hallId=hid,
            rotateX=0,
            rotateY=angle,
            rotateZ=0,
            deleted=0,
            extraJson='{"extraType":"formImg"}',
            hallPropAttr={
                "hallId": 0,
                "hallPropId": 0,
                "imgFileId": image_object_id,
                "title": title,
                "name": title,
                "previewCtrl": 0,
                "textCfg": '{"collidabled":false,"ktxFileId":""}',
            },
        )
        if not confirm:
            return dry(
                c,
                "新增展厅配图",
                image=image_object_id,
                title=title,
                target=panel_id,
                sample=sample_image_id,
                position=pos,
                bind={"source_revision": fingerprint([panel, sample])},
            )
        if fingerprint([panel, sample]) != source_revision:
            raise XxtError("展板位置或样板已变化。")
        js = "const hid=%s,row=%s,panel=%s,sample=%s;" % tuple(
            map(json.dumps, (hid, row, panel, sample))
        )
        cl.here(
            js
            + READ
            + _SAVE_GUARD
            + """
          if(![panel,sample].every(r=>same(props.find(x=>x.id===r.id),r)))throw Error('展板已变');
          const atSite=props.filter(p=>['positionX','positionY','positionZ'].every(k=>Math.abs(p[k]-row[k])<0.015));
          if(atSite.length){if(atSite.length===1&&atSite[0].hallPropAttr?.imgFileId===row.hallPropAttr.imgFileId&&atSite[0].hallPropAttr.title===row.hallPropAttr.title)return true;throw Error('配图位置已占用');}
          row.frontEndId='f'+crypto.randomUUID();const result=await mod.saveMaterials([row]);
        """
            + _RECEIPT,
            retry_safe=False,
        )
        if open_hall(cl, c, public=True) != hid:
            raise XxtError("展厅入口已变更。")
        matches = [
            p
            for p in state(cl, hid)["props"]
            if p["hallPropAttr"].get("imgFileId") == image_object_id
            and p["hallPropAttr"].get("title") == title
            and all(abs(p[k] - row[k]) < 0.015 for k in TRANSFORM)
        ]
        return {
            "ok": len(matches) == 1,
            "created_or_present_id": str(matches[0]["id"])
            if len(matches) == 1
            else None,
        }


_SAVE_GUARD = r"""
const same=(a,b)=>{if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;
const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&same(a[k],b[k]));};
const entry=resources.find(x=>{const u=new URL(x.name);return u.origin===location.origin&&/^\/apiScene\.[\w-]+\.js$/.test(u.pathname)});
if(!entry)throw Error('未加载展厅编辑器');const mod=await import(entry.name);
"""
_RECEIPT = "if(![result,result?.data].some(r=>r?.success===true||r?.code===200))throw Error('展厅保存回执不明确');return true;"
