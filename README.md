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

Install dependencies:

```bash
npm install
```

Run the complete QA workflow:

```bash
make qa
```

To audit a separate static website repository while keeping the toolkit as the
working directory, pass its path with `TARGET`:

```bash
make qa TARGET=../barkey-pet-sitting
```

`TARGET` defaults to `.`, so `make qa` continues to audit the current directory.
The resolved target must exist and be a directory. Reports remain in this
toolkit's `reports/` directory.

or

```bash
npm run qa
```

Reports are generated in the `reports/` directory.

## Project Structure

```text
scripts/
    *_audit.py
    generate_summary.py

reports/
    Generated reports

examples/
    Sample reports

docs/
    Documentation
```

## Roadmap

### Completed

* HTML Validation
* CSS Health
* JavaScript Lint
* Accessibility
* Lighthouse
* Broken Link Audit
* Design Consistency

### Planned

* Asset Audit
* SEO Audit
* Security Audit
* Project Quality Audit
* Visual Regression Testing
* Historical Report Dashboard
* Multi-site Monitoring

## Vision

This project began as a reusable QA workflow for personal websites and client projects. The long-term goal is to evolve it into a complete static website quality platform capable of monitoring multiple websites, tracking quality over time, and assisting with ongoing maintenance through structured reporting and automation.

## Why another QA toolkit?

Most website QA tools focus on one area, such as linting, accessibility, or performance. This project aims to unify technical validation, engineering quality, and design consistency into a single workflow with a shared reporting schema. The goal is to make routine website quality checks repeatable, extensible, and useful for both developers and AI-assisted review.
