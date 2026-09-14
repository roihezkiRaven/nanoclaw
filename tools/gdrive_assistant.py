#!/usr/bin/env python3
"""Read all Drive files or create text outputs in the configured writer folder."""

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

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


def service(mode: str, authorize: bool):
    token_path = TOKENS[mode]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES[mode]) if token_path.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not authorize:
            raise RuntimeError(f"{mode} authorization is required; run auth first")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENTS[mode], SCOPES[mode])
        creds = flow.run_local_server(
            host="127.0.0.1",
            port=int(os.environ.get("GDRIVE_OAUTH_PORT", "8080")),
            open_browser=False,
        )
    token_path.write_text(creds.to_json())
    token_path.chmod(0o600)
    api = "calendar" if mode == "calendar" else "drive"
    return build(api, "v3", credentials=creds, cache_discovery=False)


def auth(mode: str) -> None:
    service(mode, authorize=True)
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
    sys.stdout.buffer.write(data[:1_000_000])


def write(name: str, text: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,120}", name):
        raise RuntimeError("name must be a simple filename")
    folder_id = env_value("GOOGLE_WRITER_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("GOOGLE_WRITER_FOLDER_ID is not configured")
    drive = service("writer", authorize=False)
    media = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain", resumable=False)
    created = drive.files().create(
        body={"name": name, "parents": [folder_id], "mimeType": "text/plain"},
        media_body=media,
        fields="id,name,webViewLink",
    ).execute()
    print(json.dumps(created))


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
            fields="items(id,summary,start,end,location,htmlLink,status)",
        ).execute()
        for event in result.get("items", []):
            event["calendar"] = {"id": calendar["id"], "summary": calendar.get("summary"), "primary": calendar.get("primary", False)}
            events.append(event)
    events.sort(key=lambda event: event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", ""))
    print(json.dumps(events[: min(max(limit, 1), 50)], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("reader", "writer", "calendar"))
    parser.add_argument("action", choices=("auth", "search", "read", "write", "events"))
    parser.add_argument("--query")
    parser.add_argument("--file-id")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--name")
    parser.add_argument("--text")
    parser.add_argument("--text-file")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    if args.action == "auth":
        auth(args.mode)
    elif args.action == "search":
        if args.mode != "reader" or not args.query:
            parser.error("reader search requires --query")
        search(args.query, min(max(args.limit, 1), 50))
    elif args.action == "read":
        if args.mode != "reader" or not args.file_id:
            parser.error("reader read requires --file-id")
        read(args.file_id)
    elif args.action == "events":
        if args.mode != "calendar":
            parser.error("calendar events requires calendar mode")
        calendar_events(args.start, args.end, args.limit)
    else:
        if args.mode != "writer" or not args.name or (args.text is None and not args.text_file):
            parser.error("writer write requires --name and --text")
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8")
        else:
            text = args.text
        write(args.name, text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
