#!/usr/bin/env python3
"""Generate MCP server config in the right format/location for a given tool.

One source of truth (SERVERS) → per-tool emitters. Adding a new tool = one function.

Usage:
    python3 tools/gen-mcp.py <tool>
    tool ∈ {claude, codex}

Project-scoped configs (claude, codex) are WRITTEN to the repo.

Env vars: GITHUB_TOKEN (required for github), DATABASE_URL (optional → adds db server).
"""
import json
import os
import re
import sys

# ── Single source of truth ────────────────────────────────────
# env: name of the environment variable this server needs (or None).
SERVERS = [
    {"name": "github",     "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": "GITHUB_TOKEN", "env_key": "GITHUB_PERSONAL_ACCESS_TOKEN"},
    {"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."], "env": None},
    {"name": "git",        "command": "uvx", "args": ["mcp-server-git", "--repository", "."], "env": None},
    {"name": "playwright", "command": "npx", "args": ["-y", "@playwright/mcp"], "env": None},
    {"name": "sequential-thinking", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"], "env": None},
    {"name": "context7",   "command": "npx", "args": ["-y", "@upstash/context7-mcp"], "env": None},
]

if os.environ.get("DATABASE_URL"):
    SERVERS.append({
        "name": "db", "command": "npx",
        "args": ["-y", "@bytebase/dbhub", "--dsn", os.environ["DATABASE_URL"]],
        "env": None,
    })


def _json_servers(var_syntax):
    """Build the mcpServers dict. var_syntax formats an env var name into a placeholder."""
    out = {}
    for s in SERVERS:
        entry = {"command": s["command"], "args": list(s["args"])}
        if s["env"]:
            entry["env"] = {s["env_key"]: var_syntax(s["env"])}
        out[s["name"]] = entry
    return {"mcpServers": out}


def emit_claude():
    cfg = _json_servers(lambda v: "${%s}" % v)               # Claude: ${VAR}
    path = ".mcp.json"
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
        existing.setdefault("mcpServers", {})
        managed = {s["name"] for s in SERVERS}
        existing["mcpServers"] = {
            name: server
            for name, server in existing["mcpServers"].items()
            if name not in managed
        }
        existing["mcpServers"].update(cfg["mcpServers"])
        cfg = existing
    _write(".mcp.json", json.dumps(cfg, indent=2))


def emit_codex():
    # Codex: TOML, no ${} interpolation. Secrets are forwarded by NAME via env_vars.
    lines = []
    for s in SERVERS:
        lines.append("[mcp_servers.%s]" % s["name"])
        lines.append("command = %s" % json.dumps(s["command"]))
        lines.append("args = %s" % json.dumps(s["args"]))
        if s["env"] and s["env_key"] == s["env"]:
            # Forward the named env var from the surrounding shell into the server.
            lines.append('env_vars = ["%s"]' % s["env"])
        elif s["env"]:
            lines.append("")
            lines.append("[mcp_servers.%s.env]" % s["name"])
            lines.append("%s = %s" % (s["env_key"], json.dumps("$%s" % s["env"])))
        lines.append("")
    os.makedirs(".codex", exist_ok=True)
    body = "\n".join(lines).rstrip()
    path = ".codex/config.toml"
    existing = ""
    if os.path.exists(path):
        with open(path) as f:
            existing = f.read()
        existing = _without_managed_codex_servers(existing)
    with open(path, "w") as f:
        f.write((existing.rstrip() + "\n\n" if existing.strip() else "") + body + "\n")
    print("  wrote %s" % path)


def _without_managed_codex_servers(text):
    managed = {s["name"] for s in SERVERS}
    kept = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = re.match(r"\[mcp_servers\.([^\].]+)(?:\.[^\]]+)?\]", lines[i])
        if match and match.group(1) in managed:
            i += 1
            while i < len(lines) and not lines[i].startswith("["):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept)


def _write(path, content):
    with open(path, "w") as f:
        f.write(content + "\n")
    print("  wrote %s" % path)


EMITTERS = {
    "claude": emit_claude, "codex": emit_codex,
}

if __name__ == "__main__":
    tool = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if tool not in EMITTERS:
        print("Usage: gen-mcp.py <%s>" % "|".join(EMITTERS), file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("GITHUB_TOKEN"):
        print("  note: GITHUB_TOKEN not set — github MCP will fail until you set it in .env", file=sys.stderr)
    EMITTERS[tool]()
