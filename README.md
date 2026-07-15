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

or

```bash
make qa TARGET=../abc-design
```

The target repository is audited in place and is never modified by the toolkit.

---

### Reports

Audit reports are generated in the toolkit's `reports/` directory.

Example:

```text
reports/
├── summary.txt
├── summary.json
├── html_validation.txt
├── html_validation.json
├── css_health.txt
├── css_health.json
└── ...
```

Each report includes metadata identifying the audited target repository.

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
reports/
```

6. Return to the website project and fix any issues.
7. Repeat until the reports are clean.

---

### Notes

- The toolkit never modifies the audited website.
- Reports are written only to the toolkit repository.
- External websites and third-party services are not contacted unless explicitly required by an audit.
- Some audits (such as Lighthouse or Pa11y) require a locally running web server.
