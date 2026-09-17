## Antigravity worker (`run_agy`)

Use `run_agy` as a session-scoped sub-agent for research, multimodal interpretation, drafting, and file work. It runs the owner-authenticated `agy` CLI on the host with the current session workspace mounted. AGY may inspect and edit files in that workspace, but host credentials, Drive mounts, WhatsApp credentials, GitHub credentials, NanoClaw databases, and other sessions are not mounted. For privileged NanoClaw operations, use the normal NanoClaw tools.

The prompt is sent to Google through the Antigravity subscription session. Do not include secrets unless the user explicitly asked for that data to be processed. Prefer `gemini-3.7-flash-medium` or another explicit model when the task needs a predictable model. The result includes usage metadata.

## Video worker (`run_agy_media`)

Use `run_agy_media` only when the user explicitly selected a video attachment in the current session. Pass its `/workspace/inbox/...` path and a focused analysis prompt. The host verifies that the file is a regular, non-symlink `.mp4`, `.mov`, `.webm`, or `.avi` file no larger than 256 MB, copies only that file into a temporary AGY workspace, and removes the copy after the run. It does not mount Drive, NanoClaw databases, or credentials.
