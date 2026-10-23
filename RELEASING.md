# PersonalAssist changes and deployments

Routine application changes go through a branch, reviewed PR, and merge to this
repository's `main`. Describe behavior and validation in the PR. Do not bump the
inherited runtime version for documentation or branding changes.

A merge preserves reviewed source; it does not update an existing VPS or its
private configuration. Follow [updates](docs/personal-assistant/updates.md) and
[operations](docs/personal-assistant/operations.md) to deploy, validate services,
and keep rollback material. Publish knowledge only after its validation passes.

The [upstream release workflow](docs/reference/upstream-release.yml) is retained
as historical reference and is not active in this fork. A future PersonalAssist
release process must explicitly define its target, version, artifacts and approval
boundaries. The active image-verification workflows remain runtime infrastructure. Preserve the upstream MIT notice and existing attribution.

[CHANGELOG.md](CHANGELOG.md) retains inherited runtime release history. This fork's
merged PRs and commit history record subsequent application work.
