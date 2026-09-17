## Antigravity worker (`run_agy`)

Use `run_agy` when a bounded secondary pass is useful: summarization, research, multimodal interpretation, or drafting. It runs the owner-authenticated `agy` CLI on the host with a temporary empty working directory. NanoClaw files, Drive credentials, WhatsApp credentials, and GitHub credentials are not mounted.

The prompt is sent to Google through the Antigravity subscription session. Do not include secrets unless the user explicitly asked for that data to be processed. Prefer `gemini-3.7-flash-medium` or another explicit model when the task needs a predictable model. The result includes usage metadata.
