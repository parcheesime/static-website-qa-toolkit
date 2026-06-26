from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import json
import socket
import subprocess
import time

SCHEMA_VERSION = "1.0"
TOOL = "link_audit.py"
COMMAND = "python3 scripts/link_audit.py"
AUDIT = {
    "id": "broken-links",
    "name": "Broken Link Audit",
    "category": "links",
}
SKIPPED_SCHEMES = {"mailto", "tel", "sms", "javascript", "data"}
ASSET_EXTENSIONS = {
    ".avif",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
}
REQUEST_TIMEOUT = 5

PROJECT = Path.cwd().name
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
ROOT = Path.cwd()

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

REPORT_FILE = REPORT_DIR / "link_audit.txt"
JSON_REPORT_FILE = REPORT_DIR / "link_audit.json"


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.references = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if "id" in attrs:
            self.ids.add(attrs["id"])

        for attr, kind in reference_attributes(tag):
            if attr in attrs:
                self.references.append(
                    {
                        "tag": tag,
                        "attribute": attr,
                        "value": attrs[attr],
                        "kind": kind,
                        "attrs": attrs,
                    }
                )


def reference_attributes(tag):
    mapping = {
        "a": [("href", "link")],
        "area": [("href", "link")],
        "img": [("src", "asset"), ("srcset", "asset")],
        "script": [("src", "asset")],
        "link": [("href", "asset")],
        "source": [("src", "asset"), ("srcset", "asset")],
        "video": [("src", "asset"), ("poster", "asset")],
        "audio": [("src", "asset")],
        "iframe": [("src", "asset")],
        "embed": [("src", "asset")],
        "object": [("data", "asset")],
        "track": [("src", "asset")],
        "use": [("href", "asset"), ("xlink:href", "asset")],
    }
    return mapping.get(tag, [])


def top_level_html_files():
    files = sorted(Path(".").glob("*.html"))
    return sorted(files, key=lambda path: (path.name != "index.html", path.name))


def available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(port, timeout=5):
    deadline = time.perf_counter() + timeout

    while time.perf_counter() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)

            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True

        time.sleep(0.1)

    return False


def split_srcset(value):
    urls = []

    for candidate in value.split(","):
        parts = candidate.strip().split()

        if parts:
            urls.append(parts[0])

    return urls


def values_for_reference(reference):
    if reference["attribute"] == "srcset":
        return split_srcset(reference["value"])

    return [reference["value"]]


def is_skipped_resource_hint(reference):
    if reference["tag"] != "link" or reference["attribute"] != "href":
        return False

    rel_values = reference.get("attrs", {}).get("rel", "").lower().split()
    return any(rel in {"preconnect", "dns-prefetch"} for rel in rel_values)


def parse_page(path):
    parser = LinkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def issue(page, url, source, reason, **extra):
    data = {
        "page": page,
        "url": url,
        "source": source,
        "reason": reason,
    }
    data.update(extra)
    return data


def is_external(parsed):
    return parsed.scheme in {"http", "https"}


def is_skipped(parsed):
    return parsed.scheme in SKIPPED_SCHEMES


def resolve_local_path(page, parsed):
    raw_path = unquote(parsed.path)

    if raw_path.startswith("/"):
        relative = raw_path.lstrip("/")
    else:
        relative = str((page.parent / raw_path).as_posix())

    return (ROOT / relative).resolve()


def is_inside_root(path):
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def local_reference_type(reference, parsed):
    if reference["kind"] == "asset":
        return "asset"

    suffix = Path(unquote(parsed.path)).suffix.lower()

    if suffix in ASSET_EXTENSIONS:
        return "asset"

    return "internal"


def check_external(url):
    headers = {"User-Agent": "portfolio-site-qa-link-audit/1.0"}

    for method in ("HEAD", "GET"):
        request = Request(url, method=method, headers=headers)

        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return {
                    "ok": 200 <= response.status < 400,
                    "status": response.status,
                    "method": method,
                    "error": "",
                }
        except HTTPError as error:
            if method == "HEAD" and error.code == 405:
                continue

            return {
                "ok": 200 <= error.code < 400,
                "status": error.code,
                "method": method,
                "error": str(error),
            }
        except TimeoutError as error:
            return {
                "ok": False,
                "status": None,
                "method": method,
                "error": f"timeout: {error}",
            }
        except URLError as error:
            if method == "HEAD":
                continue

            return {
                "ok": False,
                "status": None,
                "method": method,
                "error": str(error.reason),
            }

    return {
        "ok": False,
        "status": None,
        "method": "GET",
        "error": "request failed",
    }


def anchor_exists(target_file, fragment, page_ids):
    if not fragment:
        return True

    if target_file in page_ids:
        return fragment in page_ids[target_file]

    if target_file.exists() and target_file.suffix.lower() == ".html":
        parser = parse_page(target_file.relative_to(ROOT))
        page_ids[target_file] = parser.ids
        return fragment in parser.ids

    return False


html_files = top_level_html_files()
port = available_port()
base_url = f"http://127.0.0.1:{port}"
start_time = time.perf_counter()
server = subprocess.Popen(
    ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

issues = {
    "broken_internal_links": [],
    "broken_external_links": [],
    "broken_asset_references": [],
    "malformed_links": [],
    "skipped_links": [],
}
page_ids = {}
metrics = {
    "pages_checked": len(html_files),
    "links_checked": 0,
    "internal_links": 0,
    "external_links": 0,
    "asset_references": 0,
    "broken_internal_links": 0,
    "broken_external_links": 0,
    "broken_asset_references": 0,
    "skipped_links": 0,
}
runtime_error = ""
server_started = wait_for_server(port)

try:
    if not server_started:
        runtime_error = "Local HTTP server did not start before timeout."
    else:
        for page in html_files:
            parser = parse_page(page)
            page_path = str(page)
            page_ids[(ROOT / page_path).resolve()] = parser.ids

            for reference in parser.references:
                source = f"{reference['tag']}[{reference['attribute']}]"

                for value in values_for_reference(reference):
                    value = value.strip()

                    if not value:
                        issues["malformed_links"].append(
                            issue(page_path, value, source, "empty reference")
                        )
                        continue

                    if is_skipped_resource_hint(reference):
                        metrics["skipped_links"] += 1
                        issues["skipped_links"].append(
                            issue(page_path, value, source, "ignored resource hint")
                        )
                        continue

                    parsed = urlparse(value)

                    if is_skipped(parsed):
                        metrics["skipped_links"] += 1
                        issues["skipped_links"].append(
                            issue(page_path, value, source, f"ignored {parsed.scheme}: URL")
                        )
                        continue

                    if parsed.scheme and not is_external(parsed):
                        issues["malformed_links"].append(
                            issue(page_path, value, source, f"unsupported URL scheme: {parsed.scheme}")
                        )
                        continue

                    if value == "#":
                        metrics["links_checked"] += 1
                        metrics["internal_links"] += 1
                        issues["malformed_links"].append(
                            issue(page_path, value, source, "placeholder href requires documented intent")
                        )
                        continue

                    if parsed.fragment and not parsed.path and not parsed.netloc:
                        metrics["links_checked"] += 1
                        metrics["internal_links"] += 1
                        current_file = (ROOT / page_path).resolve()

                        if parsed.fragment not in parser.ids:
                            issues["broken_internal_links"].append(
                                issue(
                                    page_path,
                                    value,
                                    source,
                                    "anchor target not found",
                                    target=f"#{parsed.fragment}",
                                )
                            )
                        continue

                    if is_external(parsed):
                        metrics["links_checked"] += 1
                        metrics["external_links"] += 1
                        result = check_external(value)

                        if not result["ok"]:
                            issues["broken_external_links"].append(
                                issue(
                                    page_path,
                                    value,
                                    source,
                                    "external request failed",
                                    status=result["status"],
                                    method=result["method"],
                                    error=result["error"],
                                )
                            )
                        continue

                    reference_type = local_reference_type(reference, parsed)
                    target_file = resolve_local_path(page, parsed)

                    if reference_type == "asset":
                        metrics["links_checked"] += 1
                        metrics["asset_references"] += 1

                        if not is_inside_root(target_file) or not target_file.exists():
                            issues["broken_asset_references"].append(
                                issue(
                                    page_path,
                                    value,
                                    source,
                                    "asset file not found",
                                    target=str(target_file.relative_to(ROOT)) if is_inside_root(target_file) else str(target_file),
                                )
                            )
                        continue

                    metrics["links_checked"] += 1
                    metrics["internal_links"] += 1

                    if parsed.path in ("", "."):
                        target_file = (ROOT / page_path).resolve()

                    if target_file.is_dir():
                        target_file = target_file / "index.html"

                    if not is_inside_root(target_file) or not target_file.exists():
                        issues["broken_internal_links"].append(
                            issue(
                                page_path,
                                value,
                                source,
                                "internal page not found",
                                target=str(target_file.relative_to(ROOT)) if is_inside_root(target_file) else str(target_file),
                            )
                        )
                        continue

                    if not anchor_exists(target_file, parsed.fragment, page_ids):
                        issues["broken_internal_links"].append(
                            issue(
                                page_path,
                                value,
                                source,
                                "anchor target not found",
                                target=f"{target_file.relative_to(ROOT)}#{parsed.fragment}",
                            )
                        )
finally:
    server.terminate()

    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()

duration_ms = round((time.perf_counter() - start_time) * 1000)

metrics["broken_internal_links"] = len(issues["broken_internal_links"])
metrics["broken_external_links"] = len(issues["broken_external_links"])
metrics["broken_asset_references"] = len(issues["broken_asset_references"])
metrics["skipped_links"] = len(issues["skipped_links"])

hard_failures = metrics["broken_internal_links"] + metrics["broken_asset_references"]
soft_issues = (
    metrics["broken_external_links"]
    + len(issues["malformed_links"])
    + metrics["skipped_links"]
)

if runtime_error:
    passed = False
    severity = "error"
    score = 0
    exit_code = 1
    result_errors = 1
    result_warnings = 0
    issues["malformed_links"].append(
        issue("runtime", base_url, "server", runtime_error)
    )
elif hard_failures:
    passed = False
    severity = "error"
    score = 60
    exit_code = 0
    result_errors = hard_failures
    result_warnings = soft_issues
elif soft_issues:
    passed = True
    severity = "warning"
    score = 85
    exit_code = 0
    result_errors = 0
    result_warnings = soft_issues
else:
    passed = True
    severity = "pass"
    score = 100
    exit_code = 0
    result_errors = 0
    result_warnings = 0

report = {
    "schema_version": SCHEMA_VERSION,
    "audit": AUDIT,
    "metadata": {
        "generated": TIMESTAMP,
        "project": PROJECT,
        "tool": TOOL,
        "command": COMMAND,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    },
    "result": {
        "passed": passed,
        "severity": severity,
        "score": score,
        "confidence": "medium",
        "counts": {
            "errors": result_errors,
            "warnings": result_warnings,
            "recommendations": 0,
        },
    },
    "metrics": metrics,
    "issues": issues,
    "recommendations": [],
}

with REPORT_FILE.open("w", encoding="utf-8") as f:
    f.write("=====================================\n")
    f.write("BROKEN LINK AUDIT REPORT\n")
    f.write("=====================================\n\n")

    f.write(f"Generated : {report['metadata']['generated']}\n")
    f.write(f"Project   : {report['metadata']['project']}\n")
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
            f.write(f"- {item['page']}: {item['url']}\n")
            f.write(f"  Source: {item['source']}\n")
            f.write(f"  Reason: {item['reason']}\n")

            for key, value in item.items():
                if key not in {"page", "url", "source", "reason"}:
                    f.write(f"  {key.replace('_', ' ').title()}: {value}\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("Broken link audit complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")

raise SystemExit(exit_code)
