# Security Scan — OWASP Top 10

Security scan of [PATH]. Check each category and report all findings.

1. **Injection** — SQL, command, LDAP injection. Parameterized queries everywhere?
2. **Auth/Access control** — Missing auth checks, broken RBAC, JWT misuse, IDOR (can user A access user B's data by changing an ID?)
3. **Secrets** — Hardcoded credentials in code or config:
   `grep -rE "(password|secret|token|api_key|apikey)\s*[:=]\s*['\"][^'\"]{6,}" [PATH]`
4. **XSS** — Unescaped user input rendered in HTML/JS.
5. **Sensitive data exposure** — Stack traces leaking to clients? Overly verbose error messages?
6. **Input validation** — All system boundary inputs validated and sanitized?
7. **Dependencies** — Run `npm audit --audit-level=high` or `pip audit` if applicable.
8. **Cryptography** — Weak hashing (MD5/SHA1 for passwords), missing TLS, weak random for tokens?
9. **PII exposure** — Emails, phones, SSN/IDs, addresses, financial identifiers leaking into logs, error messages, analytics events, URLs, or third-party telemetry. Grep candidates:
   `grep -rnE "log[^\n]*\b(email|phone|ssn|address|dob|iban|card)" [PATH]`

Report format: `[SEVERITY] file:line — description — fix`
Severity: CRITICAL | HIGH | MEDIUM | LOW

CRITICAL or HIGH findings block ship.
