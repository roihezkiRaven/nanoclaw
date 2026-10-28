---
name: knowledge-wiki-maintainer
description: Consolidate AI Engineering research into a stable evidence-grounded concept wiki.
---

# AI Engineering concept wiki

Maintain `work/knowledge/ai-engineering/wiki/`. Prior analyses, source assets,
inspection registers and checkpoints remain in their existing workspace paths.
The host publisher mirrors the wiki to the approved AI Engineering Knowledge Base
folder with stable page IDs and working Drive links. Never create another daily
version/index/ledger text export as the primary product. Old exports are supporting
research in the existing Research archive; preserve their IDs and source links.

Read relevant canonical concepts before processing new evidence. Deduplicate by
canonical source/video ID and topic, not title or publication day. Inspect the
available permitted primary source deeply; distinguish description, excerpt,
complete available machine transcript, selected slides and actual video/audio.
Never equate fetching or hash verification with understanding, and never copy
whole copyrighted transcripts into the published wiki. Retain exact source
locators, revisions/hashes, relevant timestamps and inspection limits privately.

Update one stable `brain/concepts/<concept>.md` per concept. Use `type: concept`,
`evidence_class`, nonempty `sources`, and sections `What it is`, `When to use`,
`How it works`, `Evidence and limits`, `Related concepts`. Include concrete
mechanisms/counterexamples, applicability, trade-offs and source-grounded limits.
Reconcile claims and preserve useful older knowledge instead of appending daily
“delta” sections. Mark hypotheses and unexecuted experiments; do not promote a
vendor narrative or a passed installation check to a reproduced result.

Keep public research, private community evidence, discovery-only candidates and
operational logs separate. Community reports do not independently validate public
claims. Do not place private source excerpts or customer context in public queries.
Update `evidence/private-community.md` for private evidence and use explicitly
labeled community concepts when needed. Preserve Timeless/WhatsApp boundaries;
this research wiki does not rewrite either source knowledge base.

Root navigation should guide a reader to concepts and decisions, not enumerate
runs. The generated concept map links every canonical page. Existing archived
versions retain detailed provenance. A no-delta run may update its checkpoint or
inspection status without manufacturing a new publication or newer fact date.

Run `python3 /workspace/agent/knowledge-validator.py
/workspace/agent/work/knowledge/ai-engineering/wiki` before completion. Keep the
validator's `knowledge_quality.py` companion installed. Report preparation,
publication and verified readback separately; a staged file is not a published
update. Do not send routine notifications or claim an unverified publication.
