"""Atlassian Document Format: read text out, build documents in.

Jira Cloud's v3 API represents ``description`` as ADF -- a nested JSON document
rather than a string -- so the tool needs both directions. Reading walks the
node tree collecting text; writing emits only the handful of node types a test
case needs (headings, paragraphs, ordered lists).

Reading also reports whether non-text nodes were present. A story whose
requirements live in an image or a macro cannot be fully interpreted, and the
draft says so rather than silently dropping them.
"""

from __future__ import annotations

from typing import Any

# Nodes that carry meaning this tool cannot read as text.
NON_TEXT_NODE_TYPES = frozenset(
    {
        "media",
        "mediaGroup",
        "mediaSingle",
        "mediaInline",
        "extension",
        "bodiedExtension",
        "inlineExtension",
        "embedCard",
        "blockCard",
        "inlineCard",
    }
)

# Nodes after which a line break belongs when flattening to text.
_BLOCK_NODE_TYPES = frozenset(
    {
        "paragraph",
        "heading",
        "listItem",
        "blockquote",
        "codeBlock",
        "panel",
        "tableRow",
        "taskItem",
        "decisionItem",
    }
)


class AdfText:
    """The result of flattening an ADF document."""

    def __init__(self, text: str, *, had_non_text: bool) -> None:
        self.text = text
        self.had_non_text = had_non_text

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.text


def extract_text(doc: Any) -> AdfText:
    """Flatten an ADF document to plain text.

    Accepts a real ADF document, a plain string (some Jira configurations and
    the v2 API return one), or ``None``. Headings keep their level as leading
    ``#`` marks so that a criteria section heading remains detectable
    downstream; list items keep a ``- `` marker for the same reason.
    """
    if doc is None:
        return AdfText("", had_non_text=False)
    if isinstance(doc, str):
        return AdfText(doc.strip(), had_non_text=False)

    lines: list[str] = []
    state = {"had_non_text": False}
    _walk(doc, lines, state, list_depth=0)

    text = "\n".join(line.rstrip() for line in lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return AdfText(text.strip(), had_non_text=state["had_non_text"])


def _walk(node: Any, lines: list[str], state: dict, *, list_depth: int) -> None:
    if not isinstance(node, dict):
        return

    node_type = node.get("type")

    if node_type in NON_TEXT_NODE_TYPES:
        state["had_non_text"] = True
        return

    if node_type == "text":
        _append_inline(lines, node.get("text", ""))
        return

    if node_type == "hardBreak":
        lines.append("")
        return

    if node_type == "heading":
        level = int((node.get("attrs") or {}).get("level", 1))
        inline: list[str] = []
        for child in node.get("content") or []:
            _walk(child, inline, state, list_depth=list_depth)
        heading = " ".join(part for part in inline if part).strip()
        lines.append("")
        lines.append(f"{'#' * level} {heading}".strip())
        return

    if node_type == "listItem":
        inline = []
        for child in node.get("content") or []:
            _walk(child, inline, state, list_depth=list_depth + 1)
        body = " ".join(part for part in inline if part).strip()
        if body:
            lines.append(f"{'  ' * max(0, list_depth - 1)}- {body}")
        return

    if node_type == "paragraph":
        inline = []
        for child in node.get("content") or []:
            _walk(child, inline, state, list_depth=list_depth)
        body = " ".join(part for part in inline if part).strip()
        if list_depth:
            # Inside a list item, the text belongs on the item's own line.
            if body:
                lines.append(body)
        else:
            lines.append(body)
        return

    for child in node.get("content") or []:
        _walk(child, lines, state, list_depth=list_depth)

    if node_type in _BLOCK_NODE_TYPES:
        lines.append("")


def _append_inline(lines: list[str], text: str) -> None:
    if not text:
        return
    if lines and lines[-1] and not lines[-1].endswith(("\n",)):
        lines[-1] = f"{lines[-1]}{text}"
    else:
        lines.append(text)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


def doc(*blocks: dict) -> dict:
    """Wrap blocks in an ADF document envelope."""
    return {"type": "doc", "version": 1, "content": [b for b in blocks if b]}


def heading(text: str, level: int = 3) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def paragraph(text: str) -> dict:
    """A paragraph, splitting embedded newlines into hard breaks."""
    parts = str(text).split("\n")
    content: list[dict] = []
    for index, part in enumerate(parts):
        if index:
            content.append({"type": "hardBreak"})
        if part:
            content.append({"type": "text", "text": part})
    if not content:
        content = [{"type": "text", "text": ""}]
    return {"type": "paragraph", "content": content}


def ordered_list(items: list[str]) -> dict:
    return {
        "type": "orderedList",
        "attrs": {"order": 1},
        "content": [
            {"type": "listItem", "content": [paragraph(item)]} for item in items
        ],
    }


def bullet_list(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [paragraph(item)]} for item in items
        ],
    }
