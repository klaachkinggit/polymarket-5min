#!/usr/bin/env bash
# Blocks known-dangerous shell patterns. Exit 2 = hard block.
# bash 3.2 compatible (no associative arrays — macOS ships bash 3.2).
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    ti = json.load(sys.stdin).get('tool_input', {})
    print(ti.get('command', '') or ti.get('cmd', '') or ti.get('shell_command', '') or ti.get('script', ''))
except Exception:
    pass
" 2>/dev/null)

[ -z "$CMD" ] && exit 0

CMD_ENV="$CMD" python3 - <<'PY'
import glob
import os
import re
import shlex
import sys
from pathlib import Path

cmd = os.environ.get("CMD_ENV", "")
try:
    tokens = shlex.split(cmd)
except ValueError:
    tokens = cmd.split()
if not tokens:
    sys.exit(0)

readers = {"cat", "less", "more", "head", "tail", "sed", "awk", "grep", "rg"}
name = Path(tokens[0]).name
if name not in readers:
    sys.exit(0)

patterns = [
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

example_markers = {"example", "sample", "template", "dist"}


def is_example_template(value):
    name = Path(value).name.lower()
    parts = [part for part in name.split(".") if part]
    return any(part in example_markers for part in parts)


def is_sensitive_value(value):
    if is_example_template(value):
        return False
    name = Path(value).name
    if name.startswith("secrets."):
        return True
    return any(re.search(pattern, value) for pattern in patterns if pattern != r"secrets\.")


def sensitive(raw):
    expanded = os.path.expandvars(os.path.expanduser(raw))
    matches = glob.glob(expanded) or [expanded]
    for item in matches:
        path = Path(item)
        values = [str(path)]
        try:
            values.append(str(path.resolve(strict=False)))
        except Exception:
            pass
        for value in values:
            if is_sensitive_value(value):
                return True
    return False


for token in tokens[1:]:
    if token.startswith("-"):
        continue
    if sensitive(token):
        print("BLOCKED: reading sensitive file — %s" % token, file=sys.stderr)
        sys.exit(2)
PY
secret_status=$?
if [ "$secret_status" -eq 2 ]; then
  exit 2
fi

if printf '%s' "$CMD" | grep -qE '(^|[;&|][[:space:]]*)git[[:space:]]+push([[:space:]]|$)'; then
  if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])(-f|--force|--force-with-lease)([=[:space:]]|$)|[[:space:]]\+[^[:space:]]+|[[:space:]]([^[:space:]]+:)?(main|master)(:[^[:space:]]*)?([[:space:]]|$)'; then
    echo "BLOCKED: unsafe git push" >&2
    exit 2
  fi
  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || true)
  if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    echo "BLOCKED: git push from deployment branch" >&2
    exit 2
  fi
fi

# Parallel arrays — index i pairs DESCS[i] with REGEXES[i].
# Catastrophic rm = RECURSIVE (-r/-R) on a critical target. Non-recursive rm of a
# specific file (even by absolute path) is NOT blocked — that's a normal operation.
# EXCEPTION: secret env files (.env / .env.local) ARE protected from rm/mv/truncate
# via Bash, since protect-secrets.sh only covers the Edit/Write/Read tools, not Bash.
# Append (>>) and cp (restore-from-backup) are intentionally still allowed, and
# .env.example (a non-secret, git-tracked template) is never blocked.
DESCS=(
  "recursive rm of root"
  "recursive rm of home"
  "recursive rm of current/parent dir"
  "recursive rm with bare glob"
  "sudo rm"
  "fork bomb"
  "chmod 777"
  "dd to disk device"
  "redirect to disk device"
  "mkfs"
  "pipe remote content to shell"
  "git reset --hard"
  "git branch -D"
  "git checkout ."
  "git restore ."
  "delete/move of .env secret file"
  "truncating redirect onto .env secret file"
  "git clean -f (removes untracked files incl .env)"
)
REGEXES=(
  'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+/([[:space:]]|$|\*)'
  'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+(~|\$HOME)([[:space:]]|/|$)'
  'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+\.\.?/?([[:space:]]|$)'
  'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+\*([[:space:]]|$)'
  'sudo[[:space:]]+rm'
  ':\(\)[[:space:]]*\{'
  'chmod[[:space:]]+[0-9]*777'
  'dd[[:space:]]+if=.*of=/dev/'
  '>[[:space:]]*/dev/s[dh][a-z]'
  'mkfs\.'
  '(curl|wget)[[:space:]].*[|][[:space:]]*(ba)?sh([[:space:]]|$)'
  '(^|[;&|][[:space:]]*)git[[:space:]]+reset[[:space:]].*--hard([[:space:]]|$)'
  '(^|[;&|][[:space:]]*)git[[:space:]]+branch[[:space:]].*-[a-zA-Z]*D([[:space:]]|$)'
  '(^|[;&|][[:space:]]*)git[[:space:]]+checkout[[:space:]]+\./?([[:space:]]|$)'
  '(^|[;&|][[:space:]]*)git[[:space:]]+restore[[:space:]]+\./?([[:space:]]|$)'
  '(rm|mv|shred|truncate)[[:space:]]+([^|;&]*[[:space:]])?\.env(\.local|\*)?([[:space:]]|"|'"'"'|$)'
  '[^>]>[[:space:]]*\.env(\.local)?([[:space:]]|"|'"'"'|$)'
  'git[[:space:]]+clean[[:space:]].*-[a-zA-Z]*f'
)

i=0
while [ $i -lt ${#REGEXES[@]} ]; do
  if printf '%s' "$CMD" | grep -qE "${REGEXES[$i]}"; then
    echo "BLOCKED: ${DESCS[$i]}" >&2
    exit 2
  fi
  i=$((i + 1))
done
exit 0
