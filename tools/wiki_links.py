"""Render portable Markdown links using the existing published Drive identities."""

import re
import json


def readable_markdown(text):
    """Keep machine metadata canonical while giving Drive readers normal wiki prose."""
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not match:
        return text
    header, body = match[1], text[match.end() :].lstrip("\n")
    labels = []
    for key, label in [
        ("status_evidence_date", "Evidence through"),
        ("last_reviewed", "Reviewed"),
        ("evidence_class", "Evidence"),
    ]:
        field = re.search(r"^" + key + r":\s*(.+)$", header, re.M)
        if field:
            labels.append(label + ": " + display_value(field[1]))
    source = re.search(r"^sources:.*?(?=^[a-z_]+:|\Z)", header, re.M | re.S)
    urls = list(dict.fromkeys(re.findall(r'https?://[^\s"\]>,]+', source[0]))) if source else []
    footer = ("\n\n---\n\n" + " · ".join(labels)) if labels or urls else ""
    urls = [url.strip("\"'") for url in urls if url.strip("\"'") not in body]
    if urls:
        footer += "\n\nSource references:\n\n" + "\n".join("- [Source](" + url.strip("\"'") + ")" for url in urls)
    return body.rstrip() + footer + "\n"


def display_value(value):
    try:
        return str(json.loads(value))
    except ValueError:
        return value.strip("\"'")


def exported_text(path, root, state):
    """Resolve local Markdown navigation to the stable published Drive IDs."""

    def replace(match):
        target = match[2]
        if target.startswith(("https://", "http://", "mailto:", "#")):
            return match[0]
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError(f"Export link escapes knowledge base: {target}")
        relative = resolved.relative_to(root.resolve()).as_posix()
        if relative not in state:
            raise ValueError(f"Export link has no published page: {relative}")
        return match[1] + "https://drive.google.com/file/d/" + state[relative] + "/view" + match[3]

    return re.sub(r"(\[[^\]]*\]\()([^)]*)(\))", replace, readable_markdown(path.read_text()))
