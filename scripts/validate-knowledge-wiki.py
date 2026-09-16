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
        if meta is not None and meta.get("generated", "").lower() == "true":
            missing = sorted(REQUIRED - meta.keys())
            if missing:
                errors.append(f"{path.relative_to(root)}: missing frontmatter: {', '.join(missing)}")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{path.relative_to(root)}: broken link: {target}")
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
