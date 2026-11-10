#!/usr/bin/env python3
"""
deploy.py — Turnkey Deployer for Apify Standby PPE Actor: 'agentic-codebase-issue-verifier'
"""

import subprocess
import sys
from pathlib import Path

ACTOR_DIR = Path(__file__).parent.resolve()
APIFY_DEPLOY_PY = ACTOR_DIR / "apify_api_deploy.py"

def main():
    if not APIFY_DEPLOY_PY.exists():
        print(f"Error: {APIFY_DEPLOY_PY} not found!", file=sys.stderr)
        sys.exit(1)
    res = subprocess.run([sys.executable, str(APIFY_DEPLOY_PY)] + sys.argv[1:], cwd=ACTOR_DIR)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
