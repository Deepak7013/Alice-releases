from __future__ import annotations
import hashlib
import re
import xml.etree.ElementTree as ET
from .models import AndroidElement, AndroidScreenState

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

class AndroidStateParser:
    """Normalize Android uiautomator XML into stable semantic state."""
    def parse(self, serial: str, xml: str, package: str = "", activity: str = "") -> AndroidScreenState:
        elements = []
        try:
            root = ET.fromstring(xml or "<hierarchy />")
        except ET.ParseError as exc:
            raise ValueError(f"invalid Android UI XML: {exc}") from exc
        for idx, node in enumerate(root.iter("node")):
            b = _BOUNDS.fullmatch(node.attrib.get("bounds", ""))
            bounds = tuple(map(int, b.groups())) if b else (0, 0, 0, 0)
            clickable = node.attrib.get("clickable", "false").lower() == "true"
            enabled = node.attrib.get("enabled", "true").lower() != "false"
            focused = node.attrib.get("focused", "false").lower() == "true"
            class_name = node.attrib.get("class", "")
            if any(node.attrib.get(k) for k in ("text", "content-desc", "resource-id")) or (
                focused and "edittext" in class_name.casefold()
            ):
                elements.append(AndroidElement(
                    text=node.attrib.get("text", ""),
                    hint=node.attrib.get("hint", ""),
                    content_desc=node.attrib.get("content-desc", ""),
                    resource_id=node.attrib.get("resource-id", ""),
                    class_name=class_name,
                    clickable=clickable, enabled=enabled, bounds=bounds, index=idx, focused=focused))
        canonical = "|".join(f"{e.text}\0{e.hint}\0{e.content_desc}\0{e.resource_id}\0{e.class_name}\0{e.bounds}\0{e.focused}" for e in elements)
        fp = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return AndroidScreenState(serial, package, activity, elements, fp)
