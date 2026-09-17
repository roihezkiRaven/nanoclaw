#!/usr/bin/env python3
"""Validate a Markdown knowledge graph without changing it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
REQUIRED = {"type", "title", "description", "tags", "generated", "sources"}
WHATSAPP_FORBIDDEN_LINKS = ("../projects/", "../topics/", "../tasks/", "../people/", "../decisions/")
WHATSAPP_WORK_HEADINGS = (
    "## Developments",
    "## Decisions",
    "## Actions and deadlines",
    "## Blockers or open questions",
    "## Technical/context notes",
)


def frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta = frontmatter(text)
        relative = path.relative_to(root)
        is_log_or_root_index = (
            relative.as_posix() in {"index.md", "log.md", "whatsapp/log.md", "whatsapp/coverage.md"}
            or (len(relative.parts) == 3 and relative.parts[0] == "whatsapp" and relative.name == "index.md")
        )
        if not is_log_or_root_index:
            if meta is None:
                errors.append(f"{relative}: missing frontmatter")
                continue
            missing = sorted(REQUIRED - meta.keys())
            if missing:
                errors.append(f"{relative}: missing frontmatter: {', '.join(missing)}")
            if relative.parts[0] == "whatsapp":
                missing_provenance = sorted({"group_label", "group_jid"} - meta.keys())
                if missing_provenance:
                    errors.append(f"{relative}: missing WhatsApp provenance: {', '.join(missing_provenance)}")
        if relative.parts[0] == "whatsapp":
            if any(link in text for link in WHATSAPP_FORBIDDEN_LINKS):
                errors.append(f"{relative}: links into Timeless graph")
            if relative.name not in {"index.md", "log.md"}:
                for heading in WHATSAPP_WORK_HEADINGS:
                    if heading in text:
                        errors.append(f"{relative}: work-oriented WhatsApp heading: {heading}")
                if text.count("## Developments — later archive batch") > 0:
                    errors.append(f"{relative}: duplicate late-developments section")
        elif "whatsapp/" in text:
            errors.append(f"{relative}: references WhatsApp knowledge")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{relative}: broken link: {target}")
    for checkpoint in root.glob("*ingestion.json"):
        try:
            json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{checkpoint.relative_to(root)}: invalid checkpoint: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="knowledge wiki directory")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"not a directory: {args.root}")
    errors = validate(args.root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: {len(list(args.root.rglob('*.md')))} Markdown pages validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
