from pathlib import Path
import json
import subprocess
import time

from qa_common import discover, is_minified, local_tool, report_metadata, target_arguments


ARGS, TARGET, REPORT_DIR = target_arguments("Lint CSS files in a static website")
AUDIT = {"id": "stylelint", "name": "Stylelint", "category": "css"}
JSON_FILE = REPORT_DIR / "stylelint.json"
TEXT_FILE = REPORT_DIR / "stylelint.txt"
files = [path for path in discover(TARGET, "*.css") if not is_minified(path)]
tool = local_tool("stylelint")
config = Path(__file__).resolve().parent.parent / "stylelint.config.cjs"
command_args = [str(tool), "--config", str(config), *map(str, files)] if tool else []
command = " ".join(command_args) or "node_modules/.bin/stylelint"
start = time.perf_counter()

if not tool:
    status, tool_status, code, stdout, stderr = "NOT_RUN", "MISSING", None, "", "Run npm install."
elif not files:
    status, tool_status, code, stdout, stderr = "NOT_APPLICABLE", "AVAILABLE", 0, "", ""
else:
    result = subprocess.run(command_args, text=True, capture_output=True, shell=False, cwd=Path(__file__).parent.parent)
    code, stdout, stderr = result.returncode, result.stdout, result.stderr
    status, tool_status = ("PASS" if code == 0 else "ERROR"), "AVAILABLE"

duration = round((time.perf_counter() - start) * 1000)
severity = {"PASS": "pass", "ERROR": "error", "NOT_RUN": "not_run", "NOT_APPLICABLE": "not_applicable"}[status]
report = {
    "schema_version": "1.0", "audit": AUDIT,
    "metadata": report_metadata(TARGET, ARGS, AUDIT["name"], command, tool_status, duration, JSON_FILE),
    "result": {"passed": status in {"PASS", "NOT_APPLICABLE"}, "status": status, "severity": severity,
               "score": 100 if status == "PASS" else None, "confidence": "high",
               "counts": {"errors": 1 if status == "ERROR" else 0, "warnings": 0,
                          "recommendations": 1 if status == "NOT_RUN" else 0}},
    "metrics": {"files_checked": len(files)}, "issues": {"stdout": stdout, "stderr": stderr},
    "recommendations": ["Run npm install in the QA toolkit repository."] if status == "NOT_RUN" else [],
}
JSON_FILE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
TEXT_FILE.write_text(f"Schema Version: 1.0\nAudit: Stylelint\nProject: {ARGS.project}\nTarget: {TARGET}\nRun ID: {ARGS.run_id}\nCommand: {command}\nStatus: {status}\nTool Status: {tool_status}\nConfidence: high\nDuration Ms: {duration}\nReport: {TEXT_FILE.resolve()}\n\n{stdout}{stderr}", encoding="utf-8")
print(f"Stylelint audit: {status}")
