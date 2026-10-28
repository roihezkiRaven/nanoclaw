#!/usr/bin/env python3
"""Independently check captured UTC group-days and provenance against the published digests."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

from gdrive_assistant import service
from inventory_knowledge_sources import cache_source

spec = importlib.util.spec_from_file_location(
    "knowledge_validator",
    Path(__file__).resolve().parent.parent / "scripts/validate-knowledge-wiki.py",
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def records(text):
    """Decode concatenated records, preserving literal newlines in legacy JSON strings."""
    decoder, offset = json.JSONDecoder(strict=False), 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset == len(text):
            return
        row, offset = decoder.raw_decode(text, offset)
        if not isinstance(row, dict) or not isinstance(row.get("groupJid"), str):
            raise ValueError("Invalid archive group provenance")
        stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Archive timestamp needs an explicit timezone")
        day = stamp.astimezone(timezone.utc).date().isoformat()
        yield row["groupJid"], day


def inventory(api, folder):
    files, token = [], None
    while True:
        page = (
            api.files()
            .list(
                q=f"trashed=false and '{folder}' in parents",
                pageSize=1000,
                pageToken=token,
                fields="nextPageToken,files(id,name,mimeType,modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files += [f for f in page.get("files", []) if f["name"].startswith("whatsapp-raw-") and f["name"].endswith(".jsonl")]
        token = page.get("nextPageToken")
        if not token:
            return files


def digest_pages(wiki):
    result = {}
    for path in (wiki / "whatsapp").glob("*/*.md"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}.md", path.name):
            continue
        text = path.read_text()
        meta = validator.frontmatter(text) or {}
        if meta.get("type") == "coverage-status":
            continue
        key = (meta.get("group_jid", "").strip("\"'"), path.stem)
        if key in result:
            raise ValueError("Duplicate canonical group/day digest")
        result[key] = path
    return result


def expected_days(api, files, checkpoint, cache):
    expected, pending, normalized = defaultdict(set), [], []
    for item in files:
        cache_source(api, item, cache)
        if checkpoint.get(item["id"], {}).get("modifiedTime") != item["modifiedTime"]:
            pending.append(item)
            continue
        revision = hashlib.sha256(item["modifiedTime"].encode()).hexdigest()
        text = json.loads((cache / item["id"] / (revision + ".json")).read_text())["text"]
        try:
            for line in text.splitlines():
                if line.strip():
                    json.loads(line)
        except ValueError:
            normalized.append(item["id"])
        for key in records(text):
            expected[key].add(item["id"])
    return expected, pending, normalized


def coverage_errors(wiki, expected):
    pages, errors = digest_pages(wiki), []
    for key, source_ids in expected.items():
        path = pages.get(key)
        if path is None:
            errors.append(f"{key[1]}: captured group/day has no canonical digest")
            continue
        header = path.read_text().split("---", 2)[1]
        if any(id not in header for id in source_ids):
            errors.append(f"{path.relative_to(wiki)}: contributing archive source omitted from provenance")
    return errors


def coverage_page(wiki, result):
    lines = [
        "# WhatsApp evidence coverage",
        "",
        "Checked at **" + result["checked_at"] + "**.",
        f"{result['eligible_sources']} archive sources observed; {result['pending_sources']} await ingestion.",
        f"All {result['processed_group_days']} processed captured group-days have a canonical digest and complete source references.",
        f"{result['normalized_legacy_sources']} legacy source required lossless JSON newline normalization; original bytes are preserved.",
        "",
        "This covers captured records only. Collector outages, messages never captured and days without retained records remain unknown; an absent digest date does not prove inactivity.",
        "",
        "## Group evidence",
        "",
        "| Group | Digest days | First captured day | Last captured day |",
        "| --- | ---: | --- | --- |",
    ]
    groups = defaultdict(list)
    for (_, day), path in digest_pages(wiki).items():
        groups[path.parent.name].append(day)
    for group, days in sorted(groups.items()):
        lines.append(f"| [{group.replace('-', ' ')}]({group}/index.md) | {len(days)} | {min(days)} | {max(days)} |")
    return "\n".join(lines) + "\n"


def audit(args):
    api = service("reader", False)
    files = inventory(api, args.archive_folder)
    checkpoint = json.loads((args.wiki / "whatsapp-ingestion.json").read_text()).get("files", {})
    if checkpoint and not files:
        raise ValueError("Empty archive inventory with an existing checkpoint; availability is unverified")
    expected, pending, normalized = expected_days(api, files, checkpoint, args.cache_dir)
    errors = coverage_errors(args.wiki, expected)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "complete": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "eligible_sources": len(files),
        "processed_group_days": len(expected),
        "pending_sources": len(pending),
        "pending": pending,
        "normalized_legacy_sources": len(normalized),
        "capture_completeness": "unknown outside captured records",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiki", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--archive-folder", required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", args.archive_folder):
        parser.error("Invalid archive folder")
    result = audit(args)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.state.with_suffix(".tmp")
    temporary.write_text(json.dumps(result))
    temporary.replace(args.state)
    page = args.wiki / "whatsapp/coverage.md"
    temporary = page.with_suffix(".tmp")
    temporary.write_text(coverage_page(args.wiki, result))
    temporary.replace(page)
    print(json.dumps({k: v for k, v in result.items() if k != "pending"}))


if __name__ == "__main__":
    main()
