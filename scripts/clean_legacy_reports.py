from pathlib import Path
import argparse

from qa_common import REPORTS_ROOT


KNOWN_STEMS = {
    "accessibility", "css_health", "design_audit", "eslint", "html_validate",
    "lighthouse", "lighthouse_raw", "link_audit", "project_quality", "stylelint", "summary",
}
parser = argparse.ArgumentParser(description="Remove known legacy flat QA reports")
parser.add_argument("--apply", action="store_true", help="Delete listed files; default is dry-run")
args = parser.parse_args()
files = sorted(path for path in REPORTS_ROOT.iterdir() if path.is_file() and path.stem in KNOWN_STEMS and path.suffix in {".txt", ".json"})
print("Legacy flat reports selected:")
for path in files:
    print(path)
if not files:
    print("(none)")
if args.apply:
    for path in files:
        path.unlink()
    print(f"Removed {len(files)} known legacy report file(s).")
else:
    print("Dry run only. Re-run with --apply to remove these files.")
