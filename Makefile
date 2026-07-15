.PHONY: serve qa validate-target clean-legacy-reports clean-legacy-reports-dry-run

TARGET ?= .
TARGET_ABS := $(abspath $(TARGET))
PROJECT ?= $(notdir $(patsubst %/,%,$(TARGET_ABS)))
BROWSER_AUDITS ?= 0
RUN_ID := $(shell date -u +%Y%m%dT%H%M%SZ)-$(shell python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')
REPORT_DIR := $(abspath reports/runs/$(RUN_ID))
RUN_ARGS := --target "$(TARGET_ABS)" --project "$(PROJECT)" --run-id "$(RUN_ID)" --report-dir "$(REPORT_DIR)" $(if $(filter 1,$(BROWSER_AUDITS)),--browser-audits,)

serve:
	@echo "Starting local server at http://localhost:8000"
	explorer.exe "http://localhost:8000" || true
	python3 -m http.server 8000

validate-target:
	@test -d "$(TARGET_ABS)" || { echo "Error: TARGET is not a directory: $(TARGET_ABS)" >&2; exit 2; }

clean-legacy-reports-dry-run:
	@python3 scripts/clean_legacy_reports.py

clean-legacy-reports:
	@python3 scripts/clean_legacy_reports.py --apply

qa: validate-target
	@mkdir -p "$(REPORT_DIR)"
	@echo "Resolved target: $(TARGET_ABS)"
	@echo "Project name: $(PROJECT)"
	@echo "Run ID: $(RUN_ID)"
	@echo "Report directory: $(REPORT_DIR)"
	@python3 scripts/preflight.py $(RUN_ARGS)
	@echo "Running CSS health audit..."
	@python3 scripts/css_health.py $(RUN_ARGS) || true

	@echo ""
	@echo "Running design consistency audit..."
	@python3 scripts/design_audit.py $(RUN_ARGS) || true

	@echo ""
	@echo "Running HTML validation..."
	@test ! -x node_modules/.bin/html-validate || python3 scripts/html_audit.py $(RUN_ARGS) || true

	@echo ""
	@echo "Running Stylelint..."
	@python3 scripts/stylelint_audit.py $(RUN_ARGS) || true

	@echo ""
	@echo "Running ESLint..."
	@test ! -x node_modules/.bin/eslint || python3 scripts/js_audit.py $(RUN_ARGS) || true

	@echo ""
	@echo "Running accessibility audit..."
	@test "$(BROWSER_AUDITS)" != "1" || test ! -x node_modules/.bin/pa11y || python3 scripts/accessibility_audit.py $(RUN_ARGS) || true
	@python3 scripts/ensure_browser_report.py --audit accessibility $(RUN_ARGS)

	@echo ""
	@echo "Running Lighthouse audit..."
	@test "$(BROWSER_AUDITS)" != "1" || test ! -x node_modules/.bin/lighthouse || python3 scripts/lighthouse_audit.py $(RUN_ARGS) || true
	@python3 scripts/ensure_browser_report.py --audit lighthouse $(RUN_ARGS)

	@echo ""
	@echo "Running broken link audit..."
	@python3 scripts/link_audit.py $(RUN_ARGS) || true

	@echo ""
	@echo "Running project quality audit..."
	@python3 scripts/project_quality_audit.py $(RUN_ARGS) || true

	@echo ""
	@echo "Generating QA summary..."
	@python3 scripts/generate_summary.py $(RUN_ARGS)
