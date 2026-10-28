"""Structural consolidation checks; source-grounded answer checks live in private fixtures."""

import json
import hashlib
import re
from datetime import date


def project_errors(relative, text, meta):
    if meta.get("type") != "project" or not meta.get("status_evidence_date"):
        return []
    headings = re.findall(r"^## Current status[^\n]*", text, re.M)
    date = meta["status_evidence_date"].strip("\"'")
    if len(headings) != 1:
        return [f"{relative}: project needs exactly one current-status section"]
    if date not in headings[0]:
        return [f"{relative}: current-status heading differs from status_evidence_date"]
    return []


def aliases(meta):
    value = json.loads(meta.get("aliases", "[]"))
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError("aliases must be a JSON list of nonempty names")
    return [x.casefold().strip() for x in value]


def alias_errors(pages):
    owners, errors = {}, []
    for relative, _, meta in pages:
        if meta.get("type") != "project":
            continue
        try:
            for alias in aliases(meta):
                if alias in owners and owners[alias] != relative:
                    errors.append(f"{relative}: alias {alias!r} already belongs to {owners[alias]}")
                owners[alias] = relative
        except (ValueError, TypeError) as error:
            errors.append(f"{relative}: {error}")
    return errors


def assessment_errors(root, source_id, item):
    values = item.get("project_assessments", [])
    if not isinstance(values, list) or any(not isinstance(a, dict) for a in values):
        return [f"{source_id}: project_assessments must be a list of objects"]
    return [f"{source_id}: {message}" for a in values for message in assessment_error(root, item, a)]


def assessment_error(root, item, assessment):
    path = assessment.get("project", "")
    if not isinstance(path, str) or (root / path).resolve().parent != (root / "projects").resolve():
        return ["assessment project must be a canonical project path"]
    errors = []
    if not (root / path).is_file():
        errors.append(f"assessment project does not exist: {path}")
    if assessment.get("outcome") not in {"updated", "no_material_change", "unresolved"}:
        errors.append("invalid project assessment outcome")
    if not assessment.get("reason") or not assessment.get("evidence"):
        errors.append("project assessment requires a reason and source evidence")
    if assessment.get("outcome") == "updated" and path not in item.get("project_outputs", []):
        errors.append(f"assessed update is absent from project_outputs: {path}")
    return errors


def concept_errors(relative, text, meta):
    if meta.get("type") != "concept":
        return []
    required = [
        "What it is",
        "When to use",
        "How it works",
        "Evidence and limits",
        "Related concepts",
    ]
    missing = [heading for heading in required if not re.search(r"^## " + heading + r"\s*$", text, re.M)]
    errors = [f"{relative}: concept lacks section: {heading}" for heading in missing]
    if not meta.get("evidence_class") or meta.get("sources", "").strip() in {"", "[]"}:
        errors.append(f"{relative}: concept requires an evidence class and source references")
    return errors


def navigation_errors(relative, text):
    if relative.as_posix() != "index.md":
        return []
    projects = re.findall(r"\]\((projects/[^)#]+\.md)(?:#[^)]*)?\)", text)
    duplicate = sorted({path for path in projects if projects.count(path) > 1})
    return [f"{relative}: duplicate project navigation: {path}" for path in duplicate]


def metadata_errors(relative, text, meta):
    errors = []
    for key in ('status_evidence_date', 'last_reviewed'):
        if key not in meta:
            continue
        value = meta[key].strip("\"'")
        try:
            valid = date.fromisoformat(value).isoformat() == value
        except ValueError:
            valid = False
        if not valid:
            errors.append(f'{relative}: {key} must be a standalone ISO date')
    current = None
    header = text.split('---', 2)[1] if text.startswith('---\n') else ''
    for line in header.splitlines():
        if re.match(r'^[a-zA-Z_]+:', line):
            current = line.split(':', 1)[0]
        if re.match(r'^\s+- id:', line) and current != 'sources':
            errors.append(f'{relative}: source record is outside the sources field')
    return errors


def page_quality_errors(relative, text, meta):
    header = text.split('---', 2)[1] if text.startswith('---\n') else ''
    keys = re.findall(r'^([a-zA-Z_]+):', header, re.M)
    errors = [f'{relative}: duplicate frontmatter key: {key}' for key in set(keys) if keys.count(key) > 1]
    errors += metadata_errors(relative, text, meta)
    errors += project_errors(relative, text, meta) + concept_errors(relative, text, meta) + navigation_errors(relative, text)
    templates = ('Historical backfill synthesis', 'Mentioned in the day’s technical discussion', "Mentioned in the day's technical discussion")
    if relative.parts[0] == 'whatsapp' and re.fullmatch(r'\d{4}-\d{2}-\d{2}.md', relative.name) and any(t in text for t in templates):
        errors.append(f'{relative}: keyword-template digest needs substantive reprocessing')
    return errors


def validate(root, scope, frontmatter, in_scope):
    pages, errors = [], []
    for path in root.rglob('*.md'):
        relative = path.relative_to(root)
        if not in_scope(relative, scope):
            continue
        text = path.read_text()
        meta = frontmatter(text) or {}
        pages.append((relative, text, meta))
        errors += page_quality_errors(relative, text, meta)
    return errors + alias_errors(pages)


def mentioned_projects(root, text, frontmatter):
    found = {}
    for path in (root / "projects").glob("*.md"):
        meta = frontmatter(path.read_text()) or {}
        if meta.get("type") != "project":
            continue
        sensitive = json.loads(meta.get("case_sensitive_aliases", "[]"))
        for alias in json.loads(meta.get("aliases", "[]")):
            flags = 0 if alias in sensitive else re.I
            match = re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, flags)
            if match:
                found[path.relative_to(root).as_posix()] = text[max(0, match.start() - 80) : match.end() + 120]
                break
    return found


def source_assessment_errors(root, cache, frontmatter):
    path = root / "ingestion.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text()).get("files", {})
    errors = []
    for source_id, item in entries.items():
        if item.get("consolidation_version") != 2:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", source_id):
            errors.append("Invalid source ID in assessment checkpoint")
            continue
        try:
            revision = hashlib.sha256(item["modifiedTime"].encode()).hexdigest()
            versioned = cache / source_id / (revision + ".json")
            path = versioned if versioned.exists() else cache / (source_id + ".json")
            source = json.loads(path.read_text())
            errors += source_review_errors(root, source_id, item, source, frontmatter)
        except (OSError, ValueError, TypeError) as error:
            errors.append(f"{source_id}: unavailable source assessment cache: {type(error).__name__}")
    return errors


def normalized(value):
    return " ".join(value.replace("\ufeff", "").split()).casefold()


def updated_claim_errors(root, source_id, assessment):
    if assessment.get("outcome") != "updated":
        return []
    path = root / assessment.get("project", "")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        return [f"{source_id}: missing assessed project"]
    text = path.read_text()
    body = normalized(text.split("---", 2)[-1])
    claim = normalized(assessment.get("canonical_fact", assessment.get("reason", "")))
    start = body.find(claim)
    if not claim or start < 0:
        return [f"{source_id}: assessed fact is absent from project body: {path.name}"]
    citation = body[start : start + len(claim) + 220]
    if source_id.casefold() not in citation:
        return [f"{source_id}: assessed project fact lacks its nearby source citation: {path.name}"]
    return []


def explicit_projects(root, source, frontmatter):
    named = mentioned_projects(root, source.get("meta", {}).get("name", ""), frontmatter)
    headings = [
        line.strip().strip("# ").rstrip(":")
        for line in source.get("text", "").splitlines()
        if len(line.strip()) <= 120 and len(line.split()) <= 12 and not line.strip().startswith(("*", "-", "•", "http"))
    ]
    for path in (root / "projects").glob("*.md"):
        meta = frontmatter(path.read_text()) or {}
        if meta.get("type") != "project":
            continue
        ambiguous = json.loads(meta.get("ambiguous_aliases", "[]"))
        names = [a for a in json.loads(meta.get("aliases", "[]")) if a not in ambiguous]
        if any(re.match(re.escape(a) + r"(?!\w)", heading, re.I) for a in names for heading in headings):
            named[path.relative_to(root).as_posix()] = ""
    return set(named)


def no_change_errors(root, source_id, assessment, explicit):
    fact, excluded = assessment.get('retained_fact'), assessment.get('scope_exclusion')
    if fact:
        body = (root / assessment['project']).read_text().split('---', 2)[-1]
        if normalized(fact) not in normalized(body):
            return [f'{source_id}: claimed retained fact is absent from the canonical page']
    elif not excluded or assessment['project'] in explicit:
        return [f'{source_id}: no-change requires a retained fact or a concrete non-project scope exclusion']
    return []


def disposition_errors(root, source_id, assessment, explicit):
    if re.search(r'legacy consolidation review|mentioned in contextual|does not justify attributing', assessment.get('reason', ''), re.I):
        return [f'{source_id}: generic source assessment is not a semantic review']
    if assessment.get('outcome') == 'no_material_change':
        return no_change_errors(root, source_id, assessment, explicit)
    if assessment.get('outcome') == 'unresolved' and (not assessment.get('uncertainty') or assessment.get('project') in explicit):
        return [f'{source_id}: explicit project evidence cannot be dismissed as generic ambiguous attribution']
    return []


def source_review_errors(root, source_id, item, source, frontmatter):
    if not source.get("complete") or source.get("meta", {}).get("modifiedTime") != item.get("modifiedTime"):
        return [f"{source_id}: source assessment needs the complete checkpointed revision"]
    text = source.get("text", "")
    assessments = item.get("project_assessments", [])
    if not isinstance(assessments, list) or any(not isinstance(a, dict) for a in assessments):
        return [f"{source_id}: malformed source assessments"]
    assessed = {a.get("project") for a in assessments if isinstance(a, dict)}
    mentions = mentioned_projects(root, text, frontmatter)
    errors = [f"{source_id}: unassessed known project mention: {p}" for p in mentions if p not in assessed]
    explicit = explicit_projects(root, source, frontmatter)
    explicit -= {a.get("project") for a in assessments if a.get("outcome") == "updated" or a.get("retained_fact")}
    for assessment in assessments:
        evidence = assessment.get("evidence", "")
        if not isinstance(evidence, str) or not evidence or normalized(evidence) not in normalized(text):
            errors.append(f"{source_id}: assessment evidence is not an exact excerpt of this source revision")
        errors += updated_claim_errors(root, source_id, assessment)
        errors += disposition_errors(root, source_id, assessment, explicit)
    return errors
