# Knowledge publication failure, October 24, 2026

At 04:20 UTC the WhatsApp publication precheck rejected five broken links in the
new weekly synthesis. The 04:23 watchdog retry failed on the same files. Each
reference used `../<group>/<date>.md` from `whatsapp/brain/weekly/`; the correct
path requires `../../`. The frontmatter source references had the same defect.
The failure occurred before any Drive upload. Timeless publication was isolated.

The prior repair corrected generated files and installed a validator in the
brain runtime. That improved feedback but left correctness dependent on model
behavior. The authoritative host check still rejected the entire knowledge base,
and a retry could only recheck the same invalid synthesis. There was no validated
fallback that allowed fresh daily knowledge to publish independently.

The fix makes the host publisher own a scoped snapshot, deterministic bounded
link repair, complete validation, and last-successful-publication caching. A
broken synthesis can use the last validated brain and navigation while fresh
valid daily pages continue. Fallback remains explicitly degraded and alerts the
owner. Invalid source provenance never falls back silently. Original repairs and
rejected candidates remain private for investigation; stable Drive IDs and upload
checkpoints are retained. Network/upload failures have bounded retries.

Regression coverage exercises both knowledge scopes, repeated safe repairs,
source freshness during fallback, navigation recovery, bad provenance, missing
or corrupt cache, interrupted upload, concurrent edits, secret exclusion, and
symlink escape. Watchdog tests verify degraded alerts are deduplicated without
pointless retries. These checks establish structural publication safety; they do
not guarantee the semantic completeness of model-written summaries.
