from datetime import datetime
from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time

SCHEMA_VERSION = "1.0"
TOOL = "lighthouse_audit.py"
LIGHTHOUSE_PACKAGE = "lighthouse@12"
AUDIT = {
    "id": "lighthouse",
    "name": "Lighthouse",
    "category": "performance",
}
CATEGORY_TARGET = 90
ERROR_THRESHOLD = 70

PROJECT = Path.cwd().name
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

REPORT_FILE = REPORT_DIR / "lighthouse.txt"
JSON_REPORT_FILE = REPORT_DIR / "lighthouse.json"
RAW_REPORT_FILE = REPORT_DIR / "lighthouse_raw.json"


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


def chrome_path():
    for command in ("chromium", "chromium-browser", "google-chrome"):
        path = shutil.which(command)

        if path:
            return path

    snap_chromium = Path("/snap/bin/chromium")

    if snap_chromium.exists():
        return str(snap_chromium)

    return ""


def category_score(category):
    score = category.get("score")

    if score is None:
        return None

    return round(score * 100)


def metric_key(category_id):
    return category_id.replace("-", "_")


def build_metrics(raw_report):
    metrics = {}

    for category_id, category in raw_report.get("categories", {}).items():
        score = category_score(category)

        if score is not None:
            metrics[metric_key(category_id)] = score

    return metrics


def build_issues(raw_report, metrics):
    issues = {
        "categories": [],
        "audits": [],
    }

    categories = raw_report.get("categories", {})
    audits = raw_report.get("audits", {})

    for category_id, score in metrics.items():
        if score < CATEGORY_TARGET:
            original_id = category_id.replace("_", "-")
            category = categories.get(original_id, {})
            issues["categories"].append(
                {
                    "id": original_id,
                    "title": category.get("title", original_id),
                    "score": score,
                    "target": CATEGORY_TARGET,
                }
            )

    for audit_id, audit in audits.items():
        score = audit.get("score")

        if score is None or score >= 0.9:
            continue

        issues["audits"].append(
            {
                "id": audit_id,
                "title": audit.get("title", audit_id),
                "score": round(score * 100),
                "score_display_mode": audit.get("scoreDisplayMode", ""),
                "description": audit.get("description", ""),
            }
        )

    return issues


port = available_port()
url = f"http://127.0.0.1:{port}/index.html"
chrome_profile = tempfile.TemporaryDirectory(prefix="lighthouse-profile-")
chrome_flags = (
    "--headless --no-sandbox --disable-gpu "
    f"--user-data-dir={chrome_profile.name}"
)
COMMAND = (
    f"npx --yes {LIGHTHOUSE_PACKAGE} "
    f"{url} --output=json --output-path={RAW_REPORT_FILE} --quiet "
    f"--chrome-flags=\"{chrome_flags}\""
)

start_time = time.perf_counter()

if RAW_REPORT_FILE.exists():
    RAW_REPORT_FILE.unlink()

server = subprocess.Popen(
    ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

command_exit_code = 0
stdout = ""
stderr = ""
raw_report = {}
parse_error = ""
server_started = wait_for_server(port)

try:
    if not server_started:
        command_exit_code = 1
        stderr = "Local HTTP server did not start before timeout."
    else:
        env = os.environ.copy()
        detected_chrome = chrome_path()

        if detected_chrome:
            env["CHROME_PATH"] = detected_chrome

        result = subprocess.run(
            [
                "npx",
                "--yes",
                LIGHTHOUSE_PACKAGE,
                url,
                "--output=json",
                f"--output-path={RAW_REPORT_FILE}",
                "--quiet",
                f"--chrome-flags={chrome_flags}",
            ],
            text=True,
            capture_output=True,
            shell=False,
            env=env,
        )
        command_exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr

        if RAW_REPORT_FILE.exists():
            try:
                raw_report = json.loads(RAW_REPORT_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                parse_error = str(error)
                command_exit_code = max(command_exit_code, 1)
        else:
            command_exit_code = max(command_exit_code, 1)
            parse_error = "Lighthouse raw report was not created."
finally:
    server.terminate()

    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()

    chrome_profile.cleanup()

duration_ms = round((time.perf_counter() - start_time) * 1000)
metrics = build_metrics(raw_report) if raw_report else {}
issues = build_issues(raw_report, metrics) if raw_report else {"categories": [], "audits": []}
main_scores = [
    score
    for key, score in metrics.items()
    if key in {"performance", "accessibility", "best_practices", "seo", "pwa"}
]
overall_score = min(main_scores) if main_scores else 0
errors = sum(1 for score in main_scores if score < ERROR_THRESHOLD)
warnings = sum(1 for score in main_scores if ERROR_THRESHOLD <= score < CATEGORY_TARGET)

if command_exit_code != 0:
    passed = False
    severity = "error"
    score = 0
    errors = max(errors, 1)
elif errors:
    passed = False
    severity = "error"
    score = overall_score
elif warnings:
    passed = True
    severity = "warning"
    score = overall_score
else:
    passed = True
    severity = "pass"
    score = overall_score

if parse_error:
    issues["runtime"] = {
        "stderr": stderr,
        "parse_error": parse_error,
    }

report = {
    "schema_version": SCHEMA_VERSION,
    "audit": AUDIT,
    "metadata": {
        "generated": TIMESTAMP,
        "project": PROJECT,
        "tool": TOOL,
        "command": COMMAND,
        "exit_code": command_exit_code,
        "duration_ms": duration_ms,
    },
    "result": {
        "passed": passed,
        "severity": severity,
        "score": score,
        "confidence": "high",
        "counts": {
            "errors": errors,
            "warnings": warnings,
            "recommendations": 0,
        },
    },
    "metrics": metrics,
    "issues": issues,
    "recommendations": [],
}

with REPORT_FILE.open("w", encoding="utf-8") as f:
    f.write("=====================================\n")
    f.write("LIGHTHOUSE REPORT\n")
    f.write("=====================================\n\n")

    f.write(f"Generated : {report['metadata']['generated']}\n")
    f.write(f"Project   : {report['metadata']['project']}\n")
    f.write(f"Tool      : {report['metadata']['tool']}\n")
    f.write(f"Command   : {report['metadata']['command']}\n")
    f.write(f"Exit Code : {report['metadata']['exit_code']}\n")
    f.write(f"Result    : {report['result']['severity'].upper()}\n")
    f.write("\n=====================================\n\n")

    f.write(f"URL: {url}\n")
    f.write(f"Overall Score: {report['result']['score']}\n")
    f.write(f"Confidence: {report['result']['confidence']}\n\n")

    f.write("=== Metrics ===\n")
    for key, value in report["metrics"].items():
        label = key.replace("_", " ").title()
        f.write(f"{label}: {value}\n")

    if stdout:
        f.write("\n=== STDOUT ===\n")
        f.write(stdout)
        f.write("\n")

    if stderr:
        f.write("\n=== STDERR ===\n")
        f.write(stderr)
        f.write("\n")

    if report["issues"].get("categories"):
        f.write("\n=== Categories Below Target ===\n")
        for issue in report["issues"]["categories"]:
            f.write(f"- {issue['title']}: {issue['score']} (target {issue['target']})\n")

    if report["issues"].get("audits"):
        f.write("\n=== Audits Below Target ===\n")
        for issue in report["issues"]["audits"]:
            f.write(f"- {issue['title']}: {issue['score']}\n")

    if report["issues"].get("runtime"):
        f.write("\n=== Runtime Issue ===\n")
        f.write(f"Parse Error: {report['issues']['runtime']['parse_error']}\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("Lighthouse audit complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")
print(f"Raw report written to: {RAW_REPORT_FILE}")

raise SystemExit(command_exit_code)
