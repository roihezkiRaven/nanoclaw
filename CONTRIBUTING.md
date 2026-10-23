# Working on PersonalAssist

Branch from this repository's `main` and keep each PR focused on one application,
knowledge-pipeline, or deployment concern. Search this repository's issues and
PRs before duplicating work. Changes for this personal system can include
application features, fixes, tools, skills, and deployment configuration.

## Review and validation

Explain the problem, resulting behavior, and evidence needed to review the
change. State any remaining limitations. Follow the repository PR template and
request `@claude` review when opening a PR.

Run checks appropriate to the change. Host changes use `pnpm run typecheck` and
`pnpm test`; agent-runner changes use its Bun suite. Knowledge validation changes
use `python3 scripts/validate_knowledge_wiki_test.py`. For documentation, verify
links and examples. Tests should exercise meaningful behavior.

Commit and push authorized work so source changes do not remain only on a
workstation or deployed host. A successful merge is not a deployment; use the
[deployment and update guidance](docs/personal-assistant/updates.md) and verify
the affected services separately.

## Privacy and credentials

Never commit credentials, account identities, real chats, knowledge content,
databases, runtime logs, or private recovery artifacts. Keep installation values
in ignored host configuration and use synthetic examples in tests and docs.
Review staged paths, run a secret scan, and redact diagnostic output before
posting it to this public repository. The commit hook runs Gitleaks when installed.

Report exploitable vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Engine compatibility

The application uses the NanoClaw runtime and its channel/provider registry
branches. Preserve required runtime identifiers and compatibility paths unless a
reviewed migration explicitly changes them. The runtime's historical architecture,
security, and migration references remain available in [docs/](docs/README.md).
