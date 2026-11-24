"""Edit existing chapter cards while preserving native task-point placeholders."""

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .ops_exhibit import fingerprint
from .ops_write import card_attachments, sanitize_html
from .xxt import XxtError, _safe_id


def replace_visible_text(source, find, replacement):
    """Change one visible text span without serializing any surrounding markup."""
    if not find:
        raise XxtError("缺少原文字。")
    starts = [0] + [m.end() for m in re.finditer("\n", source)]
    hits = []

    class TextSpans(HTMLParser):
        blocked = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "iframe", "template"):
                self.blocked += 1

        def handle_endtag(self, tag):
            if tag in ("script", "style", "iframe", "template"):
                self.blocked = max(0, self.blocked - 1)

        def handle_data(self, text):
            if self.blocked:
                return
            line, col = self.getpos()
            hits.extend(
                starts[line - 1] + col + m.start()
                for m in re.finditer(re.escape(find), text)
            )

    parser = TextSpans(convert_charrefs=False)
    parser.feed(source)
    parser.close()
    if len(hits) != 1:
        raise XxtError("原文字在可见正文中必须恰好匹配一次。")
    at = hits[0]
    return (
        source[:at] + html.escape(replacement, quote=False) + source[at + len(find) :]
    )


def replace_resource_url(source, old, new):
    starts = [0] + [m.end() for m in re.finditer("\n", source)]
    changes = []
    attr = re.compile(
        r"""\s+([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?"""
    )

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in (
                "a",
                "img",
                "iframe",
                "source",
                "video",
                "audio",
                "embed",
                "link",
            ):
                return
            raw = self.get_starttag_text()
            index = re.match(r"<[^\s/>]+", raw).end()
            line, col = self.getpos()
            while m := attr.match(raw, index):
                index = m.end()
                if m[1].lower() not in ("href", "src"):
                    continue
                group = next((k for k in (2, 3, 4) if m[k] is not None), None)
                if group and html.unescape(m[group]) == old:
                    a, b = m.span(group)
                    changes.append(
                        (starts[line - 1] + col + a, starts[line - 1] + col + b)
                    )

    parser = Links(convert_charrefs=False)
    parser.feed(source)
    parser.close()
    if not changes:
        raise XxtError("章节中没有该资源地址。")
    for a, b in reversed(changes):
        source = source[:a] + html.escape(new, quote=True) + source[b:]
    return source


def patch_card(source, mode, content, find):
    before = card_attachments(source)
    if mode == "append":
        block = sanitize_html(content)
        if not block.strip():
            raise XxtError("追加内容为空。")
        result = source + block
    elif mode == "text":
        result = replace_visible_text(source, find, content)
    elif mode == "resource_url":
        for url in (find, content):
            u = urlsplit(url)
            if (
                u.scheme != "https"
                or not u.hostname
                or u.username
                or u.password
                or u.port not in (None, 443)
                or not (
                    u.hostname.endswith((".chaoxing.com", ".cldisk.com"))
                    or u.hostname == "vrmodel.sslibweb.com"
                )
                or re.search(r"""[\s<>"'`\\]""", url)
            ):
                raise XxtError("只接受超星课程资源和三维教学资源的 HTTPS 地址。")
        result = replace_resource_url(source, find, content)
    else:
        raise XxtError("mode 可选 append、text、resource_url。")
    if card_attachments(result) != before:
        raise XxtError("章节任务点发生变化，已停止。")
    return result


def register_chapter_patches(tool, client, check_write, dry):
    @tool(
        "write",
        "在已有任务点的章节卡片追加图文、替换指定正文或更新已有资源地址，保留原生测验和附件。",
    )
    def patch_chapter_card(
        course: str,
        chapter: str,
        card_id: str,
        mode: str,
        content: str,
        find: str = "",
        confirm: bool = False,
        revision: str = "",
    ):
        cl, c = client(), check_write(course)
        node = cl.find_chapter(c.id, chapter)["chapter_id"]
        card = cl._read_card(c, _safe_id(node), _safe_id(card_id))
        if not card or str(card.get("id")) != card_id:
            raise XxtError("章节中找不到指定卡片。")
        body = card["description"] or ""
        after = patch_card(body, mode, content, find)
        current = fingerprint([card_id, card["title"], body])
        if not confirm:
            return dry(
                c,
                "更新章节卡片",
                chapter=node,
                card_id=card_id,
                mode=mode,
                find=find,
                content=content,
                bind={"chapter": node, "revision": current},
            )
        if current != revision:
            raise XxtError("卡片已变化。")
        if after != body:
            receipt = cl._save_card(
                c, node, card_id, card["title"], after, card_attachments(after)
            )
            if receipt.get("http") != 200:
                raise XxtError("卡片保存回执不明确。")
        back = cl._read_card(c, node, card_id)
        return {
            "ok": bool(
                back
                and str(back.get("id")) == card_id
                and back["description"] == after
                and back["title"] == card["title"]
            ),
            "card_id": card_id,
            "attachments": len(card_attachments(after)),
        }
