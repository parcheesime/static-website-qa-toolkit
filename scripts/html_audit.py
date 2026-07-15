from datetime import datetime
from pathlib import Path
import json
import subprocess
import time
from qa_common import discover, report_metadata, target_arguments

SCHEMA_VERSION = "1.0"
TOOL = "html_audit.py"
AUDIT = {
    "id": "html-validation",
    "name": "HTML Validation",
    "category": "html",
}

ARGS, TARGET = target_arguments("Validate HTML files in a static website")
HTML_FILES = discover(TARGET, "*.html")
COMMAND_ARGS = ["npx", "--no-install", "html-validate", *[str(path) for path in HTML_FILES]]
COMMAND = " ".join(COMMAND_ARGS)
PROJECT = TARGET.name
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

REPORT_FILE = REPORT_DIR / "html_validate.txt"
JSON_REPORT_FILE = REPORT_DIR / "html_validate.json"

start_time = time.perf_counter()

if HTML_FILES:
    result = subprocess.run(
        COMMAND_ARGS,
        text=True,
        capture_output=True,
        shell=False,
    )
else:
    result = subprocess.CompletedProcess(COMMAND_ARGS, 0, "", "")

exit_code = result.returncode
duration_ms = round((time.perf_counter() - start_time) * 1000)
has_output = bool(result.stdout or result.stderr)

if exit_code != 0:
    passed = False
    severity = "error"
    score = 0
    errors = 1
    warnings = 0
elif has_output:
    passed = True
    severity = "warning"
    score = 90
    errors = 0
    warnings = 1
else:
    passed = True
    severity = "pass"
    score = 100
    errors = 0
    warnings = 0

report = {
    "schema_version": SCHEMA_VERSION,
    "audit": AUDIT,
    "metadata": {
        "generated": TIMESTAMP,
        **report_metadata(TARGET, ARGS.run_id),
        "tool": TOOL,
        "command": COMMAND,
        "exit_code": exit_code,
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
    "metrics": {
        "stdout_lines": len(result.stdout.splitlines()),
        "stderr_lines": len(result.stderr.splitlines()),
        "has_output": has_output,
    },
    "issues": {
        "stdout": result.stdout,
        "stderr": result.stderr,
    },
    "recommendations": [],
}

with REPORT_FILE.open("w", encoding="utf-8") as f:
    f.write("=====================================\n")
    f.write("HTML VALIDATE REPORT\n")
    f.write("=====================================\n\n")

    f.write(f"Generated : {report['metadata']['generated']}\n")
    f.write(f"Project   : {report['metadata']['project']}\n")
    f.write(f"Tool      : {report['metadata']['tool']}\n")
    f.write(f"Command   : {report['metadata']['command']}\n")
    f.write(f"Exit Code : {report['metadata']['exit_code']}\n")
    f.write(f"Result    : {report['result']['severity'].upper()}\n")
    f.write("\n=====================================\n\n")

    if report["issues"]["stdout"]:
        f.write("=== STDOUT ===\n")
        f.write(report["issues"]["stdout"])
        f.write("\n")

    if report["issues"]["stderr"]:
        f.write("=== STDERR ===\n")
        f.write(report["issues"]["stderr"])
        f.write("\n")

    if not report["metrics"]["has_output"]:
        f.write("No output. HTML validation passed.\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("HTML validation complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")

raise SystemExit(exit_code)
