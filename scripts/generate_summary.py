from datetime import datetime
from pathlib import Path
import json
from qa_common import target_arguments

ARGS, TARGET = target_arguments("Summarize the current static website QA run")

REPORT_DIR = Path("reports")
SUMMARY_FILE = REPORT_DIR / "summary.txt"
REPORT_FILES = (
    REPORT_DIR / "css_health.json",
    REPORT_DIR / "design_audit.json",
    REPORT_DIR / "html_validate.json",
    REPORT_DIR / "eslint.json",
    REPORT_DIR / "accessibility.json",
    REPORT_DIR / "lighthouse.json",
    REPORT_DIR / "link_audit.json",
)


def load_report(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def overall_status(reports):
    severities = [report["result"]["severity"] for report in reports]

    if "error" in severities:
        return "ERROR"

    if "warning" in severities:
        return "WARNING"

    return "PASS"


def format_summary(report):
    audit = report.get("audit", {})
    metadata = report["metadata"]
    result = report["result"]
    counts = result["counts"]
    metrics = report.get("metrics", {})
    recommendations = report.get("recommendations", [])
    audit_name = audit.get("name", metadata["tool"])

    lines = [
        f"{audit_name}: {result['severity'].upper()}",
        f"  Score: {result['score']}",
        f"  Confidence: {result['confidence']}",
        f"  Errors: {counts['errors']}",
        f"  Warnings: {counts['warnings']}",
        f"  Recommendations: {counts['recommendations']}",
        f"  Exit Code: {metadata['exit_code']}",
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

    with SUMMARY_FILE.open("w", encoding="utf-8") as f:
        f.write("=====================================\n")
        f.write("QA AUDIT SUMMARY\n")
        f.write("=====================================\n\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Site      : {TARGET.name}\n")
        f.write(f"Target    : {TARGET}\n")
        f.write(f"Run ID    : {ARGS.run_id}\n")
        f.write(f"Source    : JSON reports in {REPORT_DIR}\n")
        f.write("\n=====================================\n\n")

        if reports:
            f.write(f"Overall Result : {overall_status(reports)}\n")
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


if __name__ == "__main__":
    main()
