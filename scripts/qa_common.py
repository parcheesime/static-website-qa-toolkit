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
    "public/build",
}


def target_arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--target", required=True, help="Static website directory to audit")
    parser.add_argument("--run-id", default="", help="Identifier shared by reports from one QA run")
    args = parser.parse_args()
    try:
        target = Path(args.target).expanduser().resolve(strict=True)
    except OSError as error:
        parser.error(f"cannot resolve target {args.target!r}: {error}")
    if not target.is_dir():
        parser.error(f"target is not a directory: {target}")
    return args, target


def is_excluded(path, target):
    relative = path.relative_to(target)
    parts = relative.parts[:-1] if path.is_file() else relative.parts
    return any(part in EXCLUDED_DIRS for part in parts)


def discover(target, pattern):
    return sorted(path for path in target.rglob(pattern) if path.is_file() and not is_excluded(path, target))


def report_metadata(target, run_id):
    return {
        "project": target.name,
        "site_name": target.name,
        "target": str(target),
        "run_id": run_id,
    }
