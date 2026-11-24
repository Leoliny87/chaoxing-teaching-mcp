"""Author an existing teaching model linked by the verified course portal."""

import copy
import json
import math
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .ops_exhibit import fingerprint, one
from .ops_portal_authoring import public_portal
from .xxt import XxtError

HOST = "vrmodel.sslibweb.com"
OBJECT = re.compile(r"[0-9a-f]{32}")


class ModelLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.models = set()

    def handle_starttag(self, tag, attrs):
        kind = {"a": "href", "iframe": "src"}.get(tag)
        if not kind:
            return
        url = urlsplit(dict(attrs).get(kind) or "")
        model = re.fullmatch(r"/preview/([1-9][0-9]*)/?", url.path)
        if url.scheme == "https" and url.netloc == HOST and model:
            self.models.add(model[1])


READ_MODEL = """
const res=performance.getEntriesByType('resource').find(e=>{
 const u=new URL(e.name); return u.origin===location.origin&&u.pathname==='/api/model-editor/config/get'});
if(!res)throw Error('模型数据未加载');
const read=async()=>{const doc=await J(res.name,{cache:'no-store'});const r=doc.result;
 if(!doc.success||!r||String(r.id)!==model)throw Error('模型标识不匹配');
 return {id:r.id,modelFileId:r.modelFileId,previewId:r.previewId,configJSON:r.configJSON};};
"""


def open_model(cl, c, portal_url, article_id, model_id):
    links = ModelLinks()
    links.feed(one(public_portal(cl, c, portal_url), article_id)["content"])
    if model_id not in links.models:
        raise XxtError("指定模型未挂在这个课程栏目。")
    cl.b.navigate(f"https://{HOST}/edit/{model_id}", readiness=False)
    if not cl.wait_for(
        "return location.host==='vrmodel.sslibweb.com'&&location.pathname==="
        + json.dumps("/edit/" + model_id)
        + "&&performance.getEntriesByType('resource').some(e=>new URL(e.name).pathname==='/api/model-editor/config/get')"
    ):
        raise XxtError("模型编辑器未载入。")
    return "const model=" + json.dumps(model_id) + ";" + READ_MODEL


def text_field(value, limit):
    if (
        not isinstance(value, str)
        or len(value) > limit
        or re.search(r"[<>\x00]", value)
    ):
        raise XxtError("模型文字超长或含有标记。")


def vector(value):
    return (
        isinstance(value, dict)
        and set(value) == {"x", "y", "z"}
        and all(
            type(n) in (float, int) and math.isfinite(n) and abs(n) <= 1e7
            for n in value.values()
        )
    )


def validate_anchor(value):
    if not isinstance(value, dict) or set(value) != {
        "position",
        "viewDirection",
        "cameraPosition",
        "meshName",
        "vertexBinding",
    }:
        raise XxtError("热点需要位置、相机、观察方向和网格定位信息。")
    binding = value["vertexBinding"]
    if (
        not all(
            vector(value[k]) for k in ("position", "viewDirection", "cameraPosition")
        )
        or not isinstance(value["meshName"], str)
        or not re.fullmatch(r"[\w. -]{1,128}", value["meshName"])
        or not isinstance(binding, dict)
        or set(binding) != {"indices", "barycentric"}
        or not isinstance(binding["indices"], list)
        or len(binding["indices"]) != 3
        or any(type(i) is not int or i < 0 for i in binding["indices"])
        or not vector(binding["barycentric"])
        or min(binding["barycentric"].values()) < -0.0001
        or abs(sum(binding["barycentric"].values()) - 1) > 0.001
    ):
        raise XxtError("热点的三角网格或相机参数无效。")


def change_model(row, settings, hotspots):
    wanted = copy.deepcopy(row)
    cfg = json.loads(row["configJSON"])
    if (
        not isinstance(settings, dict)
        or not isinstance(hotspots, list)
        or len(hotspots) > 100
        or not (settings or hotspots)
    ):
        raise XxtError("提供模型设置或最多 100 个热点变更。")
    for key, v in settings.items():
        if key in ("modelFileId", "previewId"):
            if not isinstance(v, str) or not OBJECT.fullmatch(v):
                raise XxtError("模型或封面需要平台文件 ID。")
            wanted[key] = v
        elif key in ("name", "description"):
            text_field(v, 4000 if key == "description" else 200)
            cfg["modelSettings"][key] = v
        elif key in ("scale", "rotateSpeed"):
            if type(v) not in (int, float) or not 0 < v <= 100:
                raise XxtError("缩放或旋转速度无效。")
            cfg["modelSettings"][key] = v
        elif key in ("autoRotate", "hotspotAutoSwitch", "hotspotModalVisible"):
            if type(v) is not bool:
                raise XxtError("需要布尔值。")
            cfg["modelSettings" if key == "autoRotate" else "hotSetting"][key] = v
        elif key == "hotspotSwitchFrequency" and type(v) is int and 1 <= v <= 10:
            cfg["hotSetting"][key] = v
        else:
            raise XxtError("未知模型设置或无效值。")
    points = cfg["hotSetting"]["hotspots"]
    seen = set()
    for patch in hotspots:
        if (
            not isinstance(patch, dict)
            or type(patch.get("id")) is not int
            or patch["id"] < 1
            or patch["id"] in seen
        ):
            raise XxtError("每个热点需要唯一数字 ID。")
        seen.add(patch["id"])
        matches = [r for r in points if r["id"] == patch["id"]]
        if len(matches) > 1:
            raise XxtError("原有热点 ID 重复。")
        if matches:
            point = matches[0]
        else:
            if not all(k in patch for k in ("name", "description", "hotInfo")):
                raise XxtError("新增热点需要名称、描述和锚点。")
            point = {
                "id": patch["id"],
                "module": "default",
                "visible": True,
                "audio": None,
                "imageVideo": "",
                "url": "",
                "type": "image",
                "linkTitle": "",
                "linkUrl": "",
            }
            points.append(point)
        for k, v in patch.items():
            if k == "id":
                continue
            if k in ("name", "description", "linkTitle", "audioName"):
                text_field(v, 4000 if k == "description" else 200)
            elif k == "hotInfo":
                validate_anchor(v)
            elif k == "visible" and type(v) is bool:
                pass
            elif (
                k in ("imageVideo", "audio")
                and isinstance(v, str)
                and OBJECT.fullmatch(v)
            ):
                pass
            elif k == "type" and v in ("image", "video"):
                pass
            elif k in ("url", "linkUrl"):
                u = urlsplit(v)
                if (
                    u.scheme != "https"
                    or not u.hostname
                    or u.netloc != u.hostname
                    or not (
                        u.hostname.endswith((".chaoxing.com", ".cldisk.com"))
                        or u.hostname == HOST
                    )
                ):
                    raise XxtError("热点链接须为平台 HTTPS 资源。")
            else:
                raise XxtError("未知热点字段或无效值。")
            point[k] = v
        if "imageVideo" in patch and patch["imageVideo"] and "url" not in patch:
            raise XxtError("更改热点图片时请同时提供对应的学生端资源 URL。")
    if cfg != json.loads(row["configJSON"]):
        wanted["configJSON"] = json.dumps(
            cfg, ensure_ascii=False, separators=(",", ":")
        )
    return wanted


def register_models(tool, client, check_write, dry):
    @tool("read", "读取课程门户链接的三维教学模型、热点、相机设置、封面和文件 ID。")
    def get_teaching_model(
        course: str, portal_url: str, article_id: str, model_id: str
    ):
        cl = client()
        script = open_model(cl, cl.course(course), portal_url, article_id, model_id)
        row = cl.here(script + "return await read();")
        cfg = json.loads(row["configJSON"])
        return {
            "model_id": model_id,
            "file": row["modelFileId"],
            "cover": row["previewId"],
            "settings": cfg["modelSettings"],
            "tour": cfg["hotSetting"],
            "revision": fingerprint(row),
        }

    @tool(
        "write",
        "更新已有三维教学模型的 GLB、封面、演示设置或按 ID 新增和修改热点，保留其余场景配置。",
    )
    def edit_teaching_model(
        course: str,
        portal_url: str,
        article_id: str,
        model_id: str,
        revision: str,
        settings: dict,
        hotspots: list[dict],
        confirm: bool = False,
    ):
        cl, c = client(), check_write(course)
        script = open_model(cl, c, portal_url, article_id, model_id)
        row = cl.here(script + "return await read();")
        if fingerprint(row) != revision:
            raise XxtError("模型已变化。")
        wanted = change_model(row, settings, hotspots)
        if not confirm:
            return dry(
                c,
                "修改三维教学模型",
                model=model_id,
                settings=list(settings),
                hotspot_ids=[p["id"] for p in hotspots],
            )
        if row != wanted:
            cl.here(
                script
                + "const before="
                + json.dumps(row)
                + "; const after="
                + json.dumps(wanted)
                + """;
               const current=await read();if(Object.keys(before).some(k=>current[k]!==before[k]))throw Error('模型已变化');
               const r=await fetch('/api/model-editor/config',{method:'PUT',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(after)});
               if(!r.ok||!(await r.json()).success)throw Error('模型保存失败');return true;""",
                retry_safe=False,
            )
        back = cl.here(script + "return await read();")
        return {
            "ok": back == wanted,
            "revision": fingerprint(back),
            "hotspots": len(json.loads(back["configJSON"])["hotSetting"]["hotspots"]),
        }
