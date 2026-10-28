#!/usr/bin/env python3
"""Reconcile the complete approved Drive tree with ingestion, without reading source content."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import re

from gdrive_assistant import service

SUPPORTED = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "text/plain",
}


def eligible(item):
    return item["mimeType"] in SUPPORTED and not re.search(r"transcript|recording|whatsapp|raw-media", item["path"], re.I)


def receive(response, error, parent, prefix, queue, files, errors):
    if error:
        errors.append(str(error))
        return
    for item in response.get("files", []):
        item["path"] = prefix + "/" + item["name"]
        files.append(item)
        if item["mimeType"] == "application/vnd.google-apps.folder":
            queue.append((item["id"], item["path"], None))
    if response.get("nextPageToken"):
        queue.append((parent, prefix, response["nextPageToken"]))


def folder_request(api, parent, token):
    return api.files().list(
        q=f"trashed=false and '{parent}' in parents",
        pageSize=1000,
        pageToken=token,
        fields="nextPageToken,files(id,name,mimeType,modifiedTime,parents)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    )


def inventory(api, root):
    queue, files, errors, visited = [(root, "", None)], [], [], set()
    while queue:
        current, queue = queue[:100], queue[100:]
        batch = api.new_batch_http_request()
        for parent, prefix, token in current:
            if token is None and parent in visited:
                continue
            visited.add(parent)
            request = folder_request(api, parent, token)
            callback = lambda _, response, error, p=parent, f=prefix: receive(response, error, p, f, queue, files, errors)
            batch.add(request, callback=callback)
        batch.execute()
    if errors:
        raise RuntimeError(f"Incomplete source inventory: {len(errors)} failed folder pages")
    return files, len(visited)


def pending_sources(sources, checkpoint):
    return [
        {
            **item,
            "pending_reason": "source_revision"
            if checkpoint.get(item["id"], {}).get("modifiedTime") != item["modifiedTime"]
            else "legacy_consolidation",
        }
        for item in sources
        if checkpoint.get(item["id"], {}).get("modifiedTime") != item["modifiedTime"]
        or checkpoint.get(item["id"], {}).get("consolidation_version") != 2
    ]


def report(files, folders, checkpoint):
    sources = [item for item in files if eligible(item)]
    if checkpoint and not sources:
        raise ValueError("Empty eligible inventory with an existing checkpoint; source availability is unverified")
    changed = pending_sources(sources, checkpoint)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "folders": folders,
        "items": len(files),
        "eligible_sources": len(sources),
        "pending_sources": len(changed),
        "latest_source_revision": max((s["modifiedTime"] for s in sources), default=None),
        "revision_dates": dict(sorted(Counter(s["modifiedTime"][:10] for s in sources).items(), reverse=True)),
        "files": sources,
        "pending": changed,
    }


def coverage_header(root_id, result):
    return {
        "type": "reference",
        "title": "Timeless source coverage",
        "description": "Observed Drive inventory, ingestion lag and explicit limits.",
        "tags": [],
        "generated": result["checked_at"][:10],
        "sources": ["https://drive.google.com/drive/folders/" + root_id],
    }


def coverage_page(root_id, result):
    header = coverage_header(root_id, result)
    lines = [
        f"Checked at **{result['checked_at']}**; complete recursive, paginated inventory.",
        f"{result['eligible_sources']} eligible sources; **{result['pending_sources']}** new, revised or legacy sources await consolidation.",
        f"Latest observed source revision: **{result['latest_source_revision']}**.",
        "",
        "These dates are Drive source revision dates, not meeting dates or proof of calendar completeness. An absent date is a source-availability gap, not evidence of no meetings or lost ingestion.",
        "",
        "## Source revision dates",
        "",
        "| Date | Eligible notes |",
        "| --- | ---: |",
    ]
    lines += [f"| {day} | {count} |" for day, count in result["revision_dates"].items()]
    return (
        "---\n"
        + "\n".join(k + ": " + json.dumps(v) for k, v in header.items())
        + "\n---\n\n# Timeless source coverage\n\n"
        + "\n".join(lines)
        + "\n"
    )


def fetch_source(api, item):
    if item["mimeType"] == "application/vnd.google-apps.document":
        return api.files().export_media(fileId=item["id"], mimeType="text/plain").execute(num_retries=2)
    elif item["mimeType"] == "application/vnd.google-apps.spreadsheet":
        return api.files().export_media(fileId=item["id"], mimeType="text/csv").execute(num_retries=2)
    else:
        return api.files().get_media(fileId=item["id"]).execute(num_retries=2)


def cache_source(api, item, cache):
    revision = hashlib.sha256(item["modifiedTime"].encode()).hexdigest()
    path = cache / item["id"] / (revision + ".json")
    if path.exists():
        return
    data = fetch_source(api, item)
    current = api.files().get(fileId=item["id"], fields="modifiedTime").execute()
    if current["modifiedTime"] != item["modifiedTime"]:
        raise ValueError("Source changed during independent cache read")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    value = {
        "meta": item,
        "complete": True,
        "text": data.decode("utf-8-sig"),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def cache_sources(api, files, cache):
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in files:
        cache_source(api, item, cache)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-folder", required=True)
    parser.add_argument("--wiki", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", args.root_folder):
        parser.error("Invalid source folder ID")
    return args


def stamp_pending(result, state):
    """Measure queue age from observation, separately from the source event/revision."""
    previous = json.loads(state.read_text()) if state.exists() else {}
    prior = {(p['id'], p['modifiedTime'], p.get('pending_reason')): p for p in previous.get('pending', [])}
    for item in result.get('pending', []):
        old = prior.get((item['id'], item['modifiedTime'], item.get('pending_reason')))
        item['pending_since'] = (old.get('pending_since', previous.get('checked_at')) if old else None) or result['checked_at']
    return result


def main():
    args = arguments()
    checkpoint = json.loads((args.wiki / "ingestion.json").read_text()).get("files", {})
    api = service("reader", False)
    result = stamp_pending(report(*inventory(api, args.root_folder), checkpoint), args.state)
    if args.cache_dir:
        cache_sources(api, result["files"], args.cache_dir)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.state.with_suffix(".tmp")
    temporary.write_text(json.dumps(result))
    temporary.replace(args.state)
    page = args.wiki / "topics/source-coverage.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    temporary = page.with_suffix(".tmp")
    temporary.write_text(coverage_page(args.root_folder, result))
    temporary.replace(page)
    print(json.dumps({k: v for k, v in result.items() if k not in {"files", "pending", "revision_dates"}}))


if __name__ == "__main__":
    main()
