#!/usr/bin/env python3
"""Forward the prepared agent browser to this Mac over SSH, on loopback only."""
import datetime as dt
import json
import re
import socketserver
import subprocess
import threading
import webbrowser

HOST = "assistant@157.180.44.97"
PORT = 4848
READ_STATE = "cat /home/assistant/nanoclaw/groups/personal-assistant/work/browser-handoff.json"
STREAM = "const s=require('net').connect(PORT,'127.0.0.1');process.stdin.pipe(s);s.pipe(process.stdout);s.on('error',()=>process.exit(1));s.on('close',()=>process.exit(0));"


def remote(*command):
    return subprocess.check_output(["ssh", "-o", "BatchMode=yes", HOST, *command], text=True, timeout=20)


def container_for(state, listing):
    hostname = state.get("container_hostname", "")
    if not re.fullmatch(r"[0-9a-f]{12,64}", hostname):
        raise ValueError("Invalid browser handoff identity")
    for line in listing.splitlines():
        identity, name = line.split()
        if (identity.startswith(hostname) or hostname.startswith(identity)) and re.fullmatch(r"ncl-fc17183a-sess-[a-z0-9-]+", name):
            return name
    raise ValueError("Browser session expired. Ask the agent to prepare a new handoff in Telegram.")


def allowed_headers(data):
    headers = {}
    for line in data.decode("latin1").split("\r\n")[1:]:
        key, separator, value = line.partition(":")
        if separator:
            headers[key.lower()] = value.strip()
    hosts = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
    origins = {f"http://{host}" for host in hosts}
    return (headers.get("host") in hosts
            and headers.get("origin", "") in origins | {""}
            and headers.get("sec-fetch-site", "") != "cross-site")


class Bridge(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    state = json.loads(remote(READ_STATE))
    if state.get("provider") not in ("tavily", "gemini") or state.get("status") != "waiting_human":
        raise ValueError("Ask the agent in Telegram to prepare the approved provider handoff first.")
    expiry = dt.datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00"))
    remaining = (expiry - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if not 0 < remaining <= 1800:
        raise ValueError("Handoff expired. Ask the agent to prepare it again.")
    listing = remote("docker ps --filter label=nanoclaw-group-folder=personal-assistant --format '{{.ID}} {{.Names}}'")
    container = container_for(state, listing)
    browser_session = f"signup-{state['provider']}"
    if state.get('browser_session') != browser_session:
        raise ValueError('Unexpected browser session')
    stream_port = int(remote(f"docker exec {container} cat /home/node/.agent-browser/{browser_session}.stream").strip())
    if not 1024 <= stream_port <= 65535:
        raise ValueError('Invalid stream port')
    processes = set()
    lock = threading.Lock()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            first = b""
            self.request.settimeout(15)
            while b"\r\n\r\n" not in first and len(first) <= 16384:
                chunk = self.request.recv(4096)
                if not chunk:
                    return
                first += chunk
            if len(first) > 16384 or not allowed_headers(first.split(b"\r\n\r\n")[0]):
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            self.request.settimeout(None)
            target_port = PORT
            path = first.split(b' ', 2)[1]
            if path == f'/api/session/{stream_port}/stream'.encode():
                target_port = stream_port
                first = first.replace(path, b'/', 1)
            script = STREAM.replace('PORT', str(target_port))
            command = f"docker exec -i {container} node -e \"{script}\""
            process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", HOST, command],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            with lock:
                processes.add(process)

            def send():
                try:
                    process.stdin.write(first)
                    process.stdin.flush()
                    while chunk := self.request.recv(65536):
                        process.stdin.write(chunk)
                        process.stdin.flush()
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass

            threading.Thread(target=send, daemon=True).start()
            try:
                while chunk := process.stdout.read1(65536):
                    self.request.sendall(chunk)
            except OSError:
                pass
            finally:
                process.terminate()
                with lock:
                    processes.discard(process)

    with Bridge(("127.0.0.1", PORT), Handler) as server:
        timer = threading.Timer(remaining, server.shutdown)
        timer.daemon = True
        timer.start()
        print(f"Agent browser: http://localhost:{PORT} — closes when this handoff expires.", flush=True)
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            server.serve_forever()
        finally:
            timer.cancel()
            with lock:
                for process in processes:
                    process.terminate()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Browser handoff unavailable: {type(error).__name__}. Ask the agent to prepare or refresh it in Telegram.")
        raise SystemExit(1)
