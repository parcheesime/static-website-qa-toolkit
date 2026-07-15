from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
import json
import re
import time

from qa_common import discover, is_minified, report_metadata, target_arguments

ARGS, TARGET, REPORT_DIR = target_arguments("Find likely unused assets and dead code")
AUDIT = {"id": "project-quality", "name": "Project Quality", "category": "maintainability"}
JSON_FILE, TEXT_FILE = REPORT_DIR / "project_quality.json", REPORT_DIR / "project_quality.txt"
COMMAND = f"python3 scripts/project_quality_audit.py --target {TARGET}"
ASSET_SUFFIXES = {".avif", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp", ".woff", ".woff2", ".mp3", ".mp4", ".pdf"}
TEXT_SUFFIXES = {".html", ".htm", ".css", ".js", ".json", ".webmanifest", ".xml", ".svg"}
LOW_PREFIXES = ("text-", "bg-", "font-", "grid-", "flex-")
LOW_NAMES = {"sr-only", "visually-hidden", "is-active", "active", "open", "is-open", "expanded", "hidden"}
STATE_MARKERS = (":hover", ":focus", ":active", ":visited", ":checked", ":disabled", ":open", "::before", "::after", "[")
SOURCE_TYPES = ["HTML attributes", "CSS url()", "inline styles", "JavaScript strings", "JSON/manifests", "XML/structured data"]


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def split_srcset(value):
    return [item.strip().split()[0] for item in value.split(",") if item.strip()]


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes, self.ids, self.references, self.inline_styles = set(), set(), [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.classes.update(values.get("class", "").split())
        if values.get("id"):
            self.ids.add(values["id"])
        for key, value in values.items():
            if not value:
                continue
            if key in {"href", "src", "poster", "data", "content"} or key.startswith("data-"):
                self.references.append(value)
            if key == "srcset":
                self.references.extend(split_srcset(value))
            if key == "style":
                self.inline_styles.append(value)


def css_rule_preludes(text):
    """Yield qualified-rule selector preludes without scanning declarations."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    stack, token, start_line, line = [], [], 1, 1
    quote, escaped = None, False
    for char in text:
        if char == "\n":
            line += 1
        if quote:
            token.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            token.append(char)
        elif char == "{":
            prelude = "".join(token).strip()
            token = []
            is_at_rule = prelude.startswith("@")
            parent_declaration = bool(stack and stack[-1]["kind"] in {"rule", "keyframes"})
            kind = "keyframes" if prelude.lower().startswith(("@keyframes", "@-webkit-keyframes")) else ("at" if is_at_rule else "rule")
            if prelude and not is_at_rule and not parent_declaration:
                yield prelude, start_line, [item["prelude"] for item in stack if item["kind"] == "at"]
            stack.append({"kind": kind, "prelude": prelude})
            start_line = line
        elif char == "}":
            token = []
            if stack:
                stack.pop()
            start_line = line
        elif char == ";":
            token = [] if stack and stack[-1]["kind"] == "rule" else token + [char]
            start_line = line
        else:
            if not token and not char.isspace():
                start_line = line
            token.append(char)


def selector_parts(prelude):
    parts, current, depth, quote = [], [], 0, None
    for char in prelude:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char; current.append(char)
        elif char in "([":
            depth += 1; current.append(char)
        elif char in ")]":
            depth = max(0, depth - 1); current.append(char)
        elif char == "," and depth == 0:
            if "".join(current).strip(): parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if "".join(current).strip(): parts.append("".join(current).strip())
    return parts


def resolve_reference(source, value):
    value = value.strip().strip("\"'")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    raw = unquote(parsed.path)
    candidate = TARGET / raw.lstrip("/") if raw.startswith("/") else source.parent / raw
    try:
        resolved = candidate.resolve()
        return resolved if resolved.is_relative_to(TARGET) else None
    except OSError:
        return None


start = time.perf_counter()
html_files = discover(TARGET, "*.html")
css_files = [p for p in discover(TARGET, "*.css") if not is_minified(p)]
js_files = [p for p in discover(TARGET, "*.js") if not is_minified(p)]
text_files = [p for p in discover(TARGET, "*") if p.suffix.lower() in TEXT_SUFFIXES and not is_minified(p)]
asset_files = [p for p in discover(TARGET, "*") if p.suffix.lower() in ASSET_SUFFIXES]
classes, ids, raw_references, inline_styles = set(), set(), [], []

for path in html_files:
    parser = Markup(); parser.feed(read_text(path))
    classes.update(parser.classes); ids.update(parser.ids)
    raw_references.extend((path, ref) for ref in parser.references)
    inline_styles.extend((path, value) for value in parser.inline_styles)

all_text = {path: read_text(path) for path in text_files}
js_text = "\n".join(all_text.get(path, "") for path in js_files)
for match in re.findall(r"(?:querySelector(?:All)?|closest|matches)\s*\(\s*['\"]([^'\"]+)", js_text):
    classes.update(re.findall(r"\.([A-Za-z_-][\w-]*)", match)); ids.update(re.findall(r"#([A-Za-z_-][\w-]*)", match))
for match in re.findall(r"classList\.(?:add|remove|toggle)\s*\(([^)]*)\)", js_text):
    classes.update(re.findall(r"['\"]([A-Za-z_-][\w-]*)['\"]", match))
for match in re.findall(r"className\s*=\s*['\"]([^'\"]+)", js_text):
    classes.update(match.split())

for path, text in all_text.items():
    for value in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text, flags=re.I):
        raw_references.append((path, value[1]))
    for value in re.findall(r"['\"]([^'\"\n]+\.(?:avif|gif|ico|jpe?g|png|svg|webp|woff2?|mp3|mp4|pdf)(?:[?#][^'\"]*)?)['\"]", text, flags=re.I):
        raw_references.append((path, value))
for path, value in inline_styles:
    for _, ref in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", value, flags=re.I):
        raw_references.append((path, ref))

referenced = {resolved for source, value in raw_references if (resolved := resolve_reference(source, value))}
asset_findings = []
for asset in asset_files:
    if asset.resolve() in referenced:
        continue
    name = asset.name.lower(); relative = asset.relative_to(TARGET).as_posix()
    special = any(word in name for word in ("favicon", "apple-touch", "manifest", "social", "twitter", "404", "hover")) or name.startswith("og-")
    confidence = "LOW" if special else "MEDIUM"
    asset_findings.append({"asset_path": relative, "file_size": asset.stat().st_size, "confidence": confidence,
                           "reason": "No normalized reference was found; dynamic references remain possible.", "source_types_searched": SOURCE_TYPES})

selector_occurrences = defaultdict(list)
for path in css_files:
    for prelude, line, contexts in css_rule_preludes(read_text(path)):
        for selector in selector_parts(prelude):
            for marker in re.findall(r"[.#][A-Za-z_-][\w-]*", selector):
                selector_occurrences[marker].append({"file": str(path.relative_to(TARGET)), "line": line, "selector_text": selector, "contexts": contexts})

selector_groups = {"high_confidence_likely_unused": [], "medium_confidence_review_recommended": [], "low_confidence_informational": []}
for marker, locations in sorted(selector_occurrences.items()):
    token = marker[1:]
    if (marker[0] == "." and token in classes) or (marker[0] == "#" and token in ids):
        continue
    texts = " ".join(item["selector_text"] for item in locations)
    context_text = " ".join(context for item in locations for context in item["contexts"]).lower()
    low = token in LOW_NAMES or token.startswith(LOW_PREFIXES) or any(state in texts for state in STATE_MARKERS) or "prefers-reduced-motion" in context_text or "print" in context_text
    complex_selector = any(re.search(r"\s|[>+~]", item["selector_text"].replace(marker, "", 1)) for item in locations)
    group = "low_confidence_informational" if low else ("medium_confidence_review_recommended" if complex_selector else "high_confidence_likely_unused")
    selector_groups[group].append({"selector": marker, "occurrence_count": len(locations), "locations": locations,
                                   "confidence": "LOW" if low else ("MEDIUM" if complex_selector else "HIGH"), "reason": "No detected HTML or JavaScript usage."})

dead_functions = []
search_text = "\n".join(all_text.values())
for path in js_files:
    text = all_text.get(path, "")
    names = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", text))
    names.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", text))
    for name in sorted(names):
        if len(re.findall(rf"\b{re.escape(name)}\b", search_text)) == 1:
            dead_functions.append({"file": str(path.relative_to(TARGET)), "symbol": name, "confidence": "MEDIUM"})

issues = {"unused_assets": asset_findings, "unused_css_selectors": selector_groups, "likely_dead_javascript_functions": dead_functions}
actionable = len(selector_groups["high_confidence_likely_unused"]) + len(selector_groups["medium_confidence_review_recommended"]) + len(dead_functions)
status = "WARNING" if actionable else "PASS"
duration = round((time.perf_counter() - start) * 1000)
report = {"schema_version": "1.0", "audit": AUDIT,
          "metadata": report_metadata(TARGET, ARGS, AUDIT["name"], COMMAND, "AVAILABLE", duration, JSON_FILE),
          "result": {"passed": True, "status": status, "severity": status.lower(), "score": 85 if actionable else 100,
                     "confidence": "medium", "counts": {"errors": 0, "warnings": actionable, "recommendations": 1 if any((asset_findings, actionable)) else 0}},
          "metrics": {"html_files": len(html_files), "css_files": len(css_files), "javascript_files": len(js_files), "assets": len(asset_files), "unused_asset_candidates": len(asset_findings)},
          "issues": issues, "recommendations": ["Review findings manually; never delete based on this heuristic alone."] if any((asset_findings, actionable)) else []}
JSON_FILE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
TEXT_FILE.write_text(f"Schema Version: 1.0\nAudit: Project Quality\nProject: {ARGS.project}\nTarget: {TARGET}\nRun ID: {ARGS.run_id}\nCommand: {COMMAND}\nTool Status: AVAILABLE\nAudit Result: {status}\nConfidence: medium\nDuration Ms: {duration}\nReport: {TEXT_FILE.resolve()}\n\n" + json.dumps(issues, indent=2) + "\n", encoding="utf-8")
print(f"Project quality audit: {status}")
