"""Security-first codebase standards guard for Friday."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "codebase_standards.sqlite3"
_LOCK = threading.Lock()

PRIORITIES = ("security", "performance", "maintainability", "reliability", "portability")
_PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITIES)}

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss"}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "chroma_db",
    "coverage",
    "data",
    "dist",
    "node_modules",
    "out",
    "target",
    "venv",
}

SECURITY_PATTERNS = (
    (re.compile(r"\beval\s*\("), "Dynamic eval", "Avoid eval-style execution unless the input is fully trusted.", "Replace eval with structured parsing or a narrow command map.", 5),
    (re.compile(r"\bexec\s*\("), "Dynamic exec", "Runtime code execution is a high-risk security boundary.", "Replace exec with explicit functions or a sandboxed, audited path.", 5),
    (re.compile(r"shell\s*=\s*True"), "Shell execution", "Shell invocation can turn arguments into command injection.", "Use argument arrays with shell disabled and validate inputs.", 5),
    (re.compile(r"\bdangerouslySetInnerHTML\b|\.innerHTML\s*="), "Raw HTML injection", "Raw HTML writes can introduce XSS if content is user-controlled.", "Use text rendering or sanitize trusted markup at the boundary.", 4),
    (
        re.compile(r"(?i)\b(api[_-]?key|client[_-]?secret|secret|password|token)\b\s*[:=]\s*['\"][^'\"]{16,}['\"]"),
        "Secret-like literal",
        "Credential-looking values should not live in source files.",
        "Move credentials to environment variables or a protected vault reference.",
        5,
    ),
)

RELIABILITY_PATTERNS = (
    (re.compile(r"^\s*except\s*:\s*(?:pass)?\s*$"), "Bare except", "Bare exception handlers can hide real failures.", "Catch specific exceptions and log enough context to diagnose failures.", 4),
    (re.compile(r"^\s*except\s+Exception\s*:\s*pass\s*$"), "Swallowed exception", "Ignoring broad exceptions makes failures silent.", "Record the exception or return an explicit degraded state.", 4),
    (re.compile(r"\brequests\.(?:get|post|put|patch|delete)\s*\((?![^)]*timeout\s*=)"), "HTTP call without visible timeout", "Network calls without timeouts can hang workers and voice paths.", "Pass a timeout and surface retries/backoff in the caller.", 3),
)

PORTABILITY_PATTERNS = (
    (re.compile(r"[A-Za-z]:\\\\"), "Hard-coded Windows path", "Drive-letter paths reduce portability across machines.", "Resolve paths from configuration, the workspace root, or environment variables.", 2),
    (re.compile(r"(?i)\b(powershell|cmd\.exe|start-process|\.exe)\b"), "Platform-specific command", "Platform-specific commands need an intentional compatibility boundary.", "Wrap OS-specific behavior behind adapters or document the Windows-only requirement.", 2),
)


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS codebase_standards_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                summary TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                counts_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def standards() -> dict[str, Any]:
    return {
        "name": "Friday codebase standards",
        "priority_order": list(PRIORITIES),
        "principles": [
            "Security first: avoid secret leaks, unsafe execution, command injection, and XSS.",
            "Speed and performance: prefer event streams over unnecessary polling and keep hot paths bounded.",
            "Maintainability: keep files focused, avoid large functions, remove duplication, and make intent visible.",
            "Reliability: do not swallow errors; use timeouts, tests, and explicit degraded states.",
            "Portability: isolate machine-specific paths, commands, and platform assumptions.",
        ],
        "thresholds": _thresholds(),
    }


def status() -> dict[str, Any]:
    latest = recent(limit=1)
    return {
        "enabled": bool(config_value("codebase_standards_enabled", True)),
        "latest": latest[0] if latest else None,
        "priority_order": list(PRIORITIES),
        "thresholds": _thresholds(),
        "summary": latest[0]["summary"] if latest else "No codebase standards scan has run yet.",
    }


def scan(root: str | Path = "", *, focus: str = "", max_files: int = 250) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    if not bool(config_value("codebase_standards_enabled", True)):
        return {
            "ok": False,
            "root": str(base),
            "summary": "Codebase standards guard is disabled.",
            "findings": [],
            "counts": {},
            "metadata": {},
        }

    thresholds = _thresholds()
    file_limit = max(1, min(2000, int(max_files or thresholds["max_scan_files"])))
    if not base.exists():
        findings = [
            _finding(
                "missing_root",
                "reliability",
                3,
                str(base),
                0,
                "Project root not found",
                "Friday cannot inspect standards for a missing path.",
                "Check the requested root and run the scan again.",
            )
        ]
        return _persist(base, findings, {"scanned_files": 0, "max_files": file_limit, "focus": str(focus or ""), "thresholds": thresholds})

    code_files = list(_iter_code_files(base, file_limit))
    findings: list[dict[str, Any]] = []
    has_tests = False
    focus_text = str(focus or "").strip().lower()
    for path in code_files:
        has_tests = has_tests or _looks_like_test_file(path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = _relative(path, base)
        file_findings = _scan_file(path, rel, text, thresholds)
        if focus_text and (focus_text in rel.lower() or focus_text in text.lower()):
            file_findings.append(
                _finding(
                    "focus_match",
                    "maintainability",
                    1,
                    rel,
                    0,
                    "Matches requested focus",
                    "This file matches the requested standards focus.",
                    "Review this file with the higher-priority findings first.",
                )
            )
        findings.extend(file_findings)

    if code_files and not has_tests and not _has_tests_dir(base):
        findings.append(
            _finding(
                "missing_tests",
                "reliability",
                2,
                "",
                0,
                "No test files discovered",
                "Important behavior is harder to change safely without local tests.",
                "Add focused tests around core flows before broad refactors.",
            )
        )

    findings = sorted(findings, key=_finding_sort_key)[: int(thresholds["max_findings"])]
    metadata = {
        "scanned_files": len(code_files),
        "max_files": file_limit,
        "focus": str(focus or ""),
        "truncated": len(code_files) >= file_limit,
        "thresholds": thresholds,
    }
    return _persist(base, findings, metadata)


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM codebase_standards_reports ORDER BY id DESC LIMIT ?",
            (max(1, min(100, int(limit or 20))),),
        ).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM codebase_standards_reports")


def _scan_file(path: Path, rel: str, text: str, thresholds: dict[str, int]) -> list[dict[str, Any]]:
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []
    line_count = len(lines)
    max_file_lines = int(thresholds["max_file_lines"])
    hard_file_lines = int(thresholds["hard_file_lines"])
    if line_count > max_file_lines:
        findings.append(
            _finding(
                "large_file",
                "maintainability",
                4 if line_count > hard_file_lines else 3,
                rel,
                1,
                "File is over the preferred size",
                f"{line_count} lines; Friday's preferred limit is {max_file_lines} for normal source files.",
                "Split by stable responsibilities after adding or confirming regression coverage.",
                {"line_count": line_count},
            )
        )

    todo_count = sum(1 for line in lines if "todo" in line.lower() or "fixme" in line.lower())
    if todo_count >= int(thresholds["todo_threshold"]):
        findings.append(
            _finding(
                "todo_debt",
                "maintainability",
                2,
                rel,
                1,
                "TODO debt is accumulating",
                f"{todo_count} TODO/FIXME marker(s) in one file.",
                "Convert unresolved work into tracked tasks or prune stale comments.",
                {"todo_count": todo_count},
            )
        )

    findings.extend(_pattern_findings(rel, lines, SECURITY_PATTERNS, "security"))
    findings.extend(_pattern_findings(rel, lines, RELIABILITY_PATTERNS, "reliability"))
    findings.extend(_pattern_findings(rel, lines, PORTABILITY_PATTERNS, "portability"))
    findings.extend(_performance_findings(rel, lines))
    findings.extend(_function_length_findings(path, rel, lines, thresholds))
    duplicate = _duplication_finding(rel, lines)
    if duplicate:
        findings.append(duplicate)
    return findings[: int(thresholds["max_findings_per_file"])]


def _pattern_findings(rel: str, lines: list[str], patterns: tuple[tuple[re.Pattern[str], str, str, str, int], ...], priority: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pattern, title, reason, recommendation, severity in patterns:
        matches = 0
        for index, line in enumerate(lines, start=1):
            if not pattern.search(line):
                continue
            findings.append(_finding(title.lower().replace(" ", "_"), priority, severity, rel, index, title, reason, recommendation, {"evidence": _snippet(line)}))
            matches += 1
            if matches >= 3:
                break
    return findings


def _performance_findings(rel: str, lines: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        if "setInterval(" in line:
            findings.append(
                _finding(
                    "polling_loop",
                    "performance",
                    2,
                    rel,
                    index,
                    "Polling loop should be intentional",
                    "Frequent polling can waste CPU/network and make dashboards feel sluggish.",
                    "Prefer WebSockets, server-sent events, or a documented backoff interval when live updates are needed.",
                    {"evidence": _snippet(line)},
                )
            )
        if re.search(r"\bwhile\s+True\s*:", line):
            window = "\n".join(lines[index : index + 10]).lower()
            if "sleep(" not in window and "await " not in window:
                findings.append(
                    _finding(
                        "unbounded_loop",
                        "performance",
                        3,
                        rel,
                        index,
                        "Loop may run without a pause",
                        "Unbounded loops can pin CPU and starve voice/dashboard responsiveness.",
                        "Add an explicit sleep, await, queue wait, or cancellation path.",
                        {"evidence": _snippet(line)},
                    )
                )
    return findings[:5]


def _function_length_findings(path: Path, rel: str, lines: list[str], thresholds: dict[str, int]) -> list[dict[str, Any]]:
    limit = int(thresholds["max_function_lines"])
    spans = _python_function_spans(lines) if path.suffix.lower() == ".py" else _js_function_spans(lines)
    findings: list[dict[str, Any]] = []
    for name, start, length in spans:
        if length <= limit:
            continue
        findings.append(
            _finding(
                "large_function",
                "maintainability",
                3,
                rel,
                start,
                "Function is doing too much",
                f"{name} is {length} lines; preferred limit is {limit}.",
                "Extract focused helpers only around real responsibilities and keep behavior covered.",
                {"function": name, "line_count": length},
            )
        )
    return findings[:5]


def _python_function_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    starts: list[tuple[str, int, int]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\b", line)
        if match:
            starts.append((match.group(2), index, _indent_width(match.group(1))))
    for pos, (name, start, indent) in enumerate(starts):
        end = len(lines) - 1
        for _, next_start, next_indent in starts[pos + 1 :]:
            if next_indent <= indent:
                end = next_start - 1
                break
        spans.append((name, start + 1, max(1, end - start + 1)))
    return spans


def _js_function_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    function_re = re.compile(r"\bfunction\s+([A-Za-z0-9_$]+)\s*\(|\b(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_$]+)\s*=>")
    for index, line in enumerate(lines):
        match = function_re.search(line)
        if not match:
            continue
        name = match.group(1) or match.group(2) or "anonymous"
        depth = 0
        seen_open = False
        end = index
        for cursor in range(index, min(len(lines), index + 400)):
            current = _strip_js_strings(lines[cursor])
            depth += current.count("{") - current.count("}")
            seen_open = seen_open or "{" in current
            end = cursor
            if seen_open and depth <= 0 and cursor > index:
                break
        spans.append((name, index + 1, max(1, end - index + 1)))
    return spans


def _duplication_finding(rel: str, lines: list[str]) -> dict[str, Any] | None:
    repeated = [
        line
        for line, count in Counter(_normal_line(line) for line in lines).items()
        if line and len(line) > 90 and count >= 3
    ]
    if not repeated:
        return None
    return _finding(
        "duplication",
        "maintainability",
        2,
        rel,
        1,
        "Repeated long lines",
        "Repeated long statements often mean shared behavior is drifting.",
        "Extract a helper only if the repeated code has the same intent and lifecycle.",
        {"examples": repeated[:3]},
    )


def _persist(base: Path, findings: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    counts = _counts(findings)
    summary = _summary(findings, counts, base)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO codebase_standards_reports(timestamp, root, summary, findings_json, counts_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), str(base), summary, _json_dumps(findings), _json_dumps(counts), _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM codebase_standards_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _counts(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_priority = Counter(str(item.get("priority") or "maintainability") for item in findings)
    by_severity = Counter(str(item.get("severity") or 0) for item in findings)
    return {
        "total": len(findings),
        "by_priority": {name: int(by_priority.get(name, 0)) for name in PRIORITIES},
        "by_severity": dict(sorted(by_severity.items())),
        "high": sum(1 for item in findings if int(item.get("severity") or 0) >= 4),
    }


def _summary(findings: list[dict[str, Any]], counts: dict[str, Any], base: Path) -> str:
    total = int(counts.get("total") or 0)
    if total <= 0:
        return f"Codebase standards scan found no issues under {base.name}."
    by_priority = counts.get("by_priority") or {}
    parts = [f"{name} {int(by_priority.get(name) or 0)}" for name in PRIORITIES]
    highest = str(findings[0].get("priority") or "maintainability")
    return f"Codebase standards scan found {total} finding(s) under {base.name}: {', '.join(parts)}. Highest priority: {highest}."


def _finding(
    kind: str,
    priority: str,
    severity: int,
    path: str,
    line: int,
    title: str,
    reason: str,
    recommendation: str,
    evidence: Any | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "priority": priority if priority in _PRIORITY_RANK else "maintainability",
        "severity": max(1, min(5, int(severity or 1))),
        "path": path,
        "line": max(0, int(line or 0)),
        "title": title,
        "reason": reason,
        "recommendation": recommendation,
        "evidence": evidence or {},
    }


def _finding_sort_key(item: dict[str, Any]) -> tuple[int, int, str, int]:
    return (
        _PRIORITY_RANK.get(str(item.get("priority") or "maintainability"), len(PRIORITIES)),
        -int(item.get("severity") or 0),
        str(item.get("path") or ""),
        int(item.get("line") or 0),
    )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "summary": str(row["summary"]),
        "findings": _json_loads(row["findings_json"], []),
        "counts": _json_loads(row["counts_json"], {}),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _iter_code_files(base: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(base):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".cache")]
        for name in names:
            path = Path(current) / name
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            files.append(path)
            if len(files) >= max_files:
                return files
    return files


def _looks_like_test_file(path: Path) -> bool:
    lowered = str(path).replace("\\", "/").lower()
    name = path.name.lower()
    return "/tests/" in lowered or name.startswith("test_") or name.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx", ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx"))


def _has_tests_dir(base: Path) -> bool:
    return any((base / name).exists() for name in ("tests", "test", "__tests__", "apps/web/src/__tests__"))


def _thresholds() -> dict[str, int]:
    return {
        "max_file_lines": int(config_value("codebase_standards_max_file_lines", 300)),
        "hard_file_lines": int(config_value("codebase_standards_hard_file_lines", 600)),
        "max_function_lines": int(config_value("codebase_standards_max_function_lines", 60)),
        "todo_threshold": int(config_value("codebase_standards_todo_threshold", 5)),
        "max_findings_per_file": int(config_value("codebase_standards_max_findings_per_file", 12)),
        "max_findings": int(config_value("codebase_standards_max_findings", 200)),
        "max_scan_files": int(config_value("codebase_standards_max_scan_files", 250)),
    }


def _safe_root(root: str | Path) -> Path:
    return resolve_coding_root(root)


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path)


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def _strip_js_strings(value: str) -> str:
    value = re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", "", value)
    return re.sub(r"`(?:\\.|[^`])*`", "", value)


def _normal_line(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith(("#", "//", "*", "/*")):
        return ""
    return re.sub(r"\s+", " ", stripped)


def _snippet(value: str, limit: int = 160) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned[:limit]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
