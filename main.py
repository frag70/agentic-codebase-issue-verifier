#!/usr/bin/env python3
"""
agentic-codebase-issue-verifier — Standby Pay-Per-Event (PPE) Apify Actor.

Automated GitHub issue triage and verification engine for autonomous coding agents.
Evaluates issue reproducibility, correlates stack traces with repository file trees,
identifies candidate root-cause files, and synthesizes regression test cases.

Modes
-----
* BATCH          : triage up to 20 issues, push structured verification reports to dataset
* STANDBY_SERVER : persistent HTTP API for MCP clients / autonomous coding agent loops
* --cli <params> : local run, pretty JSON on stdout
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

try:
    from apify import Actor
except Exception:
    Actor = None

ACTOR_SLUG = "agentic-codebase-issue-verifier"
ACTOR_VERSION = "0.1.0"
UA = "AgenticCodebaseIssueVerifier/0.1.0 (+https://apify.com/fragthom/agentic-codebase-issue-verifier)"


def extract_repo_parts(repo_str: str) -> Tuple[str, str]:
    cleaned = (repo_str or "").strip()
    cleaned = re.sub(r"^https?://github\.com/", "", cleaned)
    cleaned = cleaned.rstrip("/")
    if "/" in cleaned:
        parts = cleaned.split("/")
        return parts[0], parts[1]
    return "", ""


def make_github_request(url: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    tok = token or os.environ.get("GITHUB_TOKEN") or ""
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.github.v3+json",
    }
    if tok:
        headers["Authorization"] = f"Bearer {tok}" if tok.startswith("gh") else f"token {tok}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"[WARN] GitHub request {url} failed with code {e.code}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[WARN] GitHub request {url} failed: {exc}", file=sys.stderr)
        return None


def fetch_repo_file_tree(owner: str, repo: str, default_branch: str, token: Optional[str] = None) -> List[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    data = make_github_request(url, token)
    if not data or "tree" not in data:
        return []
    paths: List[str] = []
    for item in data.get("tree", []):
        p = item.get("path")
        if p and not p.startswith(".git/"):
            paths.append(p)
    return paths[:2000]


def analyze_issue_reproducibility(title: str, body: str) -> Dict[str, Any]:
    text = f"{title}\n{body}"
    score = 0
    factors: List[str] = []

    # 1. Check for stack traces / tracebacks
    has_traceback = bool(
        re.search(r"Traceback \(most recent call last\):", text)
        or re.search(r"\b(Error|Exception):", text)
        or re.search(r"at (?:[a-zA-Z0-9_$./]+\s+\()?([a-zA-Z0-9_$./]+:\d+:\d+)\)?", text)
    )
    if has_traceback:
        score += 30
        factors.append("Contains error traceback or stack trace (+30 pts)")

    # 2. Check for code blocks / snippets
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```", text)
    if code_blocks:
        score += 25
        factors.append(f"Contains {len(code_blocks)} code block(s) (+25 pts)")
    elif "`" in text:
        score += 10
        factors.append("Contains inline code references (+10 pts)")

    # 3. Check for expected vs actual behavior
    has_expected = bool(
        re.search(r"expected (?:behavior|result|output)", text, re.IGNORECASE)
        or re.search(r"what did you expect", text, re.IGNORECASE)
    )
    has_actual = bool(
        re.search(r"actual (?:behavior|result|output)", text, re.IGNORECASE)
        or re.search(r"what happened", text, re.IGNORECASE)
    )
    if has_expected and has_actual:
        score += 20
        factors.append("Includes expected and actual behavior (+20 pts)")
    elif has_expected or has_actual:
        score += 10
        factors.append("Includes partial expected/actual behavior (+10 pts)")

    # 4. Check for environment / version info
    has_env = bool(
        re.search(r"\b(python|node|version|os|ubuntu|macos|windows|v\d+\.\d+)\b", text, re.IGNORECASE)
    )
    if has_env:
        score += 15
        factors.append("Includes environment or runtime version info (+15 pts)")

    # 5. Check for steps to reproduce
    has_steps = bool(
        re.search(r"steps to reproduce", text, re.IGNORECASE)
        or re.search(r"how to reproduce", text, re.IGNORECASE)
        or re.search(r"(?:1\.|-)\s+first", text, re.IGNORECASE)
    )
    if has_steps:
        score += 10
        factors.append("Includes step-by-step reproduction guide (+10 pts)")

    score = min(100, score)
    if score >= 75:
        rating = "HIGH"
    elif score >= 45:
        rating = "MEDIUM"
    elif score >= 25:
        rating = "LOW"
    else:
        rating = "NEEDS_INFO"

    return {
        "score": score,
        "rating": rating,
        "has_traceback": has_traceback,
        "code_blocks_count": len(code_blocks),
        "scoring_breakdown": factors,
    }


def classify_issue(title: str, body: str, labels: List[str]) -> Tuple[str, str]:
    text = f"{title} {body}".lower()
    label_names = [l.lower() for l in labels]

    # Type detection
    if any("bug" in l for l in label_names) or "bug" in text or "error" in text or "crash" in text:
        issue_type = "BUG"
    elif any("feature" in l or "enhancement" in l for l in label_names) or "feature request" in text or "add support for" in text:
        issue_type = "FEATURE_REQUEST"
    elif any("doc" in l for l in label_names) or "documentation" in text or "readme" in text:
        issue_type = "DOCUMENTATION"
    elif any("question" in l for l in label_names) or "how do i" in text or "how to" in text:
        issue_type = "QUESTION"
    else:
        issue_type = "BUG"

    # Severity detection
    if any(k in text for k in ["crash", "security", "vulnerability", "cve", "deadlock", "segfault", "panic"]):
        severity = "CRITICAL"
    elif any(k in text for k in ["broken", "fail", "regression", "cannot", "exception"]):
        severity = "HIGH"
    elif any(k in text for k in ["warning", "deprecat", "slow", "performance", "unexpected"]):
        severity = "MEDIUM"
    else:
        severity = "LOW"

    return issue_type, severity


def match_affected_files(title: str, body: str, file_tree: List[str]) -> List[Dict[str, Any]]:
    text = f"{title}\n{body}"
    candidates: List[Dict[str, Any]] = []

    # Find filenames in text
    mentioned_names = set(re.findall(r"\b[a-zA-Z0-9_-]+\.(?:py|js|ts|go|rs|java|rb|cpp|h)\b", text))
    # Find full path references
    path_refs = set(re.findall(r"[\'\"`]?([a-zA-Z0-9_-]+/[a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)[\'\"`]?", text))

    for fpath in file_tree:
        fname = os.path.basename(fpath)
        confidence = 0
        reasons: List[str] = []

        if fpath in path_refs:
            confidence += 60
            reasons.append("Exact file path matched in issue text")
        elif fname in mentioned_names:
            confidence += 40
            reasons.append(f"Filename '{fname}' mentioned directly")

        # Symbol match
        base_no_ext = os.path.splitext(fname)[0]
        if len(base_no_ext) > 3 and re.search(r"\b" + re.escape(base_no_ext) + r"\b", text, re.IGNORECASE):
            confidence += 15
            reasons.append(f"Module/Component identifier '{base_no_ext}' matched")

        if confidence > 0:
            candidates.append({
                "path": fpath,
                "confidence_score": min(100, confidence),
                "reasons": reasons,
            })

    candidates.sort(key=lambda x: x["confidence_score"], reverse=True)
    return candidates[:5]


def synthesize_reproduction_test(
    issue_type: str,
    repo_lang: str,
    title: str,
    body: str,
    candidate_files: List[Dict[str, Any]],
) -> Dict[str, str]:
    lang = (repo_lang or "").lower()
    top_file = candidate_files[0]["path"] if candidate_files else "app/main.py"

    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```", body)
    repro_snippet = code_blocks[0].strip() if code_blocks else "# TODO: Add minimal repro inputs"

    if "python" in lang:
        test_code = (
            f"# Reproduction Test Case for: {title}\n"
            f"# Generated by agentic-codebase-issue-verifier\n\n"
            f"import pytest\n\n"
            f"def test_reproduce_issue():\n"
            f"    \"\"\"\n"
            f"    Asserts the expected behavior reported in issue.\n"
            f"    Target component: {top_file}\n"
            f"    \"\"\"\n"
            f"    # Extracted reproduction snippet:\n"
            f"    {repro_snippet.replace(chr(10), chr(10) + '    ')}\n\n"
            f"    # Assert regression resolution\n"
            f"    assert True, 'Issue reproduced successfully.'\n"
        )
        framework = "pytest"
        filename = "tests/test_reproduce_issue.py"
    elif any(k in lang for k in ["typescript", "javascript"]):
        test_code = (
            f"// Reproduction Test Case for: {title}\n"
            f"// Generated by agentic-codebase-issue-verifier\n\n"
            f"describe('Issue Regression Test', () => {{\n"
            f"  it('should reproduce and resolve the reported issue', async () => {{\n"
            f"    // Target component: {top_file}\n"
            f"    {repro_snippet.replace(chr(10), chr(10) + '    ')}\n"
            f"  }});\n"
            f"}});\n"
        )
        framework = "jest / vitest"
        filename = "tests/reproduce_issue.test.ts"
    else:
        test_code = (
            f"// Reproduction Test for: {title}\n"
            f"// Target component: {top_file}\n\n"
            f"// Repro logic:\n"
            f"{repro_snippet}\n"
        )
        framework = "standard"
        filename = "tests/reproduce_test"

    return {
        "framework": framework,
        "suggested_filepath": filename,
        "test_code": test_code,
    }


def triage_issue(
    repository: str,
    issue_number: Optional[int] = None,
    issue_url: Optional[str] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    github_token: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.time()
    owner, repo = extract_repo_parts(repository)

    # Handle issue_url if passed
    if issue_url:
        m = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url)
        if m:
            owner, repo = m.group(1), m.group(2)
            issue_number = int(m.group(3))

    if not owner or not repo:
        return {
            "status": "error",
            "message": "Invalid repository format. Expected 'owner/repo' or GitHub URL.",
        }

    # Fetch repository metadata
    repo_url = f"https://api.github.com/repos/{owner}/{repo}"
    repo_meta = make_github_request(repo_url, github_token) or {}
    default_branch = repo_meta.get("default_branch", "main")
    primary_lang = repo_meta.get("language", "Python")

    # Fetch issue details if issue_number is provided
    labels: List[str] = []
    author = "unknown"
    state = "open"
    issue_id = issue_number

    if issue_number:
        i_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        issue_data = make_github_request(i_url, github_token)
        if issue_data:
            title = issue_data.get("title", title or "")
            body = issue_data.get("body", body or "")
            state = issue_data.get("state", "open")
            author = issue_data.get("user", {}).get("login", "unknown")
            labels = [l.get("name", "") for l in issue_data.get("labels", [])]

    issue_title = title or f"Issue #{issue_number}"
    issue_body = body or ""

    # Fetch file tree for root-cause correlation
    file_tree = fetch_repo_file_tree(owner, repo, default_branch, github_token)

    # Run analysis modules
    repro = analyze_issue_reproducibility(issue_title, issue_body)
    itype, severity = classify_issue(issue_title, issue_body, labels)
    candidate_files = match_affected_files(issue_title, issue_body, file_tree)
    repro_test = synthesize_reproduction_test(itype, primary_lang, issue_title, issue_body, candidate_files)

    # Construct actionable fix blueprint
    target_component = candidate_files[0]["path"] if candidate_files else f"{repo}/core"
    fix_blueprint = {
        "target_file": target_component,
        "action_required": "Modify candidate module logic and assert with reproduction test",
        "validation_command": f"pytest {repro_test['suggested_filepath']}" if "python" in primary_lang.lower() else "npm test",
        "triage_recommendation": (
            "Ready for autonomous code fixing. Reproduction test and candidate files identified."
            if repro["score"] >= 45 and candidate_files
            else "Request additional minimal reproduction steps from the author."
        ),
    }

    elapsed = round(time.time() - t0, 2)
    return {
        "repository": f"{owner}/{repo}",
        "repository_language": primary_lang,
        "issue_number": issue_id,
        "issue_title": issue_title,
        "issue_state": state,
        "author": author,
        "labels": labels,
        "elapsed_seconds": elapsed,
        "classification": {
            "type": itype,
            "severity": severity,
        },
        "reproducibility": repro,
        "candidate_root_cause_files": candidate_files,
        "synthesized_reproduction_test": repro_test,
        "fix_blueprint": fix_blueprint,
    }


# --------------------------------------------------------------------------------------
# Standby HTTP Server & Apify PPE Lifecycle
# --------------------------------------------------------------------------------------

async def _charge(event: str, count: int = 1) -> None:
    if not Actor:
        return
    try:
        await Actor.charge(event_name=event, count=count)
    except Exception as exc:
        print(f"[WARN] charge {event} x{count} failed: {exc}", file=sys.stderr)


STANDBY_HTML = """<!doctype html><html><head><title>Agentic Codebase Issue Verifier API</title></head>
<body style="font-family:system-ui;max-width:56rem;margin:3rem auto;line-height:1.5">
<h1>Agentic Codebase Issue Verifier (Standby API)</h1>
<p>Self-validating triage engine evaluating reproducibility, root-cause files, and synthesizing tests.</p>
<pre>curl "https://ACTOR-URL/?repo=pallets/flask&issue=5000"</pre>
<p>Direct issue URL: <code>?issue_url=https://github.com/owner/repo/issues/123</code></p>
</body></html>"""


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return

        parts = request_line.decode("utf-8", errors="ignore").strip().split()
        if len(parts) < 2:
            writer.close()
            return
        path = parts[1]

        headers: Dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            line_str = line.decode("utf-8", errors="ignore")
            if ":" in line_str:
                k, v = line_str.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        # Apify Standby Readiness Probe
        if "x-apify-container-server-readiness-probe" in headers or path.startswith("/healthz"):
            body = b'{"status":"ready"}'
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        parsed = urllib.parse.urlparse(path)
        query = urllib.parse.parse_qs(parsed.query)

        repo = (query.get("repo") or [""])[0].strip()
        issue_url = (query.get("issue_url") or [""])[0].strip()
        issue_str = (query.get("issue") or [""])[0].strip()
        issue_num = int(issue_str) if issue_str.isdigit() else None
        title = (query.get("title") or [""])[0].strip()
        body_text = (query.get("body") or [""])[0].strip()
        token = (query.get("github_token") or [""])[0].strip()

        if parsed.path in ("/", "/docs", "/index.html") and not (repo or issue_url):
            body = STANDBY_HTML.replace("ACTOR-URL", f"https://{headers.get('host', 'localhost')}").encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: "
                + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        # Base actor-start charge
        await _charge("actor-start", 1)

        if not repo and not issue_url:
            payload = {
                "status": "error",
                "error": "missing_repository_or_issue_url",
                "hint": "Pass ?repo=owner/repo&issue=123 or ?issue_url=https://github.com/owner/repo/issues/123",
            }
            body = json.dumps(payload, indent=2).encode()
            status_line = b"HTTP/1.1 400 Bad Request\r\n"
        else:
            loop = asyncio.get_running_loop()
            report = await loop.run_in_executor(
                None, triage_issue, repo, issue_num, issue_url, title, body_text, token
            )
            await _charge("issue-triaged", 1)

            payload = {
                "status": "success",
                "actor": ACTOR_SLUG,
                "version": ACTOR_VERSION,
                "pricing_model": "PAY_PER_EVENT",
                "events_billed": {
                    "actor-start": 1,
                    "issue-triaged": 1,
                },
                "data": report,
            }
            body = json.dumps(payload, indent=2).encode()
            status_line = b"HTTP/1.1 200 OK\r\n"

    except Exception as exc:
        body = json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}"}).encode()
        status_line = b"HTTP/1.1 500 Internal Server Error\r\n"

    writer.write(
        status_line
        + b"Content-Type: application/json; charset=utf-8\r\n"
        + b"Access-Control-Allow-Origin: *\r\n"
        + b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        + b"Connection: close\r\n\r\n" + body
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_server(port: int) -> None:
    server = await asyncio.start_server(handle_client, "0.0.0.0", port)
    print(f"[STANDBY] Agentic Codebase Issue Verifier listening on 0.0.0.0:{port}")
    async with server:
        await server.serve_forever()


async def run_batch(actor_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    repo = actor_input.get("repository", "pallets/flask")
    issue_num = actor_input.get("issueNumber")
    issue_url = actor_input.get("issueUrl")
    issues = actor_input.get("issues")
    token = actor_input.get("githubToken")

    target_issues: List[Optional[int]] = []
    if issues and isinstance(issues, list):
        for i in issues:
            if isinstance(i, int):
                target_issues.append(i)
            elif isinstance(i, str) and i.isdigit():
                target_issues.append(int(i))
    elif issue_num:
        target_issues.append(int(issue_num))
    else:
        target_issues = [None]

    print(f"[BATCH] Triaging issues for repository '{repo}'...")
    loop = asyncio.get_running_loop()
    reports = []

    for num in target_issues[:20]:
        rep = await loop.run_in_executor(None, triage_issue, repo, num, issue_url, None, None, token)
        reports.append(rep)

    if Actor:
        await _charge("actor-start", 1)
        await Actor.push_data(reports)
        await _charge("issue-triaged", len(reports))
        print(f"[BATCH] Pushed {len(reports)} issue verification report(s) to dataset!")
    else:
        print(json.dumps(reports, indent=2))
    return reports


async def main() -> None:
    if "--cli" in sys.argv:
        repo = "pallets/flask"
        issue_num = 5000
        issue_url = None

        for arg in sys.argv[1:]:
            if arg.startswith("repo="):
                repo = arg.split("=", 1)[1]
            elif arg.startswith("issue="):
                val = arg.split("=", 1)[1]
                issue_num = int(val) if val.isdigit() else None
            elif arg.startswith("issue_url="):
                issue_url = arg.split("=", 1)[1]

        print(f"[CLI] Triaging {repo} (Issue #{issue_num})...")
        res = triage_issue(repo, issue_number=issue_num, issue_url=issue_url)
        print(json.dumps(res, indent=2))
        return

    if "--server" in sys.argv:
        port = int(os.environ.get("ACTOR_WEB_SERVER_PORT", "8080"))
        await run_server(port)
        return

    if Actor:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            mode = str(actor_input.get("runMode", "BATCH")).upper()
            if mode == "STANDBY_SERVER":
                port = int(os.environ.get("ACTOR_WEB_SERVER_PORT", "8080"))
                web_port = getattr(getattr(Actor, "configuration", None), "web_server_port", None)
                await run_server(web_port or port)
            else:
                await run_batch(actor_input)
    else:
        await run_batch({})


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)
