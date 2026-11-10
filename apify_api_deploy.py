#!/usr/bin/env python3
"""
apify_api_deploy.py — Direct API Automated Deployer for 'agentic-codebase-issue-verifier'
Standby Pay-Per-Event (PPE) Apify Actor
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

ACTOR_DIR = Path(__file__).parent.resolve()
ACTOR_SLUG = "agentic-codebase-issue-verifier"
ACTOR_TITLE = "Agentic Codebase Issue Verifier & Triager (Standby API)"
ACTOR_DESC = "Zero-proxy Standby API triaging GitHub issues, checking reproducibility, matching root-cause files in the codebase, and synthesizing regression test cases."
REPO_NAME = f"frag70/{ACTOR_SLUG}"
REPO_URL = f"https://github.com/{REPO_NAME}#main"

def get_token(args_token: str = None) -> str:
    if args_token:
        return args_token
    token = os.environ.get("APIFY_TOKEN")
    if token:
        return token
    env_file = Path("/home/thomas/autonomous-engine/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def api_call(endpoint: str, token: str, method: str = "GET", data: dict = None):
    url = f"https://api.apify.com/v2/{endpoint}"
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    body = json.dumps(data).encode("utf-8") if data else None
    with urllib.request.urlopen(req, data=body, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def sync_git_and_github():
    print(f"📦 Synchronizing local Git repository for {ACTOR_SLUG}...")
    git_dir = ACTOR_DIR / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=ACTOR_DIR, check=True)
        subprocess.run(["git", "config", "user.name", "Frag70"], cwd=ACTOR_DIR, check=True)
        subprocess.run(["git", "config", "user.email", "thomas.fragrante@gmail.com"], cwd=ACTOR_DIR, check=True)

    subprocess.run(["git", "add", "."], cwd=ACTOR_DIR, check=True)
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=ACTOR_DIR)
    if diff.returncode != 0:
        subprocess.run(["git", "commit", "-m", "feat: initial commit for agentic-codebase-issue-verifier actor"], cwd=ACTOR_DIR, check=True)
        print("✅ Committed local changes to git.")
    else:
        print("ℹ️ No uncommitted changes.")

    # Check if GitHub repo exists
    check_repo = subprocess.run(["gh", "repo", "view", REPO_NAME], capture_output=True, text=True)
    if check_repo.returncode != 0:
        print(f"🌐 Creating public GitHub repository: {REPO_NAME}...")
        subprocess.run([
            "gh", "repo", "create", REPO_NAME,
            "--public",
            f"--description={ACTOR_DESC}",
            "--source=.",
            "--remote=origin",
            "--push"
        ], cwd=ACTOR_DIR, check=True)
        print(f"✅ Created & pushed {REPO_NAME}!")
    else:
        print(f"ℹ️ GitHub repository {REPO_NAME} exists. Ensuring remote and pushing...")
        subprocess.run(["git", "remote", "set-url", "origin", f"git@github.com:{REPO_NAME}.git"], cwd=ACTOR_DIR, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=ACTOR_DIR, check=True)
        print(f"✅ Pushed main to {REPO_NAME}!")

def deploy_to_apify(token: str):
    if not token:
        print("❌ Error: No APIFY_TOKEN found.")
        return False

    print(f"🔑 Verifying Apify API Token...")
    user_info = api_call("users/me", token)
    username = user_info.get("data", {}).get("username")
    print(f"✅ Authenticated as Apify user: @{username}")

    actor_id = None
    try:
        existing = api_call(f"actors/{username}~{ACTOR_SLUG}", token)
        actor_id = existing.get("data", {}).get("id")
        print(f"ℹ️ Found existing Actor: {username}~{ACTOR_SLUG} (ID: {actor_id})")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"📦 Creating new Actor '{ACTOR_SLUG}' on Apify...")
            payload = {
                "name": ACTOR_SLUG,
                "title": ACTOR_TITLE,
                "description": ACTOR_DESC,
                "restartOnError": False,
                "isPublic": False,
            }
            res = api_call("actors", token, method="POST", data=payload)
            actor_id = res.get("data", {}).get("id")
            print(f"✅ Actor created successfully! ID: {actor_id}")
        else:
            raise

    # Configure Git repo version
    print(f"🔗 Linking Git Repository: {REPO_URL}...")
    version_payload = {
        "versionNumber": "0.1",
        "sourceType": "GIT_REPO",
        "gitRepoUrl": REPO_URL,
        "buildTag": "latest",
    }
    try:
        api_call(f"actors/{actor_id}/versions/0.1", token, method="PUT", data=version_payload)
        print("✅ Version 0.1 updated with Git repo.")
    except urllib.error.HTTPError:
        api_call(f"actors/{actor_id}/versions", token, method="POST", data=version_payload)
        print("✅ Version 0.1 created with Git repo.")

    # Trigger Build
    print("🔨 Triggering container build...")
    build_res = api_call(f"actors/{actor_id}/builds?version=0.1", token, method="POST")
    build_id = build_res.get("data", {}).get("id")
    print(f"🚀 Build initiated! Build ID: {build_id}")
    print(f"\n🎉 Actor is live in your Apify Console!")
    print(f"   Console link: https://console.apify.com/actors/{actor_id}")
    return True

if __name__ == "__main__":
    tok = get_token(sys.argv[1] if len(sys.argv) > 1 else None)
    sync_git_and_github()
    deploy_to_apify(tok)
