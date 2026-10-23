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
        if re.match(r"^[a-zA-Z_]+:", line):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def project_output_error(root: Path, source_id: str, item: dict, output: str) -> str | None:
    """Verify a claimed canonical project update cites this exact source revision."""
    target = (root / output).resolve()
    if not target.is_relative_to(root.resolve()) or target.parent != (root / "projects").resolve() or not target.is_file():
        return "project output must be an existing canonical project page"
    if not isinstance(item.get("outputs"), list) or output not in item["outputs"]:
        return "project output is absent from outputs"
    text = target.read_text(encoding="utf-8")
    meta = frontmatter(text)
    if not meta or meta.get("type") != "project":
        return "project output is not a project page"
    header = text.split("---", 2)[1]
    for block in re.split(r"(?m)^\s+- id:", header)[1:]:
        if block.splitlines()[0].strip(" \"'") == source_id:
            modified = re.search(r"(?m)^\s+modified:\s*(.+)$", block)
            if modified and modified.group(1).strip(" \"'") == item.get("modifiedTime"):
                return None
    return "project output lacks the exact source ID and observed modification time"


def project_checkpoint_errors(root: Path, source_id: str, item: dict) -> list[str]:
    projects = item.get("project_outputs", [])
    if not isinstance(projects, list) or any(not isinstance(path, str) for path in projects):
        return [f"{source_id}: project_outputs must be a list of canonical paths"]
    return [f"{source_id}: {error}: {path}" for path in projects
            if (error := project_output_error(root, source_id, item, path))]


def in_scope(relative: Path, scope: str) -> bool:
    whatsapp = relative.parts[0] in {"whatsapp", "whatsapp-ingestion.json"}
    return scope == "all" or whatsapp == (scope == "whatsapp")


def validate(root: Path, scope: str = "all") -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        if not in_scope(relative, scope):
            continue
        text = path.read_text(encoding="utf-8")
        meta = frontmatter(text)
        is_log_or_root_index = (
            relative.as_posix() in {"index.md", "log.md", "whatsapp/log.md", "whatsapp/coverage.md"}
            or (len(relative.parts) == 3 and relative.parts[0] == "whatsapp" and relative.name == "index.md")
        )
        is_whatsapp_brain = len(relative.parts) >= 2 and relative.parts[:2] == ("whatsapp", "brain")
        if not is_log_or_root_index:
            if meta is None:
                errors.append(f"{relative}: missing frontmatter")
                continue
            missing = sorted(REQUIRED - meta.keys())
            if missing:
                errors.append(f"{relative}: missing frontmatter: {', '.join(missing)}")
            if relative.parts[0] == "whatsapp" and not is_whatsapp_brain:
                missing_provenance = sorted({"group_label", "group_jid"} - meta.keys())
                if missing_provenance:
                    errors.append(f"{relative}: missing WhatsApp provenance: {', '.join(missing_provenance)}")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", relative.name) and meta.get("type") != "coverage-status":
                    jid = meta.get("group_jid", "").strip("\"'")
                    if not re.fullmatch(r"\d+(?:-\d+)?@g\.us", jid):
                        errors.append(f"{relative}: daily digest requires an exact group JID")
                    if meta.get("sources", "").strip() == "[]":
                        errors.append(f"{relative}: daily digest has no source provenance; use coverage-status for no-record checks")
        if relative.parts[0] == "whatsapp":
            if re.search(r"(?m)^[-*] \[\d{4}-\d{2}-\d{2}T", text):
                errors.append(f"{relative}: copied timestamped chat messages instead of a digest")
            if re.search(r"\bsender_jid\s*:", text):
                errors.append(f"{relative}: exposes a sender identifier")
            if relative.name not in {"index.md", "log.md"}:
                for heading in WHATSAPP_WORK_HEADINGS:
                    if heading in text:
                        errors.append(f"{relative}: work-oriented WhatsApp heading: {heading}")
                if text.count("## Developments — later archive batch") > 0:
                    errors.append(f"{relative}: duplicate late-developments section")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(root.resolve()):
                errors.append(f"{relative}: link escapes knowledge wiki: {target}")
            elif (relative.parts[0] == "whatsapp") != (resolved.relative_to(root.resolve()).parts[:1] == ("whatsapp",)):
                errors.append(f"{relative}: link crosses knowledge isolation boundary: {target}")
            elif not resolved.exists():
                errors.append(f"{relative}: broken link: {target}")
    for checkpoint in root.rglob("*ingestion*.json"):
        if not in_scope(checkpoint.relative_to(root), scope):
            continue
        try:
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            entries = data.get("files", data.get("sources")) if isinstance(data, dict) else None
            if not isinstance(entries, dict) or any(
                not isinstance(item, dict) or not isinstance(item.get("modifiedTime", item.get("modified")), str)
                for item in entries.values()
            ):
                raise ValueError("expected a source map with observed modification times")
            for source_id, item in entries.items():
                if in_scope(checkpoint.relative_to(root), "whatsapp") and item.get("project_outputs"):
                    errors.append(f"{checkpoint.relative_to(root)}: WhatsApp checkpoint cannot claim Timeless project outputs")
                    continue
                errors.extend(f"{checkpoint.relative_to(root)}: {message}" for message in project_checkpoint_errors(root, source_id, item))
        except (OSError, ValueError) as exc:
            errors.append(f"{checkpoint.relative_to(root)}: invalid checkpoint: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="knowledge wiki directory")
    parser.add_argument("--scope", choices=("all", "timeless", "whatsapp"), default="all")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"not a directory: {args.root}")
    errors = validate(args.root, args.scope)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: {sum(in_scope(p.relative_to(args.root), args.scope) for p in args.root.rglob('*.md'))} Markdown pages validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
