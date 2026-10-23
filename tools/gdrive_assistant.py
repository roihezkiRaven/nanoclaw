#!/usr/bin/env python3
"""Read all Drive files or create text outputs in the configured writer folder."""

import argparse
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

ROOT = Path("/home/assistant/nanoclaw")
CONFIG = ROOT / "config" / "google"
SCOPES = {
    "reader": ["https://www.googleapis.com/auth/drive.readonly"],
    "writer": ["https://www.googleapis.com/auth/drive.file"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
}
CLIENTS = {
    "reader": CONFIG / "reader-client.json",
    "writer": CONFIG / "writer-client.json",
    "calendar": CONFIG / "reader-client.json",
}
TOKENS = {
    "reader": CONFIG / "reader-token.json",
    "writer": CONFIG / "writer-token.json",
    "calendar": CONFIG / "calendar-token.json",
}


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def save_token(token_path: Path, content: str) -> None:
    """Publish a complete private token atomically for concurrent readers."""
    with tempfile.TemporaryDirectory(dir=token_path.parent, prefix=".oauth-") as directory:
        temporary = Path(directory) / "token.json"
        temporary.write_text(content)
        temporary.chmod(0o600)
        temporary.replace(token_path)


def service(mode: str, authorize: bool):
    token_path = TOKENS[mode]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES[mode]) if token_path.exists() and not authorize else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            if exc.retryable:
                raise
            raise RuntimeError(
                f"{mode} Google authorization was rejected. Check Google Auth Platform > "
                "Audience: external apps in Testing expire after 7 days. Set the OAuth "
                f"project to In production, then run {mode} auth for a fresh offline grant."
            ) from exc
    if not creds or not creds.valid:
        if not authorize:
            raise RuntimeError(f"{mode} authorization is required; run auth first")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENTS[mode], SCOPES[mode])
        creds = flow.run_local_server(
            host="127.0.0.1",
            port=int(os.environ.get("GDRIVE_OAUTH_PORT", "8080")),
            open_browser=False,
            access_type="offline",
            prompt="consent",
        )
    save_token(token_path, creds.to_json())
    api = "calendar" if mode == "calendar" else "drive"
    return build(api, "v3", credentials=creds, cache_discovery=False)


def auth(mode: str) -> None:
    service(mode, authorize=True)
    print(json.dumps({"ok": True, "mode": mode, "scope": SCOPES[mode][0]}))


def check(mode: str) -> None:
    """Refresh and validate one configured OAuth credential without writing data."""
    service(mode, authorize=False)
    print(json.dumps({"ok": True, "mode": mode, "scope": SCOPES[mode][0]}))


def search(query: str, limit: int) -> None:
    drive = service("reader", authorize=False)
    escaped = query.replace("'", "\\'")
    result = drive.files().list(
        q=f"trashed = false and (name contains '{escaped}' or fullText contains '{escaped}')",
        pageSize=limit,
        orderBy="modifiedTime desc",
        fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
    ).execute()
    print(json.dumps(result.get("files", []), indent=2))


def list_folder(folder_id: str, limit: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", folder_id):
        raise RuntimeError("folder_id is invalid")
    drive = service("reader", authorize=False)
    result = drive.files().list(
        q=f"trashed = false and '{folder_id}' in parents",
        pageSize=limit,
        orderBy="folder,name",
        fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    print(json.dumps(result.get("files", []), indent=2))


def read(file_id: str) -> None:
    drive = service("reader", authorize=False)
    meta = drive.files().get(fileId=file_id, fields="name,mimeType").execute()
    mime = meta["mimeType"]
    if mime == "application/vnd.google-apps.document":
        data = drive.files().export_media(fileId=file_id, mimeType="text/plain").execute()
    elif mime == "application/vnd.google-apps.spreadsheet":
        data = drive.files().export_media(fileId=file_id, mimeType="text/csv").execute()
    elif mime.startswith("text/") or mime in {"application/json", "text/csv"}:
        data = drive.files().get_media(fileId=file_id).execute()
    else:
        raise RuntimeError(f"Unsupported MIME type for text extraction: {mime}")
    if len(data) > 1_000_000:
        raise RuntimeError("Content exceeds 1 MB; use broker read with offset/version continuation")
    sys.stdout.buffer.write(data)


MAX_VIDEO_BYTES = 256 * 1024 * 1024
VIDEO_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm", "video/x-msvideo": ".avi"}


class BoundedVideoFile:
    """Enforce the byte cap before each downloader write, including oversized chunks."""

    def __init__(self, output):
        self.output = output
        self.size = 0

    def write(self, data):
        if self.size + len(data) > MAX_VIDEO_BYTES:
            raise RuntimeError("video exceeds 256 MB while downloading")
        written = self.output.write(data)
        self.size += written
        return written


def download_video(file_id: str, directory: str) -> dict:
    """Download exactly one video to a host-created private staging directory."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", file_id):
        raise RuntimeError("file_id is invalid")
    api = service("reader", authorize=False)
    fields = "id,name,mimeType,size,version,modifiedTime,trashed"
    meta = api.files().get(fileId=file_id, fields=fields, supportsAllDrives=True).execute()
    extension = VIDEO_TYPES.get(meta.get("mimeType"))
    if not extension or meta.get("trashed"):
        raise RuntimeError("selected file must be an MP4, MOV, WebM, or AVI video")
    if not meta.get("size") or not 0 < int(meta["size"]) <= MAX_VIDEO_BYTES:
        raise RuntimeError("video size must be known and no larger than 256 MB")
    destination = Path(directory) / ("selected-video" + extension)
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            destination.chmod(0o600)
            download = MediaIoBaseDownload(BoundedVideoFile(output), api.files().get_media(
                fileId=file_id, supportsAllDrives=True), chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = download.next_chunk(num_retries=2)
        current = api.files().get(fileId=file_id, fields=fields, supportsAllDrives=True).execute()
        if current != meta or destination.stat().st_size != int(meta["size"]):
            raise RuntimeError("selected video changed during download; select it again")
        return {"path": str(destination), "file_id": file_id, "name": meta["name"],
                "version": meta.get("version"), "modified_time": meta.get("modifiedTime")}
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def writer_parent(api, requested_parent: str | None) -> str:
    """Validate the entire folder ancestry, retaining the requested destination."""
    root = env_value("GOOGLE_WRITER_FOLDER_ID")
    requested = root if requested_parent is None else requested_parent
    if not root:
        raise ValueError("writer folder is not configured")
    current, seen = requested, set()
    while True:
        meta = writer_folder(api, current)
        if current in seen:
            break
        if current == root:
            return requested
        seen.add(current)
        parents = meta.get("parents", [])
        if len(parents) != 1:
            break
        current = parents[0]
    raise ValueError("parent_id is outside the writer folder or has cyclic ancestry")


def writer_folder(api, folder_id):
    """Reject malformed IDs, deleted folders and unsupported destinations."""
    if not isinstance(folder_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", folder_id):
        raise ValueError("parent_id must be a valid folder ID")
    meta = api.files().get(fileId=folder_id, fields="mimeType,parents,trashed", supportsAllDrives=True).execute()
    if meta.get("mimeType") != "application/vnd.google-apps.folder" or meta.get("trashed") is not False:
        raise ValueError("parent_id must be a non-deleted folder inside the writer folder")
    return meta


def verify_created_parent(api, created, expected_parent):
    """Read persisted placement; never report a misplaced create as successful."""
    try:
        actual = api.files().get(
            fileId=created["id"], fields="id,name,webViewLink,parents,trashed,modifiedTime", supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"Created file {created['id']} but placement verification failed; inspect it before retrying") from exc
    if actual.get("trashed") is not False or actual.get("parents") != [expected_parent]:
        raise RuntimeError(f"Created file {created['id']} has unexpected placement; inspect it before retrying")
    return actual


def write(name: str, text: str, parent_id: str | None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,120}", name):
        raise RuntimeError("name must be a simple filename")
    drive = service("writer", authorize=False)
    folder_id = writer_parent(service("reader", authorize=False), parent_id)
    media = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain", resumable=False)
    created = drive.files().create(
        body={"name": name, "parents": [folder_id], "mimeType": "text/plain"},
        media_body=media,
        fields="id,name,webViewLink,parents",
    ).execute()
    print(json.dumps(verify_created_parent(drive, created, folder_id)))


def mkdir(name: str, parent_id: str | None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,120}", name):
        raise RuntimeError("name must be a simple folder name")
    drive = service("writer", authorize=False)
    folder_id = writer_parent(service("reader", authorize=False), parent_id)
    created = drive.files().create(
        body={"name": name, "parents": [folder_id], "mimeType": "application/vnd.google-apps.folder"},
        fields="id,name,webViewLink,parents",
        supportsAllDrives=True,
    ).execute()
    print(json.dumps(verify_created_parent(drive, created, folder_id)))


def calendar_events(start: str | None, end: str | None, limit: int) -> None:
    now = datetime.now(timezone.utc)
    time_min = start or now.isoformat().replace("+00:00", "Z")
    time_max = end or (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    api = service("calendar", authorize=False)
    calendars = api.calendarList().list(fields="items(id,summary,primary)").execute().get("items", [])
    events = []
    for calendar in calendars:
        result = api.events().list(
            calendarId=calendar["id"],
            timeMin=time_min,
            timeMax=time_max,
            maxResults=min(max(limit, 1), 50),
            singleEvents=True,
            orderBy="startTime",
            fields="items(id,summary,start,end,location,htmlLink,status,attendees(self,responseStatus))",
        ).execute()
        for event in result.get("items", []):
            event["calendar"] = {"id": calendar["id"], "summary": calendar.get("summary"), "primary": calendar.get("primary", False)}
            events.append(event)
    events.sort(key=lambda event: event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", ""))
    print(json.dumps(events[: min(max(limit, 1), 50)], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("reader", "writer", "calendar"))
    parser.add_argument("action", choices=("auth", "check", "search", "list", "read", "write", "mkdir", "events", "download-video"))
    parser.add_argument("--output-dir")
    parser.add_argument("--query")
    parser.add_argument("--file-id")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--name")
    parser.add_argument("--text")
    parser.add_argument("--text-file")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--parent-id")
    args = parser.parse_args()
    if args.action == "auth":
        auth(args.mode)
    elif args.action == "check":
        check(args.mode)
    elif args.action == "search":
        if args.mode != "reader" or not args.query:
            parser.error("reader search requires --query")
        search(args.query, min(max(args.limit, 1), 50))
    elif args.action == "download-video":
        if args.mode != "reader" or not args.file_id or not args.output_dir:
            parser.error("reader download-video requires --file-id and --output-dir")
        print(json.dumps(download_video(args.file_id, args.output_dir)))
    elif args.action == "read":
        if args.mode != "reader" or not args.file_id:
            parser.error("reader read requires --file-id")
        read(args.file_id)
    elif args.action == "list":
        if args.mode != "reader" or not args.file_id:
            parser.error("reader list requires --file-id")
        list_folder(args.file_id, min(max(args.limit, 1), 50))
    elif args.action == "events":
        if args.mode != "calendar":
            parser.error("calendar events requires calendar mode")
        calendar_events(args.start, args.end, args.limit)
    elif args.action == "mkdir":
        if args.mode != "writer" or not args.name:
            parser.error("writer mkdir requires --name")
        mkdir(args.name, args.parent_id)
    else:
        if args.mode != "writer" or not args.name or (args.text is None and not args.text_file):
            parser.error("writer write requires --name and --text")
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8")
        else:
            text = args.text
        write(args.name, text, args.parent_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
