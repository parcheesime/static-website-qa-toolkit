from pathlib import Path
import argparse
import json

from qa_common import report_metadata, target_arguments


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--audit", required=True, choices=("accessibility", "lighthouse"))
known, remaining = parser.parse_known_args()
import sys
sys.argv = [sys.argv[0], *remaining]
ARGS, TARGET, REPORT_DIR = target_arguments("Ensure a browser audit produced a report")
names = {"accessibility": "Accessibility Pa11y", "lighthouse": "Lighthouse"}
path = REPORT_DIR / f"{known.audit}.json"
if path.exists():
    raise SystemExit(0)
name = names[known.audit]
reason = "Browser audit did not produce a report; local sockets or browser launching may be unavailable. No server is intentionally retained."
report = {
    "schema_version": "1.0", "audit": {"id": known.audit, "name": name, "category": "browser"},
    "metadata": report_metadata(TARGET, ARGS, name, f"scripts/{known.audit}_audit.py", "UNAVAILABLE", 0, path),
    "result": {"passed": False, "status": "NOT_RUN", "severity": "not_run", "score": None, "confidence": "high",
               "counts": {"errors": 0, "warnings": 0, "recommendations": 1}},
    "metrics": {}, "issues": {"reason": reason}, "recommendations": [reason],
}
path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
path.with_suffix(".txt").write_text(f"Schema Version: 1.0\nAudit: {name}\nProject: {ARGS.project}\nTarget: {TARGET}\nRun ID: {ARGS.run_id}\nStatus: NOT_RUN\nReason: {reason}\n", encoding="utf-8")
