#!/usr/bin/env python3
"""Validate a frozen publication, with safe link repair and explicit synthesis fallback."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from build_knowledge_navigation import build as build_navigation

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("knowledge_validator", ROOT / "scripts/validate-knowledge-wiki.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    temporary.replace(path)


def copy_snapshot(source, stage, scope):
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if not path.is_file() or not validator.in_scope(relative, scope):
            continue
        if path.suffix != ".md" and relative.as_posix() not in {"ingestion.json", "whatsapp-ingestion.json"}:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Snapshot path escapes wiki: {relative}")
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def corrected_weekly_target(stage, path, target):
    original = (path.parent / target).resolve()
    corrected = (path.parent / ".." / target).resolve()
    expected = (stage / "whatsapp" / target.split("/")[1] / target.split("/")[2]).resolve()
    if original.exists() or corrected != expected or not corrected.is_relative_to(stage.resolve()) or not corrected.is_file():
        return None
    meta = validator.frontmatter(corrected.read_text()) or {}
    jid = meta.get("group_jid", "").strip("\"'")
    if corrected.parent.name == "brain" or meta.get("type") == "coverage-status" or not re.fullmatch(r"\d+(?:-\d+)?@g\.us", jid):
        return None
    return "../" + target


def repair_weekly_links(stage):
    repairs = []
    for path in (stage / "whatsapp/brain/weekly").glob("*.md"):
        text = path.read_text()
        if (validator.frontmatter(text) or {}).get("type") not in {"whatsapp-weekly", "weekly-synthesis"}:
            continue
        def replace(match):
            corrected = corrected_weekly_target(stage, path, match[2])
            if corrected is None:
                return match[0]
            repairs.append({"path": path.relative_to(stage).as_posix(), "from": match[2], "to": corrected})
            return match[1] + corrected
        path.write_text(re.sub(r'([("\'])((?:\.\./)[a-z0-9-]+/\d{4}-\d{2}-\d{2}\.md)', replace, text))
    return repairs


def restore_synthesis(stage, cache, scope):
    prefix = "whatsapp/brain/" if scope == "whatsapp" else "brain/"
    index = "whatsapp/index.md" if scope == "whatsapp" else "index.md"
    if not cache.is_file():
        raise ValueError("Invalid candidate; no last-good publication exists")
    with zipfile.ZipFile(cache) as archive:
        metadata = json.loads(archive.read("publication.json"))
        if metadata.get("scope") != scope or metadata.get("mode") not in {"healthy", "repaired", "degraded"}:
            raise ValueError("Invalid last-good publication metadata")
        members = [m for m in archive.infolist() if m.filename.startswith(prefix) or m.filename == index]
        if not any(m.filename.startswith(prefix) for m in members):
            raise ValueError("Last-good publication has no synthesis")
        shutil.rmtree(stage / prefix, ignore_errors=True)
        for member in members:
            path = stage / member.filename
            if not path.resolve().is_relative_to(stage.resolve()) or ".." in Path(member.filename).parts:
                raise ValueError("Last-good archive path escapes snapshot")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(member))
    return metadata["brain_snapshot_at"]


def cache_publication(stage, state, status):
    temporary = state / "last-good.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in stage.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())
        archive.writestr("publication.json", json.dumps(status))
    temporary.chmod(0o600)
    temporary.replace(state / "last-good.zip")


def preserve_rejected(stage, state):
    temporary = state / "rejected.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in stage.rglob("*.md"):
            archive.write(path, path.relative_to(stage).as_posix())
    temporary.chmod(0o600)
    temporary.replace(state / "rejected.zip")


def apply_safe_repairs(source, stage, state, originals, repairs):
    for relative in sorted({item["path"] for item in repairs}):
        path = source / relative
        observed = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if observed != originals.get(relative):
            continue
        backup = state / "repair-originals" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not backup.exists():
            shutil.copyfile(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".publication-tmp")
        shutil.copyfile(stage / relative, temporary)
        temporary.replace(path)


def retained_knowledge_errors(stage, state):
    cache = state / 'last-good.zip'
    if not cache.exists():
        return []
    with zipfile.ZipFile(cache) as archive:
        previous = [name for name in archive.namelist() if name.endswith('.md')]
        reviewed = json.loads(archive.read('ingestion.json')).get('files', {}) if 'ingestion.json' in archive.namelist() else {}
    errors = [f'{name}: previously published knowledge disappeared; retain a redirect or reconcile it explicitly'
              for name in previous if not (stage / name).is_file()]
    current = json.loads((stage / 'ingestion.json').read_text()).get('files', {}) if (stage / 'ingestion.json').exists() else {}
    errors += [f'{id}: previously reviewed source assessment was removed or downgraded' for id, item in reviewed.items()
               if item.get('consolidation_version') == 2 and current.get(id, {}).get('consolidation_version') != 2]
    errors += retained_assessment_errors(stage, reviewed, current)
    return errors


def retained_assessment_errors(stage, reviewed, current):
    errors = []
    for id, item in reviewed.items():
        accepted = {a['project'] for a in item.get('project_assessments', []) if a.get('outcome') == 'updated'}
        present = {a['project'] for a in current.get(id, {}).get('project_assessments', []) if a.get('outcome') == 'updated'}
        errors += [f'{id}: accepted project fact assessment was downgraded: {p}' for p in accepted - present]
    return errors


def prepare(source, stage, state, scope, navigation=False, source_cache=None):
    copy_snapshot(source, stage, scope)
    originals = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob("*.md")}
    if not originals:
        raise ValueError("No knowledge pages available for publication")
    navigation_paths = build_navigation(stage, scope, validator.frontmatter) if navigation else []
    repairs = repair_weekly_links(stage) if scope == "whatsapp" else []
    errors = validator.validate(stage, scope, source_cache) + retained_knowledge_errors(stage, state)
    mode = "repaired" if repairs else "healthy"
    now = datetime.now(timezone.utc).isoformat()
    brain_time = now
    if errors:
        preserve_rejected(stage, state)
        brain_time = restore_synthesis(stage, state / "last-good.zip", scope)
        remaining = validator.validate(stage, scope, source_cache) + retained_knowledge_errors(stage, state)
        if remaining:
            raise ValueError("Fallback cannot make source data safe: " + "; ".join(remaining))
        mode = "degraded"
    return {"scope": scope, "mode": mode, "published_at": now, "brain_snapshot_at": brain_time,
            "repairs": repairs, "navigation_paths": navigation_paths, "validation_errors": errors, "pages": len(list(stage.rglob("*.md")))}, originals


def publication_coverage(state):
    path = state / 'source-inventory.json'
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    pending = value.get('pending', [])
    return {'source_inventory': {key: value.get(key) for key in
            ['checked_at', 'complete', 'eligible_sources', 'pending_sources']},
            'oldest_pending_revision': min((p['modifiedTime'] for p in pending), default=None),
            'oldest_pending_since': min((p['pending_since'] for p in pending if p.get('pending_since')), default=None)}


def promote_snapshot(stage, destination):
    """Expose only the validated, successfully uploaded snapshot to assistant readers."""
    destination.mkdir(parents=True, exist_ok=True)
    paths = sorted((p for p in stage.rglob('*') if p.is_file()),
                   key=lambda p: (p.name == 'index.md', p.relative_to(stage).as_posix()))
    targets = [(path, destination / path.relative_to(stage)) for path in paths]
    if any(not target.resolve().is_relative_to(destination.resolve()) for _, target in targets):
        raise ValueError('Canonical destination path escapes knowledge base')
    for path, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.accepted-tmp')
        shutil.copyfile(path, temporary)
        temporary.replace(target)


def accept_publication(source, stage, state, originals, status, destination=None):
    if destination is not None:
        promote_snapshot(stage, destination)
    cache_publication(stage, state, status)
    if status['mode'] != 'degraded':
        repairs = status['repairs'] + [{'path': p} for p in status['navigation_paths']]
        apply_safe_repairs(source, stage, state, originals, repairs)
    atomic_json(state / 'status.json', status)


def publish(source, state, scope, upload, navigation=False, source_cache=None, destination=None):
    source, state = source.resolve(), state.resolve()
    if not source.is_dir() or state.is_relative_to(source):
        raise ValueError("Publication state must be outside an existing wiki")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    with (state / "publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="candidate-", dir=state) as directory:
            stage = Path(directory)
            try:
                status, originals = prepare(source, stage, state, scope, navigation, source_cache)
                status.update(publication_coverage(state))
                upload(stage)
                accept_publication(source, stage, state, originals, status, destination)
                return status
            except Exception as error:
                atomic_json(state / "status.json", {"scope": scope, "mode": "failed", "error": str(error)})
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--scope", choices=("timeless", "whatsapp", "engineering"), required=True)
    parser.add_argument("--drive-folder", required=True)
    parser.add_argument("--sync-state", type=Path, required=True)
    parser.add_argument("--build-navigation", action="store_true")
    parser.add_argument("--source-cache", type=Path)
    parser.add_argument("--canonical-destination", type=Path)
    args = parser.parse_args()
    def upload(stage):
        subprocess.run([sys.executable, str(ROOT / "tools/sync_knowledge_wiki.py"), "--source", str(stage),
                        "--drive-folder", args.drive_folder, "--drive-links", "--state-file", str(args.sync_state)], check=True, timeout=900)
    print(json.dumps(publish(args.source, args.state_dir, args.scope, upload, args.build_navigation, args.source_cache, args.canonical_destination)))


if __name__ == "__main__":
    main()
