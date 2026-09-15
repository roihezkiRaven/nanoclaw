#!/usr/bin/env python3
"""Host-only HTTP broker for the NanoClaw Google Drive helper."""

import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from googleapiclient.http import MediaIoBaseUpload

import gdrive_assistant as drive

MAX_BYTES = 1_000_000
MAX_TREE_ITEMS = 200


def writer_parent(api, requested_parent):
    root = drive.env_value("GOOGLE_WRITER_FOLDER_ID")
    if not root:
        raise ValueError("writer folder is not configured")
    current = str(requested_parent or root)
    for _ in range(10):
        if current == root:
            return current
        meta = api.files().get(fileId=current, fields="mimeType,parents", supportsAllDrives=True).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            raise ValueError("parent_id must be a folder inside the writer folder")
        parents = meta.get("parents") or []
        if len(parents) != 1:
            break
        current = parents[0]
    raise ValueError("parent_id is outside the writer folder")


def folder_tree(api, root_id, max_depth, max_items):
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", root_id):
        raise ValueError("folder_id is invalid")
    max_depth = min(max(int(max_depth), 0), 4)
    max_items = min(max(int(max_items), 1), MAX_TREE_ITEMS)
    queue = [(root_id, "", 0)]
    files = []
    while queue and len(files) < max_items:
        parent_id, prefix, depth = queue.pop(0)
        page_token = None
        while len(files) < max_items:
            result = api.files().list(
                q=f"trashed = false and '{parent_id}' in parents",
                pageSize=min(50, max_items - len(files)),
                pageToken=page_token,
                orderBy="folder,name",
                fields="nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,size)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for item in result.get("files", []):
                item["path"] = f"{prefix}/{item['name']}" if prefix else item["name"]
                files.append(item)
                if item.get("mimeType") == "application/vnd.google-apps.folder" and depth < max_depth:
                    queue.append((item["id"], item["path"], depth + 1))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
    return {"ok": True, "files": files, "truncated": bool(queue) or len(files) == max_items}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > MAX_BYTES:
                raise ValueError("request too large")
            body = json.loads(self.rfile.read(size))
            result = self.process(body)
            self.reply(200, result)
        except Exception as exc:
            self.reply(400, {"ok": False, "error": str(exc)})

    def process(self, body):
        action = body.get("action")
        if action == "search":
            query = str(body.get("query", "")).strip()
            if not query:
                raise ValueError("query is required")
            escaped = query.replace("'", "\\'")
            files = drive.service("reader", False).files().list(
                q=f"trashed = false and (name contains '{escaped}' or fullText contains '{escaped}')",
                pageSize=min(max(int(body.get("limit", 10)), 1), 50),
                orderBy="modifiedTime desc",
                fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get("files", [])
            return {"ok": True, "files": files}
        if action == "read":
            file_id = str(body.get("file_id", "")).strip()
            if not file_id:
                raise ValueError("file_id is required")
            api = drive.service("reader", False)
            meta = api.files().get(fileId=file_id, fields="name,mimeType", supportsAllDrives=True).execute()
            if meta["mimeType"] == "application/vnd.google-apps.document":
                data = api.files().export_media(fileId=file_id, mimeType="text/plain").execute()
            elif meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
                data = api.files().export_media(fileId=file_id, mimeType="text/csv").execute()
            elif meta["mimeType"].startswith("text/") or meta["mimeType"] in {"application/json", "text/csv"}:
                data = api.files().get_media(fileId=file_id).execute()
            else:
                raise ValueError("unsupported MIME type: " + meta["mimeType"])
            return {"ok": True, "name": meta["name"], "text": data[:MAX_BYTES].decode("utf-8", "replace")}
        if action == "list":
            folder_id = str(body.get("folder_id", "")).strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", folder_id):
                raise ValueError("folder_id is invalid")
            files = drive.service("reader", False).files().list(
                q=f"trashed = false and '{folder_id}' in parents",
                pageSize=min(max(int(body.get("limit", 50)), 1), 50),
                orderBy="folder,name",
                fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get("files", [])
            return {"ok": True, "files": files}
        if action == "tree":
            return folder_tree(
                drive.service("reader", False),
                str(body.get("folder_id", "")).strip(),
                body.get("max_depth", 2),
                body.get("limit", 100),
            )
        if action == "write":
            name = str(body.get("name", ""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,120}", name):
                raise ValueError("name must be a simple filename")
            api = drive.service("writer", False)
            folder_id = writer_parent(api, body.get("parent_id"))
            media = MediaIoBaseUpload(io.BytesIO(str(body.get("text", "")).encode()), mimetype="text/plain", resumable=False)
            file = api.files().create(
                body={"name": name, "parents": [folder_id], "mimeType": "text/plain"},
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            ).execute()
            return {"ok": True, "file": file}
        if action == "mkdir":
            name = str(body.get("name", ""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,120}", name):
                raise ValueError("name must be a simple folder name")
            api = drive.service("writer", False)
            folder_id = writer_parent(api, body.get("parent_id"))
            folder = api.files().create(
                body={"name": name, "parents": [folder_id], "mimeType": "application/vnd.google-apps.folder"},
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            ).execute()
            return {"ok": True, "folder": folder}
        if action == "calendar":
            now = datetime.now(timezone.utc)
            time_min = str(body.get("start") or now.isoformat().replace("+00:00", "Z"))
            time_max = str(body.get("end") or (now + timedelta(days=7)).isoformat().replace("+00:00", "Z"))
            limit = min(max(int(body.get("limit", 20)), 1), 50)
            api = drive.service("calendar", False)
            calendars = api.calendarList().list(fields="items(id,summary,primary)").execute().get("items", [])
            events = []
            for calendar in calendars:
                result = api.events().list(
                    calendarId=calendar["id"],
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=limit,
                    singleEvents=True,
                    orderBy="startTime",
                    fields="items(id,summary,start,end,location,htmlLink,status)",
                ).execute()
                for event in result.get("items", []):
                    event["calendar"] = {"id": calendar["id"], "summary": calendar.get("summary"), "primary": calendar.get("primary", False)}
                    events.append(event)
            events.sort(key=lambda event: event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", ""))
            events = events[:limit]
            return {"ok": True, "events": events}
        raise ValueError("action must be search, list, tree, read, write, mkdir, or calendar")

    def reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("GDRIVE_BROKER_HOST", "172.17.0.1"), 8765), Handler).serve_forever()
