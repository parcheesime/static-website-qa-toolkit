from datetime import datetime
from pathlib import Path
import json
import socket
import subprocess
import time
from qa_common import discover, local_tool, report_metadata, target_arguments

SCHEMA_VERSION = "1.0"
TOOL = "accessibility_audit.py"
AUDIT = {
    "id": "accessibility-pa11y",
    "name": "Accessibility Pa11y",
    "category": "accessibility",
}

ARGS, TARGET, REPORT_DIR = target_arguments("Audit static website accessibility")
PROJECT = ARGS.project
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

REPORT_DIR.mkdir(exist_ok=True)

REPORT_FILE = REPORT_DIR / "accessibility.txt"
JSON_REPORT_FILE = REPORT_DIR / "accessibility.json"


def top_level_html_files():
    files = discover(TARGET, "*.html")
    return sorted(files, key=lambda path: (path.name != "index.html", str(path)))


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


def run_pa11y(url):
    config = Path(__file__).resolve().parent.parent / "pa11y.config.json"
    return subprocess.run(
        [str(local_tool("pa11y")), "--config", str(config), "--reporter", "json", url],
        text=True,
        capture_output=True,
        shell=False,
    )


def parse_issues(stdout):
    if not stdout.strip():
        return []

    data = json.loads(stdout)

    if isinstance(data, list):
        return data

    return data.get("issues", [])


html_files = top_level_html_files()
port = available_port()
base_url = f"http://127.0.0.1:{port}"
pages = [
    {
        "path": str(path.relative_to(TARGET)),
        "url": f"{base_url}/{path.relative_to(TARGET).as_posix()}",
    }
    for path in html_files
]
COMMAND = "node_modules/.bin/pa11y --config pa11y.config.json --reporter json " + " ".join(page["url"] for page in pages)

start_time = time.perf_counter()
server = subprocess.Popen(
    ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(TARGET)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

issues_by_page = {}
page_results = {}
command_exit_code = 0
server_started = wait_for_server(port)

try:
    if not server_started:
        command_exit_code = 1

        for page in pages:
            issues_by_page[page["path"]] = []
            page_results[page["path"]] = {
                "url": page["url"],
                "exit_code": 1,
                "stderr": "Local HTTP server did not start before timeout.",
            }
    else:
        for page in pages:
            result = run_pa11y(page["url"])
            command_exit_code = max(command_exit_code, result.returncode)

            try:
                page_issues = parse_issues(result.stdout)
                parse_error = ""
            except json.JSONDecodeError as error:
                page_issues = []
                parse_error = str(error)
                command_exit_code = max(command_exit_code, 1)

            issues_by_page[page["path"]] = page_issues
            page_results[page["path"]] = {
                "url": page["url"],
                "exit_code": result.returncode,
                "stderr": result.stderr,
                "parse_error": parse_error,
            }
finally:
    server.terminate()

    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()

duration_ms = round((time.perf_counter() - start_time) * 1000)

errors = 0
warnings = 0
notices = 0

for page_issues in issues_by_page.values():
    for issue in page_issues:
        issue_type = issue.get("type")

        if issue_type == "error":
            errors += 1
        elif issue_type == "warning":
            warnings += 1
        elif issue_type == "notice":
            notices += 1

command_failed = command_exit_code != 0 and errors == 0 and warnings == 0 and notices == 0

if command_failed:
    errors = 1

total_issues = errors + warnings + notices

if errors:
    passed = False
    severity = "error"
    score = 0 if command_failed else 60
elif warnings or notices:
    passed = True
    severity = "warning"
    score = 90
else:
    passed = True
    severity = "pass"
    score = 100

report = {
    "schema_version": SCHEMA_VERSION,
    "audit": AUDIT,
    "metadata": {
        "generated": TIMESTAMP,
        **report_metadata(TARGET, ARGS, AUDIT["name"], COMMAND, "AVAILABLE", duration_ms, JSON_REPORT_FILE),
        "tool": TOOL,
        "command": COMMAND,
        "exit_code": command_exit_code,
        "duration_ms": duration_ms,
    },
    "result": {
        "passed": passed,
        "status": severity.upper(),
        "severity": severity,
        "score": score,
        "confidence": "high",
        "counts": {
            "errors": errors,
            "warnings": warnings,
            "recommendations": 0,
        },
    },
    "metrics": {
        "pages_checked": len(pages),
        "total_issues": total_issues,
        "errors": errors,
        "warnings": warnings,
        "notices": notices,
    },
    "issues": {
        page: {
            "url": page_results[page]["url"],
            "issues": page_issues,
            "stderr": page_results[page]["stderr"],
            "parse_error": page_results[page].get("parse_error", ""),
        }
        for page, page_issues in issues_by_page.items()
    },
    "recommendations": [],
}

with REPORT_FILE.open("w", encoding="utf-8") as f:
    f.write("=====================================\n")
    f.write("ACCESSIBILITY PA11Y REPORT\n")
    f.write("=====================================\n\n")

    f.write(f"Generated : {report['metadata']['generated']}\n")
    f.write(f"Project   : {report['metadata']['project']}\n")
    f.write(f"Schema    : {report['schema_version']}\nTarget    : {TARGET}\nRun ID    : {ARGS.run_id}\nTool Status: AVAILABLE\nConfidence: {report['result']['confidence']}\nDuration Ms: {duration_ms}\nReport    : {REPORT_FILE.resolve()}\n")
    f.write(f"Tool      : {report['metadata']['tool']}\n")
    f.write(f"Command   : {report['metadata']['command']}\n")
    f.write(f"Exit Code : {report['metadata']['exit_code']}\n")
    f.write(f"Result    : {report['result']['severity'].upper()}\n")
    f.write("\n=====================================\n\n")

    f.write(f"Pages Checked: {report['metrics']['pages_checked']}\n")
    f.write(f"Total Issues: {report['metrics']['total_issues']}\n")
    f.write(f"Errors: {report['metrics']['errors']}\n")
    f.write(f"Warnings: {report['metrics']['warnings']}\n")
    f.write(f"Notices: {report['metrics']['notices']}\n\n")

    for page, page_report in report["issues"].items():
        f.write(f"=== {page} ===\n")
        f.write(f"URL: {page_report['url']}\n")

        if page_report["stderr"]:
            f.write("STDERR:\n")
            f.write(page_report["stderr"])
            f.write("\n")

        if page_report["parse_error"]:
            f.write(f"Parse Error: {page_report['parse_error']}\n")

        if not page_report["issues"]:
            f.write("No Pa11y issues were reported.\n\n")
            continue

        for issue in page_report["issues"]:
            f.write(f"- {issue.get('type', 'unknown').upper()}: {issue.get('message', '')}\n")
            f.write(f"  Code: {issue.get('code', '')}\n")
            f.write(f"  Selector: {issue.get('selector', '')}\n")
            f.write(f"  Context: {issue.get('context', '')}\n")

        f.write("\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("Accessibility audit complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")

raise SystemExit(command_exit_code)
