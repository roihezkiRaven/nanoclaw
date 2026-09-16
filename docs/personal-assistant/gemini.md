# Gemini subscription boundary

Google AI Pro/Ultra provides higher Gemini CLI quotas when you sign in with the
subscribed Google account. Gemini CLI also has headless output and usage stats,
but that does not make its OAuth session an approved backend credential for a
third-party agent.

Google’s Gemini CLI FAQ explicitly warns that third-party software must not
harvest or piggyback on Gemini CLI OAuth authentication. Therefore NanoClaw does
not store, mount, refresh, proxy, or invoke the subscription OAuth session from
agent turns, cron jobs, ADK workers, or wrappers.

## What the subscription provides

The published Gemini CLI limits currently list 1,500 requests/day for Google AI
Pro and 2,000 requests/day for Google AI Ultra. Agent mode and Gemini CLI usage
share the same per-user quota, so adding NanoClaw as another OAuth client would
not create extra quota and would make usage accounting less predictable.

## Supported use

Use Gemini CLI interactively on a trusted workstation, authenticate with the
subscription account, and inspect usage with `/stats model`. For a one-off batch,
the supported CLI also has headless mode (for example, `gemini -p "..."
--output-format json --stats`). Copy the resulting report into NanoClaw as an
ordinary file if the assistant should summarize it. This keeps the subscription
inside Google’s intended CLI surface and supports its multimodal features
without giving the daemon the OAuth session.

## Automation boundary

Automated NanoClaw multimodal work is disabled until the owner explicitly
provides a separate compliant Gemini API authorization key or Vertex AI
identity. That future provider must have independent quota/billing limits,
source-policy checks, usage logging, and a fail-closed credential path. It must
not reuse Drive OAuth credentials or Gemini CLI tokens.

References: [Gemini CLI quotas](https://geminicli.com/docs/resources/quota-and-pricing/),
[headless mode](https://geminicli.com/docs/cli/headless/),
[Google Cloud agent-mode quotas](https://docs.cloud.google.com/gemini/docs/quotas#quotas-for-agent-mode-gemini-cli),
and [Gemini CLI FAQ](https://github.com/google-gemini/gemini-cli/blob/main/docs/resources/faq.md).
