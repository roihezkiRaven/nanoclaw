"""Build stable wiki navigation from canonical pages, keeping evidence out of the front door."""

import json
import re


def title(path, metadata):
    return metadata.get("title", path.stem.replace("-", " ")).strip("\"'")


def page_link(path, base, metadata):
    import os

    return f"[{title(path, metadata)}]({os.path.relpath(path, base)})"


def write_page(root, relative, heading, lines, changes, date, whatsapp=False):
    path = root / relative
    meta = f'---\ntype: index\ntitle: {json.dumps(heading)}\ndescription: "Generated navigation to canonical knowledge and separate evidence."\ntags: []\ngenerated: {date}\nsources: []\n'
    if whatsapp:
        meta += 'group_label: "Cross-group navigation"\ngroup_jid: "cross-group"\n'
    text = meta + "---\n\n# " + heading + "\n\n" + "\n".join(lines).strip() + "\n"
    if not path.exists() or path.read_text() != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        changes.append(relative)


def pages_in(root, folder, frontmatter):
    return [
        (p, frontmatter(p.read_text()) or {})
        for p in sorted((root / folder).rglob("*.md"))
        if p.name != "index.md" and p.name != "evidence-index.md"
    ]


def latest_source(root):
    path = root / "ingestion.json"
    if not path.exists():
        return "unknown"
    entries = json.loads(path.read_text()).get("files", {})
    return max((v.get("modifiedTime", "")[:10] for v in entries.values()), default="unknown")


def current_excerpt(path):
    text = path.read_text()
    match = re.search(r"^## Current status[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        return ""
    bullet = next(
        (line[2:].strip() for line in match[1].splitlines() if line.startswith("- ")),
        "",
    )
    bullet = re.sub(r"\[[^\]]+\]\([^)]+\)", "", bullet).strip(" ()")
    return bullet


def directory(root, folder, label, frontmatter, changes, date):
    entries = pages_in(root, folder, frontmatter)
    durable = [(p, m) for p, m in entries if not p.name.startswith("historical-") and m.get("type") != "redirect"]
    lines = []
    for path, meta in durable:
        evidence = meta.get("status_evidence_date", "").strip("\"'")
        suffix = f" — evidence {evidence}" if evidence else ""
        lines.append("- " + page_link(path, root / folder, meta) + suffix)
    write_page(
        root,
        f"{folder}/index.md",
        label,
        lines or ["No canonical pages yet."],
        changes,
        date,
    )
    return durable


def evidence_directory(root, frontmatter, changes, date):
    entries = [(p, m) for p, m in pages_in(root, "topics", frontmatter) if p.name.startswith("historical-")]
    lines = [
        "Dated source assessments support the concept/project wiki. Repeated meeting titles represent separate meetings, not separate projects.",
        "",
    ]
    for path, meta in sorted(entries, key=lambda item: item[0].name, reverse=True):
        lines.append("- " + page_link(path, root / "topics", meta))
    write_page(
        root,
        "topics/evidence-index.md",
        "Source evidence archive",
        lines,
        changes,
        date,
    )


TIMELESS_BROWSE = [
    "",
    "## Browse the wiki",
    "",
    "- [Projects](projects/index.md)",
    "- [Concepts](topics/index.md)",
    "- [Decisions](decisions/index.md)",
    "- [Actions](tasks/index.md)",
    "- [Source evidence archive](topics/evidence-index.md)",
]


def timeless(root, frontmatter, changes):
    date = latest_source(root)
    projects = directory(root, "projects", "Projects and engagements", frontmatter, changes, date)
    for folder, label in [
        ("tasks", "Actions and commitments"),
        ("decisions", "Decisions"),
        ("topics", "Durable concepts"),
    ]:
        directory(root, folder, label, frontmatter, changes, date)
    evidence_directory(root, frontmatter, changes, date)
    lines = timeless_lines(root, projects, date)
    write_page(root, 'index.md', 'Timeless Knowledge', lines, changes, date)


def timeless_lines(root, projects, date):
    dated = [(p, m) for p, m in projects if m.get("status_evidence_date", "").strip("\"'") == date]
    lines = [
        f"Latest source revision in the checkpoint: **{date}**. Publication time is not evidence of new activity.",
        "",
        "## Start here",
        "",
    ]
    lines += (
        [
            "- [Current synthesis](brain/overview.md)",
            "- [Active work](brain/active-work.md)",
            "- [Risks and unresolved evidence](brain/stale-or-unresolved.md)",
        ]
        if (root / "brain/overview.md").exists()
        else []
    )
    lines += ["", "## Latest project evidence", ""]
    for path, meta in sorted(dated, key=lambda item: title(*item).casefold()):
        lines.append("- " + page_link(path, root, meta) + ": " + current_excerpt(path))
    if not dated:
        lines.append("No project has reconciled status for the latest source revision; consult unresolved evidence.")
    lines += TIMELESS_BROWSE
    if (root / "topics/source-coverage.md").exists():
        lines += ["- [Source freshness and gaps](topics/source-coverage.md)"]
    return lines


WHATSAPP_NAVIGATION = [
    "Use the concept wiki for durable learning; use group digests only to inspect evidence.",
    "",
    "## Learn by concept",
    "",
    "- [Concept map](brain/concepts/index.md)",
    "- [Synthesis](brain/overview.md)",
    "- [Tools and models](brain/tools-and-models.md)",
    "- [Patterns](brain/patterns-and-techniques.md)",
    "- [Lessons and limitations](brain/lessons-and-gotchas.md)",
    "",
    "## Evidence and coverage",
    "",
    "- [Group evidence archive](archive.md)",
    "- [Capture and ingestion coverage](coverage.md)",
]


def whatsapp_groups(root, frontmatter, changes):
    groups = []
    for folder in sorted((root / "whatsapp").iterdir()):
        if not folder.is_dir() or folder.name == "brain":
            continue
        digests = [(p, m) for p, m in pages_in(root, f"whatsapp/{folder.name}", frontmatter) if m.get("type") != "coverage-status"]
        date = max((p.stem for p, _ in digests), default="unknown")
        lines = [
            "Dated group evidence. Missing dates do not establish inactivity; consult capture coverage.",
            "",
        ]
        lines += ["- " + page_link(p, folder, m) for p, m in sorted(digests, reverse=True)]
        write_page(
            root,
            f"whatsapp/{folder.name}/index.md",
            folder.name.replace("-", " "),
            lines,
            changes,
            date,
            True,
        )
        groups.append((folder.name, len(digests), date))
    return groups


def whatsapp(root, frontmatter, changes):
    groups = whatsapp_groups(root, frontmatter, changes)
    date = max((d for _, n, d in groups if n), default="unknown")
    lines = WHATSAPP_NAVIGATION
    write_page(root, "whatsapp/index.md", "WhatsApp learning wiki", lines, changes, date, True)
    archive = [f"- [{name.replace('-', ' ')}]({name}/index.md) — {n} source digests; latest {d}." for name, n, d in groups]
    write_page(
        root,
        "whatsapp/archive.md",
        "WhatsApp group evidence",
        archive,
        changes,
        date,
        True,
    )
    concepts(root, "whatsapp/brain", frontmatter, changes, date, True)


def concepts(root, prefix, frontmatter, changes, date, whatsapp=False):
    entries = pages_in(root, prefix + "/concepts", frontmatter)
    lines = [
        "Stable concept pages combine evidence across dates. A reported community claim is not a verified result.",
        "",
    ]
    lines += ["- " + page_link(p, root / prefix / "concepts", m) for p, m in entries]
    write_page(
        root,
        prefix + "/concepts/index.md",
        "Concept map",
        lines,
        changes,
        date,
        whatsapp,
    )


def build(root, scope, frontmatter):
    changes = []
    if scope == "whatsapp":
        whatsapp(root, frontmatter, changes)
    elif scope == "engineering":
        concepts(root, "brain", frontmatter, changes, latest_source(root))
    else:
        timeless(root, frontmatter, changes)
    return changes
