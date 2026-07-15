from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
import json
import re
import time
from qa_common import discover, report_metadata, target_arguments

SCHEMA_VERSION = "1.0"
TOOL = "design_audit.py"
AUDIT = {
    "id": "design-consistency",
    "name": "Design Consistency",
    "category": "design",
}

ARGS, TARGET, REPORT_DIR = target_arguments("Audit static website design consistency")
COMMAND = f"python3 scripts/design_audit.py --target {TARGET}"
PROJECT = ARGS.project
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
ROOT = TARGET

REPORT_DIR.mkdir(exist_ok=True)

REPORT_FILE = REPORT_DIR / "design_audit.txt"
JSON_REPORT_FILE = REPORT_DIR / "design_audit.json"

COLOR_PATTERN = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]+\)|hsla?\([^)]+\)|\b(?:black|white|red|green|blue|yellow|orange|purple|gray|grey|transparent|currentColor)\b",
    re.I,
)
DECLARATION_PATTERN = re.compile(r"([\w-]+)\s*:\s*([^;{}]+);")
BLOCK_PATTERN = re.compile(r"([^{}]+)\{([^{}]+)\}", re.S)
CSS_VAR_PATTERN = re.compile(r"--[\w-]+\s*:")
BUTTON_KEYWORDS = (
    "button",
    "btn",
    "cta",
    "nav-link",
    "resume-link",
    "project-button",
    "skill-button",
)
BUTTON_PROPS = ("padding", "border-radius", "background", "color", "border", "box-shadow")
SPACING_PROPS = {"margin", "padding", "gap", "row-gap", "column-gap", "top", "right", "bottom", "left"}
FONT_PROPS = {"font-family", "font-size", "font-weight", "line-height", "letter-spacing"}
SMALL_VISUAL_MARKERS = ("icon", "avatar", "profile", "logo", "badge", "spark")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.stylesheets = []
        self.inline_styles = []
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if "style" in attrs:
            self.inline_styles.append({"tag": tag, "style": attrs["style"]})

        if tag == "img":
            self.images.append(attrs)

        if tag == "link":
            rel_values = attrs.get("rel", "").lower().split()
            href = attrs.get("href", "")

            if "stylesheet" in rel_values and href:
                self.stylesheets.append(href)

        classes = attrs.get("class", "")
        element_id = attrs.get("id", "")
        marker = f"{tag} {classes} {element_id}".lower()

        if tag == "button" or any(keyword in marker for keyword in BUTTON_KEYWORDS):
            self.buttons.append({"tag": tag, "class": classes, "id": element_id})


def top_level_html_files():
    files = discover(ROOT, "*.html")
    return sorted(files, key=lambda path: (path.name != "index.html", str(path)))


def local_path_from_href(href):
    parsed = urlparse(href)

    if parsed.scheme or parsed.netloc:
        return None

    return Path(unquote(parsed.path))


def css_files_used_by_site(html_pages):
    css_files = []

    css_files.extend(discover(ROOT, "*.css"))

    for page in html_pages:
        parser = parse_html(page)

        for href in parser.stylesheets:
            path = local_path_from_href(href)

            if path and path.suffix.lower() == ".css":
                candidate = (ROOT / str(path).lstrip("/")) if str(path).startswith("/") else (page.parent / path)
                candidate = candidate.resolve()
                if candidate.is_relative_to(ROOT) and candidate.exists():
                    css_files.append(candidate)

    unique = []
    seen = set()

    for path in css_files:
        normalized = path.as_posix()

        if normalized not in seen:
            unique.append(path)
            seen.add(normalized)

    return unique


def parse_html(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def normalize_value(value):
    return re.sub(r"\s+", " ", value.strip())


def normalize_hex(color):
    color = color.lower()

    if re.fullmatch(r"#[0-9a-f]{3}", color):
        return "#" + "".join(char * 2 for char in color[1:])

    return color


def normalize_font_size(value):
    value = re.sub(r"!important\b", "", value, flags=re.I)
    return normalize_value(value)


def spacing_tokens(value):
    tokens = []
    value = re.sub(r"!important\b", "", value, flags=re.I)

    for token in re.split(r"\s+", value.strip()):
        token = token.strip()

        if not token or token in {"auto", "/"} or token.endswith("%"):
            continue

        if token.startswith("var("):
            tokens.append(token)
            continue

        if re.fullmatch(r"-?\d+(?:\.\d+)?(?:px|rem|em|vh|vw)|0", token):
            tokens.append(token)

    return tokens


def collect_css(css_files):
    declarations = []
    blocks = []
    css_variable_count = 0

    for path in css_files:
        text = path.read_text(encoding="utf-8")
        css_variable_count += len(CSS_VAR_PATTERN.findall(text))

        for selector, body in BLOCK_PATTERN.findall(text):
            selector = normalize_value(selector)
            blocks.append({"file": str(path), "selector": selector, "body": body})

            for prop, value in DECLARATION_PATTERN.findall(body):
                declarations.append(
                    {
                        "file": str(path),
                        "selector": selector,
                        "property": prop.strip().lower(),
                        "value": normalize_value(value),
                        "is_custom_property": prop.strip().startswith("--"),
                    }
                )

    return declarations, blocks, css_variable_count


def values_for(declarations, property_name):
    return [item["value"] for item in declarations if item["property"] == property_name]


def unique_values(values):
    return sorted(set(values))


def color_values(declarations):
    colors = []
    hard_coded = []

    for item in declarations:
        value = item["value"]

        for color in COLOR_PATTERN.findall(value):
            normalized = normalize_hex(color)
            colors.append(normalized)

            if not item["is_custom_property"] and "var(" not in value:
                hard_coded.append(
                    {
                        "file": item["file"],
                        "selector": item["selector"],
                        "property": item["property"],
                        "value": normalized,
                    }
                )

    return colors, hard_coded


def spacing_values(declarations):
    values = []

    for item in declarations:
        prop = item["property"]

        if prop in SPACING_PROPS or prop.startswith("margin-") or prop.startswith("padding-"):
            values.extend(spacing_tokens(item["value"]))

    return values


def is_likely_small_visual(item):
    selector = item["selector"].lower()
    return any(marker in selector for marker in SMALL_VISUAL_MARKERS)


def fixed_values(declarations, properties, minimum=300):
    risks = []

    for item in declarations:
        if item["property"] not in properties:
            continue

        match = re.match(r"(\d+)px\b", item["value"])

        if not match:
            continue

        size = int(match.group(1))

        if size < minimum or is_likely_small_visual(item):
            continue

        risks.append(
            {
                "file": item["file"],
                "selector": item["selector"],
                "property": item["property"],
                "value": item["value"],
            }
        )

    return risks


def button_patterns(blocks):
    patterns = []

    for block in blocks:
        selector = block["selector"].lower()

        if not any(keyword in selector for keyword in BUTTON_KEYWORDS):
            continue

        props = dict(
            (prop.strip().lower(), normalize_value(value))
            for prop, value in DECLARATION_PATTERN.findall(block["body"])
        )
        pattern = tuple(
            (prop, normalize_button_value(prop, props.get(prop, "")))
            for prop in BUTTON_PROPS
            if props.get(prop)
        )

        if pattern:
            patterns.append(
                {
                    "file": block["file"],
                    "selector": block["selector"],
                    "pattern": dict(pattern),
                }
            )

    return patterns


def normalize_button_value(prop, value):
    value = normalize_value(value)

    if prop == "padding":
        return " ".join(spacing_tokens(value))

    if prop in {"background", "color", "border", "box-shadow"}:
        if "var(" in value:
            return re.sub(r"var\((--[\w-]+)(?:,[^)]+)?\)", r"var(\1)", value)

        if COLOR_PATTERN.search(value):
            return "hard-coded-color"

    return value


def grouped_button_patterns(button_styles):
    groups = {}

    for style in button_styles:
        key = tuple(sorted(style["pattern"].items()))

        if key not in groups:
            groups[key] = {
                "pattern": style["pattern"],
                "selectors": [],
            }

        groups[key]["selectors"].append(style["selector"])

    return list(groups.values())


def review_item(message, **details):
    item = {"message": message}
    item.update(details)
    return item


def recommendations_for(issues):
    recommendations = []

    if issues["typography_consistency"]:
        recommendations.append("Review typography scale for consistency.")

    if issues["color_consistency"]:
        recommendations.append("Consider consolidating repeated hard-coded colors into CSS variables.")

    if issues["spacing_consistency"]:
        recommendations.append("Review spacing values against a consistent spacing scale.")

    if issues["button_consistency"]:
        recommendations.append("Review button and CTA styles for consistency.")

    if issues["responsive_layout_risks"]:
        recommendations.append("Review fixed width and height values for responsive behavior.")

    if issues["image_presentation"]:
        recommendations.append("Review image dimensions and loading behavior for consistent presentation.")

    if issues["inline_styles"]:
        recommendations.append("Move inline styles into shared CSS where practical.")

    return recommendations


start_time = time.perf_counter()
html_pages = top_level_html_files()
css_files = css_files_used_by_site(html_pages)
declarations, blocks, css_variable_count = collect_css(css_files)

all_parsers = {page: parse_html(page) for page in html_pages}
images = [
    {"page": str(page), "attrs": image}
    for page, parser in all_parsers.items()
    for image in parser.images
]
inline_styles = [
    {"page": str(page), **style}
    for page, parser in all_parsers.items()
    for style in parser.inline_styles
]
html_buttons = [
    {"page": str(page), **button}
    for page, parser in all_parsers.items()
    for button in parser.buttons
]

font_families = unique_values(values_for(declarations, "font-family"))
font_sizes = unique_values(normalize_font_size(value) for value in values_for(declarations, "font-size"))
font_weights = unique_values(values_for(declarations, "font-weight"))
line_heights = unique_values(values_for(declarations, "line-height"))
letter_spacing = unique_values(values_for(declarations, "letter-spacing"))
colors, hard_coded_colors = color_values(declarations)
spacing = unique_values(spacing_values(declarations))
border_radius = unique_values(values_for(declarations, "border-radius"))
box_shadow = unique_values(values_for(declarations, "box-shadow"))
button_styles = button_patterns(blocks)
button_style_families = grouped_button_patterns(button_styles)
fixed_width = fixed_values(declarations, {"width", "min-width"})
fixed_height = fixed_values(declarations, {"height", "min-height"})
missing_width = [image for image in images if "width" not in image["attrs"]]
missing_height = [image for image in images if "height" not in image["attrs"]]
missing_lazy = [
    image
    for image in images
    if image["attrs"].get("loading", "").lower() != "lazy"
    and "profile" not in image["attrs"].get("class", "").lower()
]

hard_color_counts = Counter(item["value"] for item in hard_coded_colors)
repeated_hard_colors = [
    {"value": value, "count": count}
    for value, count in sorted(hard_color_counts.items())
    if count > 1
]
font_family_hard_coded = [
    item
    for item in declarations
    if item["property"] == "font-family" and "var(" not in item["value"]
]
distinct_button_patterns = {
    tuple(sorted(family["pattern"].items()))
    for family in button_style_families
}

issues = {
    "typography_consistency": [],
    "color_consistency": [],
    "spacing_consistency": [],
    "button_consistency": [],
    "image_presentation": [],
    "responsive_layout_risks": [],
    "inline_styles": [],
    "visual_review_notes": [],
}

if len(font_sizes) > 12:
    issues["typography_consistency"].append(
        review_item("Many unique font-size values found.", count=len(font_sizes), values=font_sizes)
    )

if len(font_weights) > 5:
    issues["typography_consistency"].append(
        review_item("Many unique font-weight values found.", count=len(font_weights), values=font_weights)
    )

if len(font_families) > 4 or font_family_hard_coded:
    issues["typography_consistency"].append(
        review_item(
            "Font-family usage may need consolidation.",
            unique_count=len(font_families),
            hard_coded_count=len(font_family_hard_coded),
        )
    )

if repeated_hard_colors:
    issues["color_consistency"].append(
        review_item("Repeated hard-coded colors found.", colors=repeated_hard_colors[:12])
    )

if len(set(colors)) > 18:
    issues["color_consistency"].append(
        review_item("Many unique color values found.", count=len(set(colors)))
    )

if len(spacing) > 24:
    issues["spacing_consistency"].append(
        review_item("Many unique spacing values found.", count=len(spacing), sample=spacing[:20])
    )

if len(border_radius) > 8:
    issues["spacing_consistency"].append(
        review_item("Many unique border-radius values found.", count=len(border_radius), values=border_radius)
    )

if len(box_shadow) > 8:
    issues["spacing_consistency"].append(
        review_item("Many unique box-shadow values found.", count=len(box_shadow))
    )

if len(distinct_button_patterns) > 4:
    issues["button_consistency"].append(
        review_item(
            "Multiple distinct button or CTA visual style families found.",
            count=len(distinct_button_patterns),
            families=button_style_families[:8],
        )
    )

if missing_width:
    issues["image_presentation"].append(
        review_item("Images missing width attributes.", count=len(missing_width), images=missing_width)
    )

if missing_height:
    issues["image_presentation"].append(
        review_item("Images missing height attributes.", count=len(missing_height), images=missing_height)
    )

if missing_lazy:
    issues["image_presentation"].append(
        review_item(
            "Images missing loading=\"lazy\"; review whether they are above the fold.",
            count=len(missing_lazy),
            images=missing_lazy,
        )
    )

if fixed_width:
    issues["responsive_layout_risks"].append(
        review_item("Fixed width values may affect responsive layout.", count=len(fixed_width), values=fixed_width[:20])
    )

if fixed_height:
    issues["responsive_layout_risks"].append(
        review_item("Fixed height values may affect responsive layout.", count=len(fixed_height), values=fixed_height[:20])
    )

max_width_values = [
    item
    for item in declarations
    if item["property"] == "max-width" and re.search(r"\d+px", item["value"])
]

if max_width_values:
    issues["visual_review_notes"].append(
        review_item("Review max-width values for layout consistency.", count=len(max_width_values), values=max_width_values[:20])
    )

if inline_styles:
    issues["inline_styles"].append(
        review_item("Inline style attributes can make design consistency harder to maintain.", count=len(inline_styles), styles=inline_styles)
    )

if len(border_radius) > 1:
    issues["visual_review_notes"].append(
        review_item("Review border-radius values against the intended component system.", values=border_radius)
    )

review_count = sum(len(items) for items in issues.values())
recommendations = recommendations_for(issues)
duration_ms = round((time.perf_counter() - start_time) * 1000)

if review_count == 0:
    severity = "pass"
    score = 100
elif review_count <= 3:
    severity = "warning"
    score = 94
elif review_count <= 8:
    severity = "warning"
    score = 86
else:
    severity = "warning"
    score = 76

metrics = {
    "html_pages_checked": len(html_pages),
    "css_files_checked": len(css_files),
    "font_families_count": len(font_families),
    "font_sizes_count": len(font_sizes),
    "font_weights_count": len(font_weights),
    "line_heights_count": len(line_heights),
    "letter_spacing_count": len(letter_spacing),
    "color_values_count": len(set(colors)),
    "css_variable_count": css_variable_count,
    "hard_coded_color_count": len(hard_coded_colors),
    "spacing_values_count": len(spacing),
    "border_radius_values_count": len(border_radius),
    "box_shadow_values_count": len(box_shadow),
    "button_style_count": len(distinct_button_patterns),
    "images_checked": len(images),
    "images_missing_width": len(missing_width),
    "images_missing_height": len(missing_height),
    "images_missing_loading_lazy": len(missing_lazy),
    "fixed_width_values": len(fixed_width),
    "fixed_height_values": len(fixed_height),
    "inline_style_count": len(inline_styles),
}

report = {
    "schema_version": SCHEMA_VERSION,
    "audit": AUDIT,
    "metadata": {
        "generated": TIMESTAMP,
        **report_metadata(TARGET, ARGS, AUDIT["name"], COMMAND, "AVAILABLE", duration_ms, JSON_REPORT_FILE),
        "tool": TOOL,
        "command": COMMAND,
        "exit_code": 0,
        "duration_ms": duration_ms,
    },
    "result": {
        "passed": True,
        "status": "NOT_APPLICABLE" if not html_pages and not css_files else severity.upper(),
        "severity": severity,
        "score": score,
        "confidence": "low",
        "counts": {
            "errors": 0,
            "warnings": review_count,
            "recommendations": len(recommendations),
        },
    },
    "metrics": metrics,
    "issues": issues,
    "recommendations": recommendations,
}

with REPORT_FILE.open("w", encoding="utf-8") as f:
    f.write("=====================================\n")
    f.write("DESIGN CONSISTENCY REPORT\n")
    f.write("=====================================\n\n")

    f.write(f"Generated : {report['metadata']['generated']}\n")
    f.write(f"Project   : {report['metadata']['project']}\n")
    f.write(f"Schema    : {report['schema_version']}\nTarget    : {TARGET}\nRun ID    : {ARGS.run_id}\nTool Status: AVAILABLE\nConfidence: {report['result']['confidence']}\nDuration Ms: {duration_ms}\nReport    : {REPORT_FILE.resolve()}\n")
    f.write(f"Tool      : {report['metadata']['tool']}\n")
    f.write(f"Command   : {report['metadata']['command']}\n")
    f.write(f"Exit Code : {report['metadata']['exit_code']}\n")
    f.write(f"Result    : {report['result']['severity'].upper()}\n")
    f.write("\n=====================================\n\n")

    for key, value in report["metrics"].items():
        label = key.replace("_", " ").title()
        f.write(f"{label}: {value}\n")

    for group, group_issues in report["issues"].items():
        f.write(f"\n=== {group.replace('_', ' ').title()} ===\n")

        if not group_issues:
            f.write("None\n")
            continue

        for item in group_issues:
            f.write(f"- {item['message']}\n")

            for key, value in item.items():
                if key != "message":
                    f.write(f"  {key.replace('_', ' ').title()}: {value}\n")

    if report["recommendations"]:
        f.write("\n=== Recommendations ===\n")

        for recommendation in report["recommendations"]:
            f.write(f"- {recommendation}\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("Design consistency audit complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")

raise SystemExit(0)
