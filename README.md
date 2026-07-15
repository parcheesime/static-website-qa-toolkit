# Static Website QA Toolkit

A reusable quality assurance toolkit for static websites.

The Static Website QA Toolkit provides a standardized workflow for auditing HTML, CSS, JavaScript, accessibility, performance, links, and design consistency before deployment. It is designed for portfolios, GitHub Pages sites, and client websites, with an emphasis on producing clear reports for both humans and automated tooling.

## Goals

* Standardize website QA before every deployment.
* Generate human-readable and machine-readable reports.
* Make audits reusable across multiple static website projects.
* Build a foundation for automated website monitoring and maintenance.
* Support AI-assisted review using structured JSON reports.

## Features

### Current Audits

* HTML Validation
* CSS Health
* JavaScript Lint
* Accessibility (Pa11y)
* Lighthouse
* Broken Link Audit
* Design Consistency

### Reporting

Each audit produces:

* Human-readable text reports (`.txt`)
* Structured JSON reports (`.json`)

A summary report combines all audit results into a single deployment overview.

Example:

```text
reports/
    summary.txt
    html_validate.txt
    html_validate.json
    css_health.txt
    css_health.json
    ...
```

## Report Schema

All audits use a common JSON schema.

```text
schema_version
audit
metadata
result
metrics
issues
recommendations
```

This shared schema allows new audits to integrate automatically with the summary generator and future dashboards.

## Running the Toolkit

### One-time setup

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required Python and Node.js dependencies:

```bash
pip install -r requirements.txt
npm install
```

The QA run performs a local dependency preflight for ESLint, Stylelint,
html-validate, Pa11y, and Lighthouse. It never downloads tools automatically.
If a required executable is missing, that audit is recorded as `NOT_RUN` with
`npm install` as the setup command, while independent audits continue.
ESLint and Stylelint use the toolkit-owned `eslint.config.js` and
`stylelint.config.cjs`; target repositories do not need lint configuration.

---

### Auditing the Current Repository

If you are running QA against the current repository:

```bash
make qa
```

By default, the toolkit audits the current working directory.

---

### Auditing Another Static Website

The toolkit can also audit another static website repository without modifying it.

Example directory layout:

```text
~/dev/
├── static-website-qa-toolkit/
├── barkey-pet-sitting/
├── abc-design/
└── pariline-studio/
```

From the toolkit directory:

```bash
make qa TARGET=../barkey-pet-sitting
```

This secure default records Pa11y and Lighthouse as `NOT_RUN`, because rendering
an untrusted target can execute its JavaScript. To explicitly allow local browser
execution, use:

```bash
make qa TARGET=../barkey-pet-sitting BROWSER_AUDITS=1
```

The opt-in serves `TARGET` on localhost, blocks non-local hostname resolution in
the browser configuration, and stops each local server after its audit. It still
allows the target's JavaScript to execute locally. If sockets or browser startup
are unavailable, the browser audit remains incomplete and must not leave a server
running.

or

```bash
make qa TARGET=../abc-design
```

The target repository is audited in place and is never modified by the toolkit.

---

### Reports

Each QA invocation writes to a unique run directory in the toolkit:

Example:

```text
reports/
└── runs/
    └── <run-id>/
        ├── preflight.json
        ├── summary.txt
        ├── summary.json
        ├── html_validate.json
        ├── css_health.json
        └── ...
```

The startup output prints the run ID and exact report directory; use that
directory to identify the latest report. A `reports/latest/` alias is not
currently created. Every report identifies the target, project, and run ID.

Statuses have these meanings:

- `PASS`: the audit ran without configured failures.
- `WARNING`: the audit ran and found reviewable issues.
- `ERROR`: the audit failed or found configured hard failures.
- `NOT_RUN`: the audit could not run, usually because a tool is missing.
- `NOT_APPLICABLE`: the target has no relevant files for that audit.

The summary separates `Site Result` from `Run Completeness`. Disabled or missing
audits make completeness `INCOMPLETE` without making the website fail. Findings
from completed site audits determine the site result.

The project-quality audit reports likely unused assets, unused CSS selectors,
and unreferenced JavaScript functions. Findings are grouped by confidence and
remain heuristics requiring manual review. The toolkit never deletes reported
files or code.

Preview removal of known legacy flat reports with:

```bash
make clean-legacy-reports-dry-run
```

After reviewing the list, remove only those known generated files with:

```bash
make clean-legacy-reports
```

Cleanup never traverses or removes `reports/runs/`, and unknown files are kept.

The audited website itself is not modified and no report files are written into the target project.

---

### Typical Workflow

1. Make changes in the website project.
2. Commit or save your work.
3. Switch to the QA toolkit repository.
4. Run the audit:

```bash
make qa TARGET=../barkey-pet-sitting
```

5. Review the reports in:

```text
reports/runs/<run-id>/
```

6. Return to the website project and fix any issues.
7. Repeat until the reports are clean.

---

### Notes

- The toolkit never modifies the audited website.
- Reports are written only to the toolkit repository.
- External websites and third-party services are not contacted automatically.
- Some audits (such as Lighthouse or Pa11y) require a locally running web server.
