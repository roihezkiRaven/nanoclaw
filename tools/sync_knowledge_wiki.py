#!/usr/bin/env python3
"""Mirror the local personal knowledge wiki into its dedicated Drive folder."""

import argparse
import json
from pathlib import Path

from gdrive_assistant import service, writer_parent
from googleapiclient.http import MediaFileUpload


def local_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.name != ".drive-sync.json")


def child_folder(drive, parent_id: str, name: str) -> str:
    result = drive.files().list(
        q=f"trashed = false and '{parent_id}' in parents and name = '{name}' and mimeType = 'application/vnd.google-apps.folder'",
        pageSize=2,
        fields="files(id)",
    ).execute()
    if result.get("files"):
        return result["files"][0]["id"]
    return drive.files().create(
        body={"name": name, "parents": [parent_id], "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()["id"]


def load_state(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--drive-folder", required=True)
    args = parser.parse_args()
    root = args.source.resolve()
    if not root.is_dir():
        raise SystemExit("source must be a directory")

    drive = service("writer", authorize=False)
    target = writer_parent(drive, args.drive_folder)
    state_path = root / ".drive-sync.json"
    state = load_state(state_path)
    folders = {Path("."): target}
    for file_path in local_files(root):
        relative = file_path.relative_to(root)
        parent = Path(".")
        for part in relative.parts[:-1]:
            parent /= part
            if parent not in folders:
                folders[parent] = child_folder(drive, folders[parent.parent], part)
        media = MediaFileUpload(str(file_path), mimetype="text/markdown", resumable=False)
        body = {"name": relative.name, "parents": [folders[parent]], "mimeType": "text/markdown"}
        if relative.as_posix() in state:
            current = drive.files().get(fileId=state[relative.as_posix()], fields="parents").execute().get("parents", [])
            drive.files().update(
                fileId=state[relative.as_posix()], body={"name": relative.name}, media_body=media,
                addParents=folders[parent] if folders[parent] not in current else None,
                removeParents=",".join(current) if folders[parent] not in current else None,
            ).execute()
        else:
            state[relative.as_posix()] = drive.files().create(body=body, media_body=media, fields="id").execute()["id"]
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n")
    temporary.replace(state_path)
    print(json.dumps({"synced": len(state)}))


if __name__ == "__main__":
    main()
