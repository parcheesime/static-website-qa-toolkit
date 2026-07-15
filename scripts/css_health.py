from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
import re
import time
from qa_common import discover, report_metadata, target_arguments

SCHEMA_VERSION = "1.0"
TOOL = "css_health.py"
AUDIT = {
    "id": "css-health",
    "name": "CSS Health",
    "category": "css",
}
ARGS, TARGET, REPORT_DIR = target_arguments("Audit CSS health in a static website")
CSS_FILES = discover(TARGET, "*.css")
COMMAND = f"python3 scripts/css_health.py --target {TARGET}"
REPORT_FILE = REPORT_DIR / "css_health.txt"
JSON_REPORT_FILE = REPORT_DIR / "css_health.json"

PROJECT = ARGS.project
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
EXIT_CODE = 0

REPORT_DIR.mkdir(exist_ok=True)

start_time = time.perf_counter()

css = "\n".join(path.read_text(encoding="utf-8") for path in CSS_FILES)
css_no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

blocks = re.findall(r"([^{}]+)\{([^{}]+)\}", css_no_comments)

selector_counts = Counter()
property_map = defaultdict(list)
important_lines = []
media_queries = []
colors = Counter()
fixed_values = []
overflow_risks = []

for line_num, line in enumerate(css.splitlines(), start=1):
    if "!important" in line:
        important_lines.append((line_num, line.strip()))

    if "@media" in line:
        media_queries.append(line.strip())

    for color in re.findall(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)", line):
        colors[color] += 1

    if re.search(r"\b(width|height|min-width|max-width|left|right|top|bottom|padding|margin)\s*:\s*\d+px", line):
        fixed_values.append((line_num, line.strip()))

    if any(x in line for x in ("100vw", "max-content", "white-space: nowrap", "overflow-x")):
        overflow_risks.append((line_num, line.strip()))

for selector, body in blocks:
    selector = selector.strip()
    selector_counts[selector] += 1

    props = re.findall(r"([\w-]+)\s*:\s*([^;]+);", body)

    for prop, value in props:
        property_map[selector].append((prop.strip(), value.strip()))

duplicate_selectors = [
    {"selector": selector, "count": count}
    for selector, count in selector_counts.items()
    if count > 1
]

conflicting_properties = []

for selector, props in property_map.items():
    values = defaultdict(set)

    for prop, value in props:
        values[prop].add(value)

    for prop, vals in values.items():
        if len(vals) > 1:
            conflicting_properties.append(
                {
                    "selector": selector,
                    "property": prop,
                    "values": sorted(vals),
                }
            )

repeated_media_queries = [
    {"query": query, "count": count}
    for query, count in Counter(media_queries).items()
    if count > 1
]

repeated_colors = [
    {"color": color, "count": count}
    for color, count in colors.most_common(15)
    if count > 1
]

metrics = {
    "css_files": [str(path.relative_to(TARGET)) for path in CSS_FILES],
    "rule_blocks": len(blocks),
    "unique_selectors": len(selector_counts),
    "duplicate_selectors": len(duplicate_selectors),
    "important_uses": len(important_lines),
    "media_queries": len(media_queries),
    "repeated_media_queries": len(repeated_media_queries),
    "hard_coded_colors": sum(colors.values()),
    "fixed_pixel_layout_values": len(fixed_values),
    "potential_overflow_risks": len(overflow_risks),
}

issues = {
    "duplicate_selectors": duplicate_selectors,
    "conflicting_properties": conflicting_properties,
    "important_usage": [
        {"line": line, "text": text}
        for line, text in important_lines
    ],
    "repeated_media_queries": repeated_media_queries,
    "most_repeated_colors": repeated_colors,
    "potential_overflow_risks": [
        {"line": line, "text": text}
        for line, text in overflow_risks
    ],
    "fixed_pixel_layout_values": [
        {"line": line, "text": text}
        for line, text in fixed_values
    ],
}

issue_count = sum(len(items) for items in issues.values())
status = "NOT_APPLICABLE" if not CSS_FILES else ("WARNING" if issue_count else "PASS")
severity = status.lower()
score = None if not CSS_FILES else (85 if issue_count else 100)
duration_ms = round((time.perf_counter() - start_time) * 1000)

report = {
    "schema_version": SCHEMA_VERSION,
    "audit": AUDIT,
    "metadata": {
        "generated": TIMESTAMP,
        **report_metadata(TARGET, ARGS, AUDIT["name"], COMMAND, "AVAILABLE", duration_ms, JSON_REPORT_FILE),
        "tool": TOOL,
        "command": COMMAND,
        "exit_code": EXIT_CODE,
        "duration_ms": duration_ms,
    },
    "result": {
        "passed": True,
        "status": status,
        "severity": severity,
        "score": score,
        "confidence": "medium",
        "counts": {
            "errors": 0,
            "warnings": issue_count,
            "recommendations": 0,
        },
    },
    "metrics": metrics,
    "issues": issues,
    "recommendations": [],
}

with REPORT_FILE.open("w", encoding="utf-8") as f:
    f.write("=====================================\n")
    f.write("CSS HEALTH REPORT\n")
    f.write("=====================================\n\n")

    f.write(f"Generated : {report['metadata']['generated']}\n")
    f.write(f"Project   : {report['metadata']['project']}\n")
    f.write(f"Schema    : {report['schema_version']}\nTarget    : {TARGET}\nRun ID    : {ARGS.run_id}\nTool Status: AVAILABLE\nConfidence: {report['result']['confidence']}\nDuration Ms: {duration_ms}\nReport    : {REPORT_FILE.resolve()}\n")
    f.write(f"Tool      : {report['metadata']['tool']}\n")
    f.write(f"Command   : {report['metadata']['command']}\n")
    f.write(f"Exit Code : {report['metadata']['exit_code']}\n")
    f.write(f"Result    : {report['result']['severity'].upper()}\n")
    f.write("\n=====================================\n\n")

    f.write(f"CSS Files: {', '.join(report['metrics']['css_files']) or '(none)'}\n")
    f.write(f"Rule Blocks: {report['metrics']['rule_blocks']}\n")
    f.write(f"Unique Selectors: {report['metrics']['unique_selectors']}\n")
    f.write(f"Duplicate Selectors: {report['metrics']['duplicate_selectors']}\n")
    f.write(f"!important Uses: {report['metrics']['important_uses']}\n")
    f.write(f"Media Queries: {report['metrics']['media_queries']}\n")
    f.write(f"Repeated Media Queries: {report['metrics']['repeated_media_queries']}\n")
    f.write(f"Hard-Coded Colors: {report['metrics']['hard_coded_colors']}\n")
    f.write(f"Fixed Pixel Layout Values: {report['metrics']['fixed_pixel_layout_values']}\n")
    f.write(f"Potential Overflow Risks: {report['metrics']['potential_overflow_risks']}\n\n")

    f.write("=== Duplicate Selectors ===\n")
    for item in report["issues"]["duplicate_selectors"]:
        f.write(f"{item['selector']} ({item['count']})\n")

    f.write("\n=== Conflicting Properties ===\n")
    for item in report["issues"]["conflicting_properties"]:
        f.write(f"{item['selector']}\n")
        f.write(f"  {item['property']}: {', '.join(item['values'])}\n")

    f.write("\n=== !important Usage ===\n")
    for item in report["issues"]["important_usage"]:
        f.write(f"{item['line']}: {item['text']}\n")

    f.write("\n=== Repeated Media Queries ===\n")
    for item in report["issues"]["repeated_media_queries"]:
        f.write(f"{item['query']} ({item['count']})\n")

    f.write("\n=== Most Repeated Colors ===\n")
    for item in report["issues"]["most_repeated_colors"]:
        f.write(f"{item['color']}: {item['count']}\n")

    f.write("\n=== Potential Overflow Risks ===\n")
    for item in report["issues"]["potential_overflow_risks"]:
        f.write(f"{item['line']}: {item['text']}\n")

    f.write("\n=== Fixed Pixel Layout Values ===\n")
    for item in report["issues"]["fixed_pixel_layout_values"]:
        f.write(f"{item['line']}: {item['text']}\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("CSS health audit complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")
raise SystemExit(EXIT_CODE)
