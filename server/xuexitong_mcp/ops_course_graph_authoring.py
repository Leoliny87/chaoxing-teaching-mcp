"""Course graph teaching cards, chapter links, and native chapter attachment associations."""

from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

from .ops_graph2 import para
from .ops_write import card_attachments
from .xxt import M1, XxtError


def digest(data):
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def numeric(value):
    value = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,63}", value):
        raise XxtError("需要有效的数字 ID。")
    return value


def check_editor(c, url):
    u = urlsplit(url)
    q = parse_qs(u.query, keep_blank_values=True)
    if (
        u.scheme != "https"
        or u.netloc != M1
        or u.fragment
        or not url.isascii()
        or not re.fullmatch(
            r"/edit/chapters/" + numeric(c.id) + r"/[1-9][0-9]*", u.path
        )
        or set(q)
        - {
            "classId",
            "newMooc",
            "mooc2",
            "microTopicId",
            "isMicroCourseEdit",
            "cpi",
            "openc",
        }
        or any(
            len(v) != 1 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", v[0])
            for v in q.values()
        )
        or q.get("cpi") != [str(c.cpi)]
        or not re.fullmatch(r"[1-9][0-9]*", q.get("microTopicId", [""])[0])
    ):
        raise XxtError("需要当前课程的知识点正文编辑器网址。")


def native_nodes(client, c, url, ids):
    check_editor(c, url)
    if not 1 <= len(ids) <= 40 or len(set(ids)) != len(ids):
        raise XxtError("每批需提供 1–40 个不同的知识点原生 ID。")
    # The editor server renders the full native point tree. Parse the response in
    # the signed-in browser without loading thousands of interactive frames.
    nodes = client.on(
        M1,
        "const doc=D(await F("
        + json.dumps(url)
        + ",{cache:'no-store'}));"
        + "if(doc.querySelector('#courseId')?.value!=="
        + json.dumps(str(c.id))
        + "||!doc.querySelector('[onclick^=linkMicroNode]'))throw Error('知识点编辑器与课程不匹配');"
        + "const ids="
        + json.dumps(ids)
        + r""";return ids.map(id=>{
      const el=doc.getElementById('cur'+id), a=el?.querySelector('[onclick]')?.getAttribute('onclick');
      const m=a?.match(/^linkMicroNode\('(\d+)',\s*'(\d+)'\);?$/);
      return m&&m[1]===id?{point_id:id,node_id:m[2],name:el.textContent.trim()}:null;
    });""",
    )
    if (
        not isinstance(nodes, list)
        or len(nodes) != len(ids)
        or any(
            not isinstance(n, dict) or n.get("point_id") != i or not n.get("name")
            for n, i in zip(nodes, ids)
        )
    ):
        raise XxtError("知识点不在本课程编辑器，或原生 ID 映射不一致。")
    for n in nodes:
        numeric(n["node_id"])
    if len({n["node_id"] for n in nodes}) != len(nodes):
        raise XxtError("多个知识点指向同一正文节点，请在课程中核对。")
    return nodes


def get_cards(client, c, node):
    q = urlencode(
        {
            "courseid": c.id,
            "cpi": c.cpi,
            "nodeid": node["node_id"],
            "microTopicId": node["point_id"],
            "cardid": 0,
        }
    )
    response = client._call(M1, "/mooc-ans/edit/getcard?" + q)
    cards = (response.get("json") or {}).get("data")
    if response.get("http") != 200 or not isinstance(cards, list) or not cards:
        raise XxtError("知识点卡片未读到。")
    for card in cards:
        if str(card.get("nodeid")) != node["node_id"] or not isinstance(
            card.get("description"), str
        ):
            raise XxtError("知识点卡片与节点不匹配。")
        numeric(card.get("id"))
    return cards


class Markup(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.words, self.links, self.modules = [], [], []
        self.source = body
        self.text_spans = []
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", body)]
        self.hidden = None
        self.feed(body)
        self.close()

    def handle_data(self, data):
        if self.hidden:
            return
        self.words.append(data)
        line, column = self.getpos()
        start = self.line_starts[line - 1] + column
        end = self.source.find("<", start)
        end = len(self.source) if end == -1 else end
        if html.unescape(self.source[start:end]) == data:
            self.text_spans.append((start, end))

    def handle_endtag(self, tag):
        if tag == self.hidden:
            self.hidden = None

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.hidden = tag
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if attrs.get("module") or tag == "img" and "mid" in attrs:
            self.modules.append(attrs)


def attachments(card):
    raw = card.get("attachments")
    if raw is not None and raw != "":
        try:
            raw = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError as exc:
            raise XxtError("卡片附件元数据无法解析。") from exc
        if not isinstance(raw, list) or any(not isinstance(a, dict) for a in raw):
            raise XxtError("卡片附件元数据格式不明。")
        if raw:
            return raw
    markup = Markup(card["description"])
    items = card_attachments(card["description"])
    if len(items) != len(markup.modules) or any(not item.get("mid") for item in items):
        raise XxtError("现有附件无法完整还原。")
    return items


def snapshot(cards):
    return digest(
        [
            [str(c["id"]), c.get("title"), c["description"], c.get("attachments")]
            for c in cards
        ]
    )


_PLACEHOLDERS = {"0", "1", "１", "暂无内容", "请输入正文", "待补充", "正文"}


def placeholder_free_html(source):
    markup = Markup(source)
    if "".join(markup.words).strip(" \t\r\n\u200b\ufeff\xa0") not in _PLACEHOLDERS:
        return source
    for start, end in reversed(markup.text_spans):
        source = source[:start] + source[end:]
    return source


def has_prose(card):
    text = "".join(Markup(card["description"]).words).strip(" \t\r\n\u200b\ufeff\xa0")
    return bool(text and text not in _PLACEHOLDERS)


def read_body_cards(client, c, url, ids):
    nodes = native_nodes(client, c, url, [numeric(i) for i in ids])
    return [(node, get_cards(client, c, node)) for node in nodes]


def body_summary(node, cards):
    return {
        **node,
        "cards": [
            {
                "card_id": str(v["id"]),
                "title": v.get("title") or "",
                "body_text": "".join(Markup(v["description"]).words),
                "attachments": len(attachments(v)),
            }
            for v in cards
        ],
    }


def fill_bodies(client, c, url, bodies, confirm, stamps):
    if not isinstance(bodies, dict) or any(
        not isinstance(v, str) or not v.strip() or len(v) > 30000
        for v in bodies.values()
    ):
        raise XxtError("请提供知识点 ID 与非空正文，每点最多三万字。")
    batch = read_body_cards(client, c, url, list(bodies))
    receipts, bindings = [], {}
    for node, cards in batch:
        pid = node["point_id"]
        before = snapshot(cards)
        # Include the body owner mapping so preview cannot migrate to a new node.
        bindings[pid] = digest([node, before])
        if not confirm:
            status = (
                "preserved"
                if any(map(has_prose, cards))
                else "review_multiple_cards"
                if len(cards) != 1
                else "would_fill"
            )
            if status == "would_fill":
                attachments(cards[0])
        elif bindings[pid] != stamps.get(pid):
            status = "changed_since_preview"
        elif any(map(has_prose, cards)):
            status = "preserved"
        elif len(cards) != 1:
            status = "review_multiple_cards"
        else:
            card = cards[0]
            prior = attachments(card)
            body = para(bodies[pid]) + placeholder_free_html(card["description"])
            form = {
                "id": str(card["id"]),
                "courseId": c.id,
                "nodeid": node["node_id"],
                "title": card.get("title") or "",
                "description": body,
                "attachments": json.dumps(prior, ensure_ascii=False),
                "isMicroCourseEdit": "false",
            }
            try:
                # Refresh immediately before each write, including when the batch took time to read.
                if snapshot(get_cards(client, c, node)) != before:
                    status = "changed_since_preview"
                else:
                    client._call(M1, "/mooc-ans/edit/savecard", "POST", form)
                    out = get_cards(client, c, node)
                    verified = (
                        len(out) == 1
                        and str(out[0]["id"]) == str(card["id"])
                        and out[0].get("title") == card.get("title")
                    )
                    status = (
                        "verified"
                        if verified
                        and out[0]["description"] == body
                        and attachments(out[0]) == prior
                        else "unconfirmed"
                    )
            except Exception:
                # Do not retry a write after ambiguous transport or browser control loss.
                status = "unconfirmed"
        receipts.append({"point_id": pid, "node_id": node["node_id"], "status": status})
        if status in {"unconfirmed", "changed_since_preview"}:
            break
    return receipts, bindings


_VISIT = "/mooc-ans/nodedetailcontroller/visitnodedetail"


def chapter_links(body, course):
    ids = []
    for link in Markup(body).links:
        try:
            u = urlsplit(link)
        except ValueError:
            continue
        q = parse_qs(u.query)
        if (
            u.scheme == "https"
            and u.netloc == M1
            and u.path == _VISIT
            and q.get("courseId") == [str(course)]
            and len(q.get("knowledgeId", [])) == 1
            and re.fullmatch(r"[1-9][0-9]*", q["knowledgeId"][0])
        ):
            ids.append(q["knowledgeId"][0])
    return list(dict.fromkeys(ids))


def point_properties(client, c, pid):
    if numeric(pid) not in {str(p["point_id"]) for p in client.knowledge_points(c.id)}:
        raise XxtError("知识点 ID 不属于这门课程。")
    p = client._get(
        "/mooc2-ans/questionBankTopic/edittopicproperty",
        {"courseid": c.id, "cpi": c.cpi, "topicModelId": 0, "topicId": pid},
    )
    if (
        not isinstance(p, dict)
        or p.get("status") is not True
        or not isinstance(p.get("topiclabelList"), list)
        or "classify" not in p
    ):
        raise XxtError("知识点属性读取失败。")
    return p


def update_fields(p):
    return {
        "classify": p["classify"],
        "cognize": p.get("cognize", -1),
        "topicDesc": p.get("topicDesc") or "",
        "topicLabelIds": ",".join(numeric(i["id"]) for i in p["topiclabelList"]),
        "teachTargert": p.get("teachTarget") or "",
        "studyHours": p["studyHours"] if p.get("studyHours") is not None else "",
    }


def resource(client, c, chapter, card_id, mid):
    source = client.chapter_cards(c.id, numeric(chapter))
    if str(source["chapter_id"]) != chapter:
        raise XxtError("章节原生 ID 不匹配。")
    cards = [x for x in source["cards"] if str(x["card_id"]) == numeric(card_id)]
    if len(cards) != 1:
        raise XxtError("章节卡片缺失或重复。")
    body = cards[0]["content_html"]
    if cards[0]["truncated"]:
        full = client._read_card(c, chapter, card_id)
        if (
            not isinstance(full, dict)
            or str(full.get("nodeid")) != chapter
            or str(full.get("id")) != card_id
            or not isinstance(full.get("description"), str)
        ):
            raise XxtError("无法读取完整章节卡片。")
        body = full["description"]
    items = [a for a in card_attachments(body) if str(a.get("mid")) == numeric(mid)]
    if len(items) != 1 or items[0].get("module") not in {
        "insertvideo",
        "insertdoc",
        "insertimage",
    }:
        raise XxtError("指定资源不属于这张章节卡片，或不支持该类型。")
    return items[0]


def resource_points(client, c, mid):
    url = "/mooc-ans/knowledge-topic-relation/knowledge-topics?" + urlencode(
        {"courseid": c.id, "mid": mid, "query": "", "queryType": 0, "graphId": ""}
    )
    response = client._call(M1, url)
    j = response.get("json") or {}
    if (
        response.get("http") != 200
        or j.get("status") is not True
        or "origin" not in (j.get("data") or {})
    ):
        raise XxtError("关联知识点读取失败。")
    raw = j["data"]["origin"]
    if isinstance(raw, str):
        raw = (
            json.loads(raw)
            if raw.strip().startswith("[")
            else [s for s in raw.split(",") if s]
        )
    if not isinstance(raw, list):
        raise XxtError("无法解析资源关联。")
    return [
        numeric(
            x.get("topicId", x.get("topicid", x.get("id")))
            if isinstance(x, dict)
            else x
        )
        for x in raw
    ]


def register_graph_authoring(tool, client, check_write, dry):
    def writable(course):
        return client().ctx(check_write(course).id)

    @tool(
        "read",
        "按原生知识点 ID 批量读取正文编辑器中的卡片、正文和附件数，每批最多 40 点。editor_url 请用本课程知识点属性中的编辑器网址。",
    )
    def read_knowledge_bodies(
        course: str, editor_url: str, point_ids: list[str]
    ) -> dict:
        api = client()
        rows = read_body_cards(api, api.ctx(course), editor_url, point_ids)
        return {"points": [body_summary(node, cards) for node, cards in rows]}

    @tool(
        "write",
        "按原生 ID 分批补写尚无正文的知识点。传入 ID 到纯文本的映射，保留已有正文和媒体。逐条返回保存结果。",
    )
    def fill_knowledge_bodies(
        course: str,
        editor_url: str,
        bodies: dict[str, str],
        confirm: bool = False,
        source_digests: dict[str, str] | None = None,
    ) -> dict:
        c = writable(course)
        receipts, stamps = fill_bodies(
            client(), c, editor_url, bodies, confirm, source_digests or {}
        )
        if not confirm:
            return dry(
                c,
                "补写缺失的知识点正文",
                bind={"source_digests": stamps},
                points=receipts,
            )
        ok = len(receipts) == len(bodies) and all(
            r["status"] in {"preserved", "verified"} for r in receipts
        )
        return {
            "ok": ok,
            "points": receipts,
            "unprocessed": list(bodies)[len(receipts) :],
        }

    @tool(
        "read", "列出知识点属性说明中指向本课章节的链接。思政节点使用相同的知识点 ID。"
    )
    def get_point_chapter_links(course: str, point_id: str) -> dict:
        api = client()
        c = api.ctx(course)
        p = point_properties(api, c, point_id)
        return {
            "point_id": point_id,
            "chapter_ids": chapter_links(p.get("topicDesc") or "", c.id),
        }

    @tool(
        "write",
        "在知识点说明末尾补上本课程的章节链接，保留原说明、标签、学习目标及已有链接。",
    )
    def add_point_chapter_links(
        course: str,
        point_id: str,
        chapter_ids: list[str],
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        api, c = client(), writable(course)
        p = point_properties(api, c, point_id)
        fields = update_fields(p)
        chapters = {str(x["chapter_id"]): str(x["title"]) for x in api.chapters(c.id)}
        ids = list(dict.fromkeys(numeric(n) for n in chapter_ids))
        if not ids or any(i not in chapters for i in ids):
            raise XxtError("目标章节需属于本课程。")
        linked = chapter_links(fields["topicDesc"], c.id)
        todo = [i for i in ids if i not in linked]
        stamp = digest([fields, [(i, chapters[i]) for i in ids]])
        if not confirm:
            return dry(
                c,
                "补充知识点到章节的链接",
                bind={"source_digest": stamp},
                point_id=point_id,
                add=todo,
                existing=linked,
            )
        if stamp != source_digest:
            raise XxtError("知识点或章节已变化，请重新预演。")
        if not todo:
            return {"ok": True, "added": [], "chapter_ids": linked}
        fields["topicDesc"] += "".join(
            f'<p><a href="https://{M1}{_VISIT}?courseId={numeric(c.id)}&amp;knowledgeId={i}" target="_blank">进入章节 · {html.escape(chapters[i])}</a></p>'
            for i in todo
        )
        api._post(
            "/mooc2-ans/questionBankTopic/savepropertyedit",
            {**fields, "courseid": c.id, "cpi": c.cpi, "topicIds": point_id},
        )
        back = point_properties(api, c, point_id)
        detail = api._get(
            "/mooc2-ans/coursetopic/gettopicdetail",
            {**api._mp(c), "topicId": point_id, "topicModelId": 0},
        )
        targets = chapter_links(
            ((detail or {}).get("data") or {}).get("topicDesc") or "", c.id
        )
        ok = update_fields(back) == fields and all(i in targets for i in ids)
        return {"ok": ok, "added": todo if ok else [], "chapter_ids": targets}

    @tool(
        "read",
        "查看指定章节卡片内的视频、文档或图片资源关联了哪些知识点。mid 来自章节卡片里的原生模块。",
    )
    def get_resource_point_links(
        course: str, chapter_id: str, card_id: str, mid: str
    ) -> dict:
        api = client()
        c = api.ctx(course)
        resource(api, c, chapter_id, card_id, mid)
        return {"mid": mid, "point_ids": resource_points(api, c, mid)}

    @tool("write", "为章节内已存在的资源追加原生知识点关联，保留原有全部关联。")
    def add_resource_point_links(
        course: str,
        chapter_id: str,
        card_id: str,
        mid: str,
        point_ids: list[str],
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        api, c = client(), writable(course)
        asset = resource(api, c, chapter_id, card_id, mid)
        linked = resource_points(api, c, mid)
        known = {str(p["point_id"]) for p in api.knowledge_points(c.id)}
        if not point_ids or any(numeric(p) not in known for p in point_ids):
            raise XxtError("待关联的知识点必须属于当前课程。")
        want = list(dict.fromkeys([*linked, *point_ids]))
        stamp = digest([asset, sorted(linked)])
        if not confirm:
            return dry(
                c,
                "为章节资源添加知识点",
                bind={"source_digest": stamp},
                mid=mid,
                existing=linked,
                desired=want,
            )
        if stamp != source_digest:
            raise XxtError("资源或原有关联已变化，请重新预演。")
        if set(linked) != set(want):
            api._call(
                M1,
                "/mooc-ans/knowledge-topic-relation/save-relation",
                "POST",
                {
                    "courseid": c.id,
                    "knowledgeid": chapter_id,
                    "cardId": card_id,
                    "microTopicId": 0,
                    "mid": mid,
                    "_jobid": asset.get("_jobid") or asset.get("jobid") or "",
                    "topicIds": ",".join(want) + ",",
                },
            )
        back = resource_points(api, c, mid)
        return {"ok": set(back) == set(want), "mid": mid, "point_ids": back}

    def read_display(api, c):
        j = api._get(
            "/mooc2-ans/coursetopic/gettopicsetting",
            {"courseid": c.id, "clazzid": c.clazz_id, "cpi": c.cpi, "topicModelId": 0},
        )
        cfg = (j or {}).get("data") or {}
        if (j or {}).get("status") is not True or cfg.get("topicCard") not in (0, 1):
            raise XxtError("无法核验知识点卡片开关。")
        return {
            "enabled": bool(cfg["topicCard"]),
            "teaching_target": cfg.get("teachTarget"),
        }

    @tool(
        "read",
        "读取图谱高级设置里的知识点卡片开关。能力图谱的知识点通过卡片里的知识概览进入关联章节。",
    )
    def get_graph_point_card_display(course: str) -> dict:
        api = client()
        return read_display(api, api.ctx(course))

    @tool("write", "在图谱的高级设置中开启或关闭知识点卡片，核对开关和教学目标设置。")
    def set_graph_point_card_display(
        course: str, enabled: bool, confirm: bool = False, source_digest: str = ""
    ) -> dict:
        api, c = client(), writable(course)
        before = read_display(api, c)
        stamp = digest(before)
        if not confirm:
            return dry(
                c,
                "设置图谱知识点卡片",
                bind={"source_digest": stamp},
                before=before["enabled"],
                after=enabled,
            )
        if stamp != source_digest:
            raise XxtError("图谱设置已变化，请重新预演。")
        if before["enabled"] == enabled:
            return {"ok": True, **before}
        from .xxt import M2

        params = urlencode(
            {"courseid": c.id, "clazzid": c.clazz_id, "cpi": c.cpi, "ut": "t"}
        )
        page = f"https://{M2}/topic-ans/knowgraph/index.html#/knowledgeMapTempPage?{params}"
        api.b.navigate(page)
        guard = (
            "if(location.origin!=="
            + json.dumps("https://" + M2)
            + "||location.pathname!=='/topic-ans/knowgraph/index.html' "
            "||new URLSearchParams(location.hash.split('?')[1]).get('courseid')!=="
            + json.dumps(str(c.id))
            + ")return false;"
        )
        for title in ("设置", "高级设置"):
            find = (
                "[...document.querySelectorAll('*')].find(e=>!e.childElementCount && e.offsetWidth && "
                "e.textContent.trim()===" + json.dumps(title) + ")"
            )
            if not api.wait_for(guard + "return !!" + find):
                raise XxtError("图谱设置界面未显示。")
            api.here(
                guard
                + "const el="
                + find
                + ";if(!el)return false;el.click();return true;",
                retry_safe=False,
            )
        lookup = (
            guard
            + """const row=[...document.querySelectorAll('.xformItem')].find(e=>
            e.querySelector('label.xformItem__label')?.textContent.trim()==='知识点卡片');
            const box=row?.querySelector('input[type=checkbox]'),label=row?.querySelector('label[for]');
        """
        )
        if not api.wait_for(lookup + "return !!box && !!label;"):
            raise XxtError("无法定位知识点卡片开关。")
        if not api.here(
            lookup
            + "if(!box||!label||box.checked!=="
            + json.dumps(before["enabled"])
            + "||!row.nextElementSibling?.textContent.includes('知识点建设/学情概览'))return false;"
            "label.click();return true;",
            retry_safe=False,
        ):
            raise XxtError("知识点卡片开关与预演状态不一致。")
        # The settings component debounces its save. Stay on it until its native settings read sees the change.
        cfg_url = "/mooc2-ans/coursetopic/gettopicsetting?" + urlencode(
            {"courseid": c.id, "clazzid": c.clazz_id, "cpi": c.cpi, "topicModelId": 0}
        )
        persisted = api.wait_for(
            guard
            + "const r=await J("
            + json.dumps(cfg_url)
            + ");return r?.status===true && "
            "r.data?.topicCard===" + str(int(enabled)) + ";"
        )
        after = read_display(api, c)
        return {
            "ok": bool(persisted) and after == {**before, "enabled": enabled},
            **after,
        }

    @tool(
        "write",
        "单独添加或移除知识点的课程思政标签，保留其他标签及属性，核对图谱中的节点。",
    )
    def set_point_ideology_membership(
        course: str,
        point_id: str,
        included: bool,
        confirm: bool = False,
        source_digest: str = "",
    ) -> dict:
        api, c = client(), writable(course)
        p = point_properties(api, c, point_id)
        labels = [
            numeric(x["label_id"])
            for x in api.knowledge_labels(c.id, c=c)
            if x.get("name") == "课程思政"
        ]
        if len(labels) != 1:
            raise XxtError("未找到唯一的课程思政标签。")
        tag = labels[0]
        fields = update_fields(p)
        original = [numeric(x["id"]) for x in p["topiclabelList"]]
        stamp = digest([fields, tag])
        if not confirm:
            return dry(
                c,
                "变更知识点的课程思政标签",
                bind={"source_digest": stamp},
                point_id=point_id,
                before=tag in original,
                after=included,
            )
        if stamp != source_digest:
            raise XxtError("知识点或标签已变化，请重新预演。")
        expected = (
            [*original, tag]
            if included and tag not in original
            else [i for i in original if included or i != tag]
        )
        if expected != original:
            fields["topicLabelIds"] = ",".join(expected)
            api._post(
                "/mooc2-ans/questionBankTopic/savepropertyedit",
                {**fields, "courseid": c.id, "cpi": c.cpi, "topicIds": point_id},
            )
        after = update_fields(point_properties(api, c, point_id))
        graph_nodes = [n for n in api._graph_nodes(c) if str(n.get("id")) == point_id]
        tags = (
            set((graph_nodes[0].get("tag") or "").strip(",").split(",")) - {""}
            if len(graph_nodes) == 1
            else None
        )
        want_tags = set(x for x in fields.pop("topicLabelIds").split(",") if x)
        actual_tags = set(x for x in after.pop("topicLabelIds").split(",") if x)
        return {
            "ok": after == fields and actual_tags == tags == want_tags,
            "point_id": point_id,
            "included": tag in actual_tags,
        }

    @tool(
        "read",
        "分批核对图谱「知识概览→查看」实际使用的详情页面里的章节链接。可选学生版布局，使用当前登录账号的权限。",
    )
    def get_rendered_point_chapter_links(
        course: str, point_ids: list[str], student_layout: bool = False
    ) -> dict:
        from .xxt import M2

        api = client()
        c = api.ctx(course)
        known = {str(p["point_id"]) for p in api.knowledge_points(c.id)}
        if (
            not 1 <= len(point_ids) <= 40
            or any(numeric(i) not in known for i in point_ids)
            or len(set(point_ids)) != len(point_ids)
        ):
            raise XxtError("每批限本课程内 1–40 个不同的知识点 ID。")
        route = "/mooc2-ans/questionBankTopic/gettopicdesc"
        args = {
            "courseid": c.id,
            "clazzid": c.clazz_id,
            "cpi": c.cpi,
            "ut": "s" if student_layout else "t",
        }
        result = []
        for pid in point_ids:
            url = route + "?" + urlencode({**args, "topicId": pid})
            payload = api.on(
                M2,
                "const u="
                + json.dumps(url)
                + ",cid="
                + json.dumps(str(c.id))
                + r""";const r=await fetch(u,{credentials:'include',cache:'no-store',redirect:'error'});
                if(!r.ok||new URL(r.url).pathname!==new URL(u,location.origin).pathname)return null;
                const d=D(await r.text());if(!d.body || d.querySelector('input[type=password]'))return null;
                const ids=new Set();for(const a of d.querySelectorAll('a[href]')){
                  let link;try{link=new URL(a.getAttribute('href'));}catch{continue;}
                  const q=link.searchParams,ks=q.getAll('knowledgeId');
                  if(link.origin==='https://mooc1.chaoxing.com' && link.pathname==='/mooc-ans/nodedetailcontroller/visitnodedetail'
                    && q.getAll('courseId').length===1 && q.get('courseId')===cid && ks.length===1
                    && /^[1-9][0-9]*$/.test(ks[0]))ids.add(ks[0]);}
                return [...ids];""",
            )
            if not isinstance(payload, list):
                raise XxtError("知识点详情未返回，请核对账号权限和课程布局。")
            result.append(
                {"point_id": pid, "chapter_ids": [numeric(i) for i in payload]}
            )
        return {"points": result, "student_layout": student_layout}
