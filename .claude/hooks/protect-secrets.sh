#!/usr/bin/env bash
# Blocks Read/Write/Edit on sensitive files. Exit 2 = hard block.
INPUT=$(cat)

INPUT_JSON="$INPUT" python3 - <<'PY'
import json
import re
import sys
from pathlib import Path

PATTERNS = [
    r"\.env$",
    r"\.env\.",
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"\.pfx$",
    r"id_rsa",
    r"id_ed25519",
    r"id_ecdsa",
    r"credentials\.json$",
    r"\.netrc$",
    r"secrets\.",
]

EXAMPLE_MARKERS = {"example", "sample", "template", "dist"}


def is_example_template(value):
    name = Path(value).name.lower()
    parts = [part for part in name.split(".") if part]
    return any(part in EXAMPLE_MARKERS for part in parts)


def is_sensitive(value):
    if is_example_template(value):
        return False
    name = Path(value).name
    if name.startswith("secrets."):
        return True
    return any(re.search(pattern, value) for pattern in PATTERNS if pattern != r"secrets\.")


def blocked(raw):
    path = Path(raw).expanduser()
    values = [str(path)]
    try:
        values.append(str(path.resolve(strict=False)))
    except Exception:
        pass
    for value in values:
        if is_sensitive(value):
            print("BLOCKED: sensitive file — %s" % raw, file=sys.stderr)
            sys.exit(2)


try:
    payload = json.loads(__import__("os").environ.get("INPUT_JSON", "{}") or "{}")
except Exception:
    sys.exit(0)

tool_input = payload.get("tool_input", {}) or {}
for key in ("file_path", "filepath", "filePath", "path"):
    value = tool_input.get(key)
    if isinstance(value, str) and value:
        blocked(value)
for key in ("paths", "files"):
    value = tool_input.get(key)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                blocked(item)
PY
