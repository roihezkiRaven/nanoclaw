# Gemini and Antigravity workers

The owner-authorized `run_agy` worker invokes the authenticated Antigravity CLI for bounded tasks. The current session and Personal Assistant workspace are available for ordinary file work. Google Drive credentials and unrelated sessions are not passed to the worker.

`run_agy_media` handles one explicitly owner-selected attachment or Drive recording. Drive credentials remain on the host; only the downloaded media enters a private temporary workspace. The host validates the source, bounds size, preprocesses larger recordings for AGY's media reader and removes temporary files after completion. Video/audio limitations and compression must be reported; a transcript or notes summary is not a video-analysis result.

Gemini 4 Argon IDs are allowed locally, but availability depends on the authenticated account's AGY catalog. Use an available explicit model unless the owner requires Argon. A separate API/Vertex identity remains independent of Drive OAuth and the AGY worker.

See [operations](operations.md#drive-video-and-telegram-capability-development) for limits, testing and the Telegram capability patch workflow.
