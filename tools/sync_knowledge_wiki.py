#!/usr/bin/env python3
"""Mirror the local personal knowledge wiki into its dedicated Drive folder."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from gdrive_assistant import service, writer_parent
from wiki_links import exported_text
from googleapiclient.http import MediaFileUpload


def local_files(root: Path, excluded: set[str], included: set[str]) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix == ".md" and not path.name.startswith(".") and not (set(path.relative_to(root).parts) & excluded)
        and (not included or path.relative_to(root).parts[0] in included)
    )


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
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError(f"invalid sync state: {path}")
    return value


def save_state(path: Path, state: dict[str, str]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n")
    temporary.replace(path)



def page_folder(drive, target, relative, folders):
    parent = Path('.')
    for part in relative.parts[:-1]:
        parent /= part
        if parent not in folders:
            folders[parent] = child_folder(drive, folders[parent.parent], part)
    return folders[parent]


def register_pages(drive, target, root, paths, state, state_path):
    folders, placements = {Path('.'): target}, []
    for path in paths:
        relative = path.relative_to(root)
        parent = page_folder(drive, target, relative, folders)
        placements.append((path, parent))
        if relative.as_posix() not in state:
            body = {'name': relative.name, 'parents': [parent], 'mimeType': 'text/markdown'}
            media = MediaFileUpload(str(path), mimetype='text/markdown', resumable=False)
            state[relative.as_posix()] = drive.files().create(body=body, media_body=media, fields='id').execute()['id']
            save_state(state_path, state)
    return placements


def publish_export(drive, path, parent, root, state, directory):
    text = exported_text(path, root, state)
    file_id = state[path.relative_to(root).as_posix()]
    metadata = drive.files().get(fileId=file_id, fields='parents,md5Checksum').execute()
    current = metadata.get('parents', [])
    if parent in current and metadata.get('md5Checksum') == hashlib.md5(text.encode()).hexdigest():
        return False
    exported = Path(directory) / 'page.md'
    exported.write_text(text)
    result = drive.files().update(fileId=file_id, body={'name': path.name},
        media_body=MediaFileUpload(str(exported), mimetype='text/markdown', resumable=False),
        addParents=parent if parent not in current else None,
        removeParents=','.join(current) if parent not in current else None,
        fields='parents,md5Checksum').execute()
    if result.get('md5Checksum') != hashlib.md5(text.encode()).hexdigest() or parent not in result.get('parents', []):
        raise ValueError('Drive upload readback differs from the validated export')
    return True


def publish_drive_links(drive, target, root, paths, state, state_path):
    placements = register_pages(drive, target, root, paths, state, state_path)
    with tempfile.TemporaryDirectory(prefix='wiki-export-') as directory:
        changed = sum(publish_export(drive, path, parent, root, state, directory) for path, parent in placements)
    save_state(state_path, state)
    return changed


def publish_plain_page(drive, path, parent, file_id):
    media = MediaFileUpload(str(path), mimetype='text/markdown', resumable=False)
    if not file_id:
        body = {'name': path.name, 'parents': [parent], 'mimeType': 'text/markdown'}
        return drive.files().create(body=body, media_body=media, fields='id').execute()['id']
    metadata = drive.files().get(fileId=file_id, fields='parents,md5Checksum').execute()
    current = metadata.get('parents', [])
    if parent in current and metadata.get('md5Checksum') == hashlib.md5(path.read_bytes()).hexdigest():
        return file_id
    drive.files().update(fileId=file_id, body={'name': path.name}, media_body=media,
        addParents=parent if parent not in current else None,
        removeParents=','.join(current) if parent not in current else None).execute()
    return file_id


def publish_plain(drive, target, root, paths, state, state_path):
    folders = {Path('.'): target}
    for path in paths:
        relative = path.relative_to(root)
        parent = page_folder(drive, target, relative, folders)
        state[relative.as_posix()] = publish_plain_page(drive, path, parent, state.get(relative.as_posix()))
        save_state(state_path, state)
    save_state(state_path, state)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--drive-folder', required=True)
    parser.add_argument('--exclude-dir', action='append', default=[])
    parser.add_argument('--include-dir', action='append', default=[])
    parser.add_argument('--state-file', type=Path)
    parser.add_argument('--drive-links', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = arguments()
    root = args.source.resolve()
    if not root.is_dir():
        raise SystemExit('source must be a directory')
    drive = service('writer', authorize=False)
    target = writer_parent(service('reader', authorize=False), args.drive_folder)
    state_path = args.state_file or root / '.drive-sync.json'
    state = load_state(state_path)
    paths = local_files(root, set(args.exclude_dir), set(args.include_dir))
    publish = publish_drive_links if args.drive_links else publish_plain
    uploaded = publish(drive, target, root, paths, state, state_path)
    print(json.dumps({'synced': len(paths) if args.drive_links else len(state), 'link_format': 'drive' if args.drive_links else 'local', 'uploaded': uploaded}))


if __name__ == '__main__':
    main()
