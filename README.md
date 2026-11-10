# Agentic Codebase Issue Verifier & Triager (Standby API)

> **Zero-proxy Standby API triaging GitHub issues, checking reproducibility, matching root-cause files in the codebase, and synthesizing regression test cases for autonomous coding agents.**

## Overview

Software repositories receive dozens of issues and bug reports every week. Most issues lack minimal reproduction examples, stack traces, or clear descriptions, forcing developers to waste time manually digging through codebases.

This Standby Actor automates GitHub issue triage and verification:

1. **Reproducibility Evaluation:** Scores issue clarity, presence of stack traces, code snippets, and environment details (0–100 scale).
2. **Codebase Correlation:** Cross-references error symbols and stack trace filenames against the repository's live file tree to identify candidate root-cause files.
3. **Automated Reproduction Test Synthesis:** Synthesizes executable regression tests (e.g. `pytest` or `jest`) reproducing the reported bug.
4. **Actionable Fix Blueprint:** Outlines targeted files, validation commands, and recommended triage actions for human developers or autonomous AI agents (Devin, Claude Code, Antigravity).

---

## Standby API Usage

When deployed in Standby mode (`usesStandbyMode: true`):

```bash
# Health check probe
curl https://<ACTOR_URL>/healthz

# Triage issue by repo and number
curl "https://<ACTOR_URL>/?repo=pallets/flask&issue=5000"

# Triage issue via direct GitHub issue URL
curl "https://<ACTOR_URL>/?issue_url=https://github.com/pallets/flask/issues/5000"
```

## Batch Run Input

```json
{
  "runMode": "BATCH",
  "repository": "pallets/flask",
  "issues": [5000, 5001]
}
```

## Pricing (Pay-Per-Event)

- **`actor-start`**: $0.0001 (Base HTTP invocation)
- **`issue-triaged`**: $0.01 (Per GitHub issue triaged, matched with file tree, and verified with test synthesis)
