from pathlib import Path
import importlib.util
import json
import time

from qa_common import local_tool, report_metadata, target_arguments


ARGS, TARGET, REPORT_DIR = target_arguments("Check local QA dependencies")
start = time.perf_counter()
TOOLS = {
    "eslint": ("eslint", "eslint.json", "JavaScript Lint"),
    "stylelint": ("stylelint", "stylelint.json", "Stylelint"),
    "html-validate": ("html-validate", "html_validate.json", "HTML Validation"),
    "pa11y": ("pa11y", "accessibility.json", "Accessibility Pa11y"),
    "lighthouse": ("lighthouse", "lighthouse.json", "Lighthouse"),
}
PYTHON_MODULES = ("argparse", "html.parser", "json", "pathlib")


def not_run_report(tool, filename, audit_name, reason="missing dependency"):
    report_file = REPORT_DIR / filename
    command = str(Path("node_modules/.bin") / tool)
    duration = round((time.perf_counter() - start) * 1000)
    report = {
        "schema_version": "1.0",
        "audit": {"id": tool, "name": audit_name, "category": "tooling"},
        "metadata": report_metadata(TARGET, ARGS, audit_name, command, "MISSING" if reason == "missing dependency" else "BLOCKED", duration, report_file),
        "result": {
            "passed": False,
            "status": "NOT_RUN",
            "severity": "not_run",
            "score": None,
            "confidence": "high",
            "counts": {"errors": 0, "warnings": 0, "recommendations": 1},
        },
        "metrics": {},
        "issues": {"reason": reason, "missing_dependency": tool if reason == "missing dependency" else None},
        "recommendations": ["Run npm install in the QA toolkit repository."] if reason == "missing dependency" else [reason],
    }
    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report_file.with_suffix(".txt").write_text(
        f"Schema Version: 1.0\nAudit: {audit_name}\nProject: {ARGS.project}\nTarget: {TARGET}\n"
        f"Run ID: {ARGS.run_id}\nStatus: NOT_RUN\nTool Status: {'MISSING' if reason == 'missing dependency' else 'BLOCKED'}\n"
        f"Command: {command}\nConfidence: high\nDuration Ms: {duration}\nReport: {report_file.with_suffix('.txt').resolve()}\n"
        + ("Setup: npm install\n" if reason == "missing dependency" else f"Reason: {reason}\n"),
        encoding="utf-8",
    )


tools = {}
for name, (binary, filename, audit_name) in TOOLS.items():
    available = local_tool(binary) is not None
    browser_tool = binary in {"pa11y", "lighthouse"}
    enabled = not browser_tool or ARGS.browser_audits
    tools[name] = {"available": available, "path": str(local_tool(binary) or ""), "audit_enabled": enabled}
    if browser_tool and not enabled:
        not_run_report(binary, filename, audit_name, "Disabled because browser audits can execute JavaScript from the untrusted target.")
    elif not available:
        not_run_report(binary, filename, audit_name)

modules = {name: importlib.util.find_spec(name) is not None for name in PYTHON_MODULES}
output = {
    "schema_version": "1.0",
    "project": ARGS.project,
    "target": str(TARGET),
    "run_id": ARGS.run_id,
    "tools": tools,
    "python_modules": modules,
    "setup": "npm install",
}
(REPORT_DIR / "preflight.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
print("Dependency preflight complete.")
for name, details in tools.items():
    state = "BLOCKED_FOR_UNTRUSTED_TARGET" if not details["audit_enabled"] else ("AVAILABLE" if details["available"] else "MISSING")
    print(f"  {name}: {state}")
