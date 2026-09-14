---
name: github-readonly
description: Inspect configured GitHub repositories, issues, pull requests, and workflow status without making changes.
---

# GitHub Read-Only

Use this skill when the owner asks about repositories, issues, pull requests, checks, or GitHub status.

Run GitHub commands only through the restricted wrapper:

```bash
/home/node/.agents/skills/github-readonly/ghr issue list --repo OWNER/REPO
/home/node/.agents/skills/github-readonly/ghr pr status --repo OWNER/REPO
/home/node/.agents/skills/github-readonly/ghr pr checks NUMBER --repo OWNER/REPO
/home/node/.agents/skills/github-readonly/ghr repo view OWNER/REPO
```

- This integration is strictly read-only. Do not create, edit, close, merge, comment on, label, or otherwise modify GitHub resources.
- Do not use `gh` directly; use `ghr` so the restricted authentication path and command guard apply.
- Report the repository and data source used. Never request, reveal, or alter credentials.
