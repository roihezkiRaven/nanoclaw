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
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != originals.get(relative):
            continue
        backup = state / "repair-originals" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copyfile(path, backup)
        temporary = path.with_suffix(".publication-tmp")
        shutil.copyfile(stage / relative, temporary)
        temporary.replace(path)


def prepare(source, stage, state, scope):
    copy_snapshot(source, stage, scope)
    originals = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob("*.md")}
    if not originals:
        raise ValueError("No knowledge pages available for publication")
    repairs = repair_weekly_links(stage) if scope == "whatsapp" else []
    errors = validator.validate(stage, scope)
    mode = "repaired" if repairs else "healthy"
    now = datetime.now(timezone.utc).isoformat()
    brain_time = now
    if errors:
        preserve_rejected(stage, state)
        brain_time = restore_synthesis(stage, state / "last-good.zip", scope)
        remaining = validator.validate(stage, scope)
        if remaining:
            raise ValueError("Fallback cannot make source data safe: " + "; ".join(remaining))
        mode = "degraded"
    return {"scope": scope, "mode": mode, "published_at": now, "brain_snapshot_at": brain_time,
            "repairs": repairs, "validation_errors": errors, "pages": len(list(stage.rglob("*.md")))}, originals


def publish(source, state, scope, upload):
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
                status, originals = prepare(source, stage, state, scope)
                upload(stage)
                cache_publication(stage, state, status)
                if status["mode"] != "degraded":
                    apply_safe_repairs(source, stage, state, originals, status["repairs"])
                atomic_json(state / "status.json", status)
                return status
            except Exception as error:
                atomic_json(state / "status.json", {"scope": scope, "mode": "failed", "error": str(error)})
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--scope", choices=("timeless", "whatsapp"), required=True)
    parser.add_argument("--drive-folder", required=True)
    parser.add_argument("--sync-state", type=Path, required=True)
    args = parser.parse_args()
    def upload(stage):
        subprocess.run([sys.executable, str(ROOT / "tools/sync_knowledge_wiki.py"), "--source", str(stage),
                        "--drive-folder", args.drive_folder, "--state-file", str(args.sync_state)], check=True, timeout=900)
    print(json.dumps(publish(args.source, args.state_dir, args.scope, upload)))


if __name__ == "__main__":
    main()
