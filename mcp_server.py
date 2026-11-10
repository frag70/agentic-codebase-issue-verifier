#!/usr/bin/env python3
"""
mcp_server.py — Model Context Protocol (MCP) stdio server for 'agentic-codebase-issue-verifier'.
Allows autonomous coding agents (Claude Code, Cursor, Devin) to triage issues and synthesize tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from main import triage_issue

SERVER_NAME = "agentic-codebase-issue-verifier-mcp"
SERVER_VERSION = "0.1.0"


def send_response(response: dict):
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def handle_request(req: dict):
    method = req.get("method")
    msg_id = req.get("id")

    if method == "initialize":
        send_response({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION
                }
            }
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send_response({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": "triage_codebase_issue",
                        "description": "Triages GitHub issues, evaluates reproducibility score, matches candidate root-cause files in the repository tree, and synthesizes executable reproduction test cases.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "repository": {
                                    "type": "string",
                                    "description": "Target repository (e.g. pallets/flask, tiangolo/fastapi, or full URL)"
                                },
                                "issue_number": {
                                    "type": "integer",
                                    "description": "GitHub issue number (e.g. 5000)"
                                },
                                "issue_url": {
                                    "type": "string",
                                    "description": "Optional direct GitHub issue URL"
                                },
                                "github_token": {
                                    "type": "string",
                                    "description": "Optional GitHub PAT for rate limit elevation or private repos"
                                }
                            },
                            "required": ["repository"]
                        }
                    }
                ]
            }
        })
    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "triage_codebase_issue":
            repo = args.get("repository", "pallets/flask")
            issue_num = args.get("issue_number")
            issue_url = args.get("issue_url")
            token = args.get("github_token")
            try:
                res = triage_issue(repo, issue_number=issue_num, issue_url=issue_url, github_token=token)
                send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(res, indent=2)
                            }
                        ]
                    }
                })
            except Exception as e:
                send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error triaging issue for {repo}: {type(e).__name__} - {e}"
                            }
                        ]
                    }
                })
        else:
            send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {tool_name}"
                }
            })
    else:
        if msg_id is not None:
            send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unhandled method: {method}"
                }
            })


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            handle_request(req)
        except Exception as e:
            sys.stderr.write(f"Error handling MCP line: {e}\n")


if __name__ == "__main__":
    main()
