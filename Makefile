.PHONY: serve qa validate-target

TARGET ?= .
TARGET_ABS := $(abspath $(TARGET))
RUN_ID := $(shell date -u +%Y%m%dT%H%M%SZ)-$(shell date +%s)

serve:
	@echo "Starting local server at http://localhost:8000"
	explorer.exe "http://localhost:8000" || true
	python3 -m http.server 8000

validate-target:
	@test -d "$(TARGET_ABS)" || { echo "Error: TARGET is not a directory: $(TARGET_ABS)" >&2; exit 2; }

qa: validate-target
	@echo "Auditing target: $(TARGET_ABS)"
	@echo "Running CSS health audit..."
	@python3 scripts/css_health.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Running design consistency audit..."
	@python3 scripts/design_audit.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Running HTML validation..."
	@python3 scripts/html_audit.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Running Stylelint..."
	@find "$(TARGET_ABS)" -type f -name '*.css' \
		-not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/reports/*' \
		-not -path '*/build/*' -not -path '*/dist/*' -not -path '*/out/*' -not -path '*/output/*' \
		-print0 | xargs -0 -r npx --no-install stylelint

	@echo ""
	@echo "Running ESLint..."
	@python3 scripts/js_audit.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Running accessibility audit..."
	@python3 scripts/accessibility_audit.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Running Lighthouse audit..."
	@python3 scripts/lighthouse_audit.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Running broken link audit..."
	@python3 scripts/link_audit.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"

	@echo ""
	@echo "Generating QA summary..."
	@python3 scripts/generate_summary.py --target "$(TARGET_ABS)" --run-id "$(RUN_ID)"
