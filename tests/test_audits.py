import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qa-tests-")
        self.target = Path(self.temp.name) / "site"
        self.target.mkdir()
        self.run_id = f"test-{uuid.uuid4().hex}"
        self.report_dir = ROOT / "reports" / "runs" / self.run_id

    def tearDown(self):
        self.temp.cleanup()
        shutil.rmtree(self.report_dir, ignore_errors=True)

    def run_audit(self, script, *extra):
        command = ["python3", str(SCRIPTS / script), "--target", str(self.target), "--project", "fixture",
                   "--run-id", self.run_id, "--report-dir", str(self.report_dir), *extra]
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)

    def report(self, name):
        return json.loads((self.report_dir / name).read_text())

    @unittest.skipUnless((ROOT / "node_modules/.bin/eslint").exists(), "local ESLint is not installed")
    def test_eslint_uses_toolkit_config_and_browser_globals(self):
        (self.target / "site.js").write_text("document.addEventListener('click', () => console.log(window.location));\n")
        self.run_audit("js_audit.py")
        self.assertEqual(self.report("eslint.json")["result"]["status"], "PASS")
        (self.target / "site.js").write_text("const actuallyUnused = 1;\n")
        self.run_audit("js_audit.py")
        self.assertEqual(self.report("eslint.json")["result"]["status"], "WARNING")

    @unittest.skipUnless((ROOT / "node_modules/.bin/stylelint").exists(), "local Stylelint is not installed")
    def test_stylelint_modern_css_and_invalid_property(self):
        css = self.target / "site.css"
        css.write_text(":root { --brand: #369; }\n.card { width: clamp(1rem, 5vw, 4rem); color: color-mix(in srgb, var(--brand), white); }\n")
        self.run_audit("stylelint_audit.py")
        self.assertEqual(self.report("stylelint.json")["result"]["status"], "PASS")
        css.write_text(".card { colr: red; }\n")
        self.run_audit("stylelint_audit.py")
        self.assertEqual(self.report("stylelint.json")["result"]["status"], "ERROR")

    def test_project_quality_selector_and_asset_regressions(self):
        (self.target / "index.html").write_text('<link rel="manifest" href="site.webmanifest"><div class="used"></div><img data-hover-src="hover.png">')
        (self.target / "site.css").write_text(".used { color: #FAF6EE; background: url('./bg.png'); }\n.dup:hover, .dup { color: #FFFFFF; }\n.dynamic { color: #C96F32; }\n.state:hover { opacity: .8; }\n")
        (self.target / "site.js").write_text("document.querySelector('.dynamic'); element.classList.toggle('dup');\n")
        (self.target / "site.webmanifest").write_text('{"icons":[{"src":"icon.png"}]}')
        for name in ("hover.png", "bg.png", "icon.png", "unused.png"):
            (self.target / name).write_bytes(b"asset")
        self.run_audit("project_quality_audit.py")
        issues = self.report("project_quality.json")["issues"]
        all_selectors = sum(issues["unused_css_selectors"].values(), [])
        self.assertFalse(any(item["selector"].startswith("#FA") or item["selector"] == "#FFFFFF" for item in all_selectors))
        self.assertFalse(any(item["selector"] in {".dynamic", ".dup"} for item in all_selectors))
        self.assertTrue(any(item["selector"] == ".state" for item in issues["unused_css_selectors"]["low_confidence_informational"]))
        unused = {item["asset_path"] for item in issues["unused_assets"]}
        self.assertEqual(unused, {"unused.png"})

    def test_external_links_are_informational(self):
        (self.target / "index.html").write_text('<a href="https://example.invalid/">External</a>')
        self.run_audit("link_audit.py")
        report = self.report("link_audit.json")
        self.assertEqual(report["result"]["status"], "PASS")
        self.assertEqual(report["metrics"]["skipped_links"], 1)

    def test_preflight_blocks_browser_audits_by_default(self):
        self.run_audit("preflight.py")
        self.assertEqual(self.report("accessibility.json")["result"]["status"], "NOT_RUN")
        self.assertEqual(self.report("lighthouse.json")["metadata"]["tool_status"], "BLOCKED")

    def test_preflight_tracks_html_validate_and_browser_opt_in(self):
        self.run_audit("preflight.py")
        preflight = self.report("preflight.json")
        self.assertIn("html-validate", preflight["tools"])
        package = json.loads((ROOT / "package.json").read_text())
        self.assertIn("html-validate", package["devDependencies"])
        dry = subprocess.run(["make", "-n", "qa", f"TARGET={self.target}", "BROWSER_AUDITS=1"], cwd=ROOT,
                             text=True, capture_output=True, check=True).stdout
        self.assertIn("--browser-audits", dry)
        self.assertIn("accessibility_audit.py", dry)
        self.assertIn("lighthouse_audit.py", dry)

    def test_browser_unavailable_fallback_is_not_run(self):
        self.run_audit("ensure_browser_report.py", "--audit", "accessibility", "--browser-audits")
        report = self.report("accessibility.json")
        self.assertEqual(report["result"]["status"], "NOT_RUN")
        self.assertIn("sockets or browser", report["issues"]["reason"])

    def test_legacy_cleanup_dry_run_preserves_runs(self):
        marker = self.report_dir / "keep.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("keep")
        subprocess.run(["python3", str(SCRIPTS / "clean_legacy_reports.py")], cwd=ROOT, check=True, capture_output=True)
        self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
