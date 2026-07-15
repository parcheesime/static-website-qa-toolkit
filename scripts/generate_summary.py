from datetime import datetime
from pathlib import Path
import json
from qa_common import target_arguments

ARGS, TARGET, REPORT_DIR = target_arguments("Summarize the current static website QA run")

SUMMARY_FILE = REPORT_DIR / "summary.txt"
SUMMARY_JSON_FILE = REPORT_DIR / "summary.json"
REPORT_FILES = (
    REPORT_DIR / "css_health.json",
    REPORT_DIR / "design_audit.json",
    REPORT_DIR / "html_validate.json",
    REPORT_DIR / "eslint.json",
    REPORT_DIR / "accessibility.json",
    REPORT_DIR / "lighthouse.json",
    REPORT_DIR / "link_audit.json",
    REPORT_DIR / "stylelint.json",
    REPORT_DIR / "project_quality.json",
)


def load_report(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def site_result(reports):
    statuses = [report["result"].get("status", report["result"]["severity"].upper()) for report in reports]

    if "ERROR" in statuses:
        return "ERROR"

    if "WARNING" in statuses:
        return "WARNING"

    return "PASS"


def run_completeness(reports):
    return "INCOMPLETE" if any(report["result"].get("status") == "NOT_RUN" for report in reports) else "COMPLETE"


def format_summary(report):
    audit = report.get("audit", {})
    metadata = report["metadata"]
    result = report["result"]
    counts = result["counts"]
    metrics = report.get("metrics", {})
    recommendations = report.get("recommendations", [])
    audit_name = audit.get("name") or metadata.get("tool", "Unknown Audit")

    lines = [
        f"{audit_name}: {result.get('status', result['severity'].upper())}",
        f"  Score: {result.get('score')}",
        f"  Confidence: {result['confidence']}",
        f"  Errors: {counts['errors']}",
        f"  Warnings: {counts['warnings']}",
        f"  Recommendations: {counts['recommendations']}",
        f"  Tool Status: {metadata.get('tool_status', 'UNKNOWN')}",
        f"  Duration Ms: {metadata['duration_ms']}",
    ]

    for key, value in metrics.items():
        label = key.replace("_", " ").title()
        lines.append(f"  {label}: {value}")

    if recommendations:
        lines.append("  Recommendation Items:")
        for item in recommendations:
            lines.append(f"    - {item}")

    return "\n".join(lines)


def main():
    REPORT_DIR.mkdir(exist_ok=True)
    reports = []
    missing = []

    for path in REPORT_FILES:
        if path.exists():
            report = load_report(path)
            metadata = report.get("metadata", {})
            if metadata.get("run_id") == ARGS.run_id and metadata.get("target") == str(TARGET):
                reports.append(report)
            else:
                missing.append(path)
        else:
            missing.append(path)

    for path in missing:
        reports.append({
            "audit": {"name": path.stem.replace("_", " ").title()},
            "metadata": {"tool": path.stem, "tool_status": "MISSING", "duration_ms": 0},
            "result": {"status": "NOT_RUN", "severity": "not_run", "score": None, "confidence": "high",
                       "counts": {"errors": 0, "warnings": 0, "recommendations": 1}},
            "metrics": {}, "recommendations": ["Audit report was not produced during this run."],
        })

    with SUMMARY_FILE.open("w", encoding="utf-8") as f:
        f.write("=====================================\n")
        f.write("QA AUDIT SUMMARY\n")
        f.write("=====================================\n\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("Schema    : 1.0\nAudit     : QA Audit Summary\n")
        f.write(f"Site      : {TARGET.name}\n")
        f.write(f"Target    : {TARGET}\n")
        f.write(f"Run ID    : {ARGS.run_id}\n")
        f.write("Command   : python3 scripts/generate_summary.py\nTool Status: AVAILABLE\nConfidence: high\nDuration Ms: 0\n")
        f.write(f"Report    : {SUMMARY_FILE.resolve()}\n")
        f.write(f"Source    : JSON reports in {REPORT_DIR}\n")
        f.write("\n=====================================\n\n")

        if reports:
            f.write(f"Site Result    : {site_result(reports)}\n")
            f.write(f"Run Completeness: {run_completeness(reports)}\n")
            f.write(f"Audits         : {len(reports)}\n\n")

            for report in reports:
                f.write(format_summary(report))
                f.write("\n\n")
        else:
            f.write("No JSON reports were found.\n\n")

        if missing:
            f.write("=== Missing JSON Reports ===\n")
            for path in missing:
                f.write(f"{path}\n")

    print("QA audit summary complete.")
    print(f"Summary written to: {SUMMARY_FILE}")

    summary = {
        "schema_version": "1.0",
        "metadata": {
            "audit_name": "QA Audit Summary", "generated": datetime.now().astimezone().isoformat(),
            "project": ARGS.project, "site_name": ARGS.project, "target": str(TARGET), "run_id": ARGS.run_id,
            "command": "python3 scripts/generate_summary.py", "tool_status": "AVAILABLE", "duration_ms": 0,
            "report_file": str(SUMMARY_JSON_FILE.resolve()),
        },
        "result": {"status": site_result(reports), "site_result": site_result(reports), "run_completeness": run_completeness(reports), "audit_count": len(reports)},
        "reports": [{"audit": item.get("audit", {}).get("name"), "status": item["result"].get("status")} for item in reports],
    }
    SUMMARY_JSON_FILE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
