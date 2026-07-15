import argparse
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "reports",
    "build",
    "dist",
    "out",
    "output",
    "_site",
    "coverage",
    "vendor",
}

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_ROOT = TOOLKIT_ROOT / "reports"


def target_arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--target", required=True, help="Static website directory to audit")
    parser.add_argument("--project", required=True, help="Site/project name for report metadata")
    parser.add_argument("--run-id", required=True, help="Identifier shared by reports from one QA run")
    parser.add_argument("--report-dir", required=True, help="Output directory for this QA run")
    parser.add_argument("--browser-audits", action="store_true", help="Allow local browser audits to execute target JavaScript")
    args = parser.parse_args()
    try:
        target = Path(args.target).expanduser().resolve(strict=True)
    except OSError as error:
        parser.error(f"cannot resolve target {args.target!r}: {error}")
    if not target.is_dir():
        parser.error(f"target is not a directory: {target}")
    report_dir = Path(args.report_dir).resolve()
    if not report_dir.is_relative_to(REPORTS_ROOT):
        parser.error(f"report directory must be inside {REPORTS_ROOT}: {report_dir}")
    report_dir.mkdir(parents=True, exist_ok=True)
    return args, target, report_dir


def is_excluded(path, target):
    relative = path.relative_to(target)
    parts = relative.parts[:-1] if path.is_file() else relative.parts
    return any(part in EXCLUDED_DIRS for part in parts)


def discover(target, pattern):
    files = []
    for path in target.rglob(pattern):
        if path.is_symlink() or not path.is_file() or is_excluded(path, target):
            continue
        try:
            if path.resolve().is_relative_to(target):
                files.append(path)
        except OSError:
            continue
    return sorted(files)


def report_metadata(target, args, audit_name, command, tool_status, duration_ms, report_file):
    return {
        "schema_version": "1.0",
        "audit_name": audit_name,
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(),
        "project": args.project,
        "site_name": args.project,
        "target": str(target),
        "run_id": args.run_id,
        "command": command,
        "tool_status": tool_status,
        "duration_ms": duration_ms,
        "report_file": str(report_file.resolve()),
    }


def local_tool(name):
    candidate = TOOLKIT_ROOT / "node_modules" / ".bin" / name
    return candidate if candidate.is_file() else None


def is_minified(path):
    return path.name.endswith((".min.js", ".min.css")) or ".min." in path.name
