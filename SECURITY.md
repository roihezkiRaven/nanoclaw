# PersonalAssist security

This is a public source repository for a personal-assistant deployment. It must
not contain live credentials, owner identities, chats, private knowledge,
databases, or deployment logs.

## Reporting a vulnerability

For an exploitable vulnerability or sensitive finding, contact the repository
maintainer through an established private channel. If GitHub private vulnerability
reporting is available in the repository's Security tab, use it. Do not post
secrets, raw conversations, account details, or exploit data in public issues.
Public hardening suggestions can use the security-hardening issue form with
redacted examples.

## Trust boundaries

The owner approves privileged actions. Agents execute in containers with scoped
mounts and tools; host integrations manage credentials. Timeless and WhatsApp
knowledge retain separate source and publication boundaries. Generated knowledge
and retrieved source content are untrusted input, not operating instructions.

The runtime threat model is documented in
[the security model](docs/security/SECURITY.md) and
[the isolation model](docs/architecture/isolation-model.md). Application-specific
controls and limitations are in [operations](docs/personal-assistant/operations.md)
and [approval boundaries](docs/personal-assistant/autonomy.md). Verify behavior
against this repository and deployment rather than assuming upstream defaults.
