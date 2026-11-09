"""RSS / Atom parsing with defusedxml (feeds are untrusted input)."""

from __future__ import annotations

from typing import Any

from defusedxml import ElementTree as ET  # noqa: N817

ATOM = "{http://www.w3.org/2005/Atom}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """Parse RSS 2.0 or Atom into plain dicts keyed by tag local-name.

    Repeated tags (e.g. <category>) become lists under the key `<name>_all`.
    """
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    entries = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    items: list[dict[str, Any]] = []
    for entry in entries:
        item: dict[str, Any] = {}
        for child in entry:
            name = _local(child.tag)
            if name == "link" and child.get("href"):  # Atom
                value = child.get("href") or ""
            else:
                value = (child.text or "").strip()
            item.setdefault(name, value)
            item.setdefault(f"{name}_all", []).append(value)
        items.append(item)
    return items
