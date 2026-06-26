from datetime import datetime
from pathlib import Path
import json
import subprocess
import time

SCHEMA_VERSION = "1.0"
TOOL = "js_audit.py"
COMMAND = "npx eslint ."
AUDIT = {
    "id": "javascript-lint",
    "name": "JavaScript Lint",
    "category": "javascript",
}

PROJECT = Path.cwd().name
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

REPORT_FILE = REPORT_DIR / "eslint.txt"
JSON_REPORT_FILE = REPORT_DIR / "eslint.json"

start_time = time.perf_counter()

result = subprocess.run(
    ["npx", "eslint", "."],
    text=True,
    capture_output=True,
    shell=False,
)

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
    f.write("ESLINT REPORT\n")
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
        f.write("No ESLint issues were reported.\n")

with JSON_REPORT_FILE.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
    f.write("\n")

print("ESLint audit complete.")
print(f"Report written to: {REPORT_FILE}")
print(f"JSON report written to: {JSON_REPORT_FILE}")

raise SystemExit(exit_code)
