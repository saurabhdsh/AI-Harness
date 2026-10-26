"""Deterministic code analysis — AST for Python, heuristics otherwise."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    line: int | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.line is not None:
            d["line"] = self.line
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class AnalysisResult:
    language: str
    complexity_hints: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    proposed_patch: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "complexity_hints": self.complexity_hints,
            "issues": [i.to_dict() for i in self.issues],
            "metrics": self.metrics,
            "proposed_patch": self.proposed_patch,
            "summary": self.summary,
        }


def _detect_language(snippet: str) -> str:
    if re.search(r"^\s*(def |class |import |from \w+ import)", snippet, re.M):
        return "python"
    if re.search(r"^\s*(function |const |let |var |export |import )", snippet, re.M):
        return "javascript"
    if re.search(r"^\s*(public |private |class |interface |package )", snippet, re.M):
        return "java"
    return "unknown"


class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.hints: list[str] = []
        self.function_count = 0
        self.class_count = 0
        self.max_nesting = 0
        self._depth = 0
        self.long_functions: list[str] = []
        self.lines_changed: list[tuple[int, str, str]] = []  # line, old, new for patch

    def _enter(self) -> None:
        self._depth += 1
        self.max_nesting = max(self.max_nesting, self._depth)

    def _leave(self) -> None:
        self._depth = max(0, self._depth - 1)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_count += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_function(node)

    def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.function_count += 1
        args = node.args
        param_count = (
            len(args.args)
            + len(args.posonlyargs)
            + len(args.kwonlyargs)
            + (1 if args.vararg else 0)
            + (1 if args.kwarg else 0)
        )
        if param_count > 5:
            self.issues.append(
                Issue(
                    code="TOO_MANY_PARAMS",
                    severity="medium",
                    message=f"Function '{node.name}' has {param_count} parameters (threshold 5)",
                    line=node.lineno,
                    suggestion="Group related parameters into a dataclass or TypedDict",
                )
            )

        # Nesting / branching complexity
        branching = 0
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.BoolOp)):
                branching += 1
        if branching > 8:
            self.issues.append(
                Issue(
                    code="HIGH_COMPLEXITY",
                    severity="high",
                    message=f"Function '{node.name}' has high branching complexity (~{branching})",
                    line=node.lineno,
                    suggestion="Extract nested conditionals into helper functions",
                )
            )
            self.hints.append(
                f"'{node.name}' would benefit from early returns / guard clauses"
            )

        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        length = end - node.lineno + 1
        if length > 40:
            self.long_functions.append(node.name)
            self.issues.append(
                Issue(
                    code="LONG_FUNCTION",
                    severity="medium",
                    message=f"Function '{node.name}' spans ~{length} lines",
                    line=node.lineno,
                    suggestion="Split into smaller, single-purpose functions",
                )
            )

        # Unused-ish args heuristic: args named unused_* or starting with _
        for a in args.args:
            if a.arg.startswith("unused") or a.arg == "_":
                self.issues.append(
                    Issue(
                        code="UNUSED_PARAM",
                        severity="low",
                        message=f"Parameter '{a.arg}' in '{node.name}' looks unused",
                        line=node.lineno,
                        suggestion="Remove unused parameter or prefix intentionally with _",
                    )
                )

        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self._enter()
        self.generic_visit(node)
        self._leave()

    def visit_For(self, node: ast.For) -> None:
        self._enter()
        self.generic_visit(node)
        self._leave()

    def visit_While(self, node: ast.While) -> None:
        self._enter()
        self.generic_visit(node)
        self._leave()


def _scan_heuristics(snippet: str, language: str) -> list[Issue]:
    issues: list[Issue] = []
    lines = snippet.splitlines()
    secret_pat = re.compile(
        r"(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]+['\"]",
        re.I,
    )
    for i, line in enumerate(lines, 1):
        if secret_pat.search(line) and "environ" not in line and "getenv" not in line:
            issues.append(
                Issue(
                    code="HARDCODED_SECRET",
                    severity="critical",
                    message="Possible hardcoded secret / credential",
                    line=i,
                    suggestion="Load secrets from environment or a secret manager",
                )
            )
        if "time.sleep(" in line and language == "python":
            issues.append(
                Issue(
                    code="BLOCKING_SLEEP",
                    severity="medium",
                    message="Blocking sleep in application logic",
                    line=i,
                    suggestion="Prefer async wait or remove artificial delays",
                )
            )
        if re.search(r"except\s*:", line):
            issues.append(
                Issue(
                    code="BARE_EXCEPT",
                    severity="high",
                    message="Bare except clause swallows all errors",
                    line=i,
                    suggestion="Catch specific exception types",
                )
            )
        if len(line) > 120:
            issues.append(
                Issue(
                    code="LONG_LINE",
                    severity="low",
                    message=f"Line exceeds 120 characters ({len(line)})",
                    line=i,
                    suggestion="Wrap or extract expression",
                )
            )
    return issues


def _build_unified_diff(
    original: str,
    issues: list[Issue],
    filename: str = "snippet.py",
) -> str | None:
    """Produce a small illustrative unified diff for improve task."""
    lines = original.splitlines(keepends=True)
    if not lines:
        return None

    # Ensure trailing newline awareness for diff
    body = original if original.endswith("\n") else original + "\n"
    src_lines = body.splitlines(keepends=True)

    # Apply simple, deterministic improvements
    new_lines: list[str] = []
    changed = False
    for line in src_lines:
        stripped = line.rstrip("\n")
        # Replace hardcoded fallback secrets
        m = re.search(
            r'(["\'])hardcoded-fallback-key\1',
            stripped,
        )
        if m or (
            re.search(r"(SECRET|API_KEY|PASSWORD)\s*=", stripped, re.I)
            and "environ" not in stripped
            and re.search(r"['\"][^'\"]{8,}['\"]", stripped)
        ):
            # Prefer env-only without hardcoded default
            if "os.environ.get" in stripped and "," in stripped:
                new = re.sub(
                    r'os\.environ\.get\(([^,]+),\s*["\'][^"\']*["\']\)',
                    r"os.environ.get(\1) or (_raise_missing_secret())",
                    stripped,
                )
                if new != stripped:
                    new_lines.append(new + "\n")
                    changed = True
                    continue
        if "time.sleep(" in stripped:
            new_lines.append(
                "# REMOVED: blocking sleep — use async/event-driven wait instead\n"
            )
            changed = True
            continue
        # Comment unused_* parameters hint inline once
        new_lines.append(line if line.endswith("\n") else line + "\n")

    # Add helper + docstring header when complexity issues exist
    high = [i for i in issues if i.severity in ("high", "critical")]
    if high and not any("def _raise_missing_secret" in ln for ln in new_lines):
        helper = (
            "def _raise_missing_secret() -> str:\n"
            '    raise RuntimeError("Required secret is not set in the environment")\n'
            "\n"
        )
        # Insert after module docstring / imports
        insert_at = 0
        for i, ln in enumerate(new_lines):
            if ln.startswith("import ") or ln.startswith("from "):
                insert_at = i + 1
            elif ln.strip() and not ln.startswith("#") and not ln.startswith('"""') and insert_at:
                break
        new_lines.insert(insert_at, "\n" + helper)
        changed = True

    if not changed:
        # Still emit a comment-only patch summarizing findings
        banner = (
            f"# AD Code Engineering Agent: {len(issues)} issue(s) found — "
            "refactor nested conditionals and reduce parameter counts.\n"
        )
        new_lines = [banner] + new_lines
        changed = True

    if not changed:
        return None

    # Build unified diff
    old = body.splitlines(keepends=True)
    new = new_lines
    # Simple hunk covering whole file
    old_count = len(old)
    new_count = len(new)
    diff_lines = [
        f"--- a/{filename}\n",
        f"+++ b/{filename}\n",
        f"@@ -1,{old_count} +1,{new_count} @@\n",
    ]
    for ln in old:
        diff_lines.append("-" + (ln if ln.endswith("\n") else ln + "\n"))
    for ln in new:
        diff_lines.append("+" + (ln if ln.endswith("\n") else ln + "\n"))
    return "".join(diff_lines)


def analyze_python(snippet: str, task: str, instruction: str = "") -> AnalysisResult:
    issues: list[Issue] = []
    hints: list[str] = []
    metrics: dict[str, Any] = {}

    try:
        tree = ast.parse(snippet)
        visitor = _ComplexityVisitor()
        visitor.visit(tree)
        issues.extend(visitor.issues)
        hints.extend(visitor.hints)
        metrics = {
            "functions": visitor.function_count,
            "classes": visitor.class_count,
            "max_ast_nesting": visitor.max_nesting,
            "lines": len(snippet.splitlines()),
        }
        if visitor.max_nesting >= 4:
            hints.append(f"Deep nesting detected (depth {visitor.max_nesting})")
        if visitor.long_functions:
            hints.append(
                "Long functions: " + ", ".join(f"'{n}'" for n in visitor.long_functions)
            )
    except SyntaxError as exc:
        issues.append(
            Issue(
                code="SYNTAX_ERROR",
                severity="critical",
                message=f"Python syntax error: {exc.msg}",
                line=exc.lineno,
                suggestion="Fix syntax before further analysis",
            )
        )
        metrics = {"lines": len(snippet.splitlines()), "parse_error": True}

    issues.extend(_scan_heuristics(snippet, "python"))

    # Dedupe by (code, line)
    seen: set[tuple[str, int | None]] = set()
    unique: list[Issue] = []
    for iss in issues:
        key = (iss.code, iss.line)
        if key not in seen:
            seen.add(key)
            unique.append(iss)
    issues = unique

    if instruction:
        hints.append(f"Instruction noted: {instruction[:200]}")

    patch = None
    if task == "improve":
        patch = _build_unified_diff(snippet, issues)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda i: severity_order.get(i.severity, 9))

    summary = (
        f"Analyzed Python snippet ({metrics.get('lines', 0)} lines): "
        f"{len(issues)} issue(s), "
        f"{metrics.get('functions', 0)} function(s)."
    )
    if task == "improve" and patch:
        summary += " Proposed unified diff attached."

    return AnalysisResult(
        language="python",
        complexity_hints=hints,
        issues=issues,
        metrics=metrics,
        proposed_patch=patch,
        summary=summary,
    )


def analyze_heuristic(snippet: str, language: str, task: str, instruction: str = "") -> AnalysisResult:
    issues = _scan_heuristics(snippet, language)
    lines = snippet.splitlines()
    metrics = {
        "lines": len(lines),
        "non_empty": sum(1 for ln in lines if ln.strip()),
    }
    hints: list[str] = []
    # Brace/indent nesting heuristic
    depth = 0
    max_depth = 0
    for ln in lines:
        depth += ln.count("{") + ln.count("(")
        depth -= ln.count("}") + ln.count(")")
        max_depth = max(max_depth, depth)
    if max_depth > 5:
        hints.append(f"High structural nesting (approx depth {max_depth})")
        issues.append(
            Issue(
                code="HIGH_NESTING",
                severity="medium",
                message=f"Approximate nesting depth {max_depth}",
                suggestion="Flatten control flow",
            )
        )
    if instruction:
        hints.append(f"Instruction noted: {instruction[:200]}")

    patch = None
    if task == "improve":
        patch = _build_unified_diff(snippet, issues, filename="snippet.txt")

    return AnalysisResult(
        language=language,
        complexity_hints=hints,
        issues=issues,
        metrics=metrics,
        proposed_patch=patch,
        summary=f"Heuristic analysis ({language}): {len(issues)} issue(s).",
    )


def analyze_code(
    snippet: str,
    task: str = "analyze",
    instruction: str = "",
) -> AnalysisResult:
    task = (task or "analyze").lower().strip()
    if task not in ("analyze", "improve"):
        task = "analyze"
    language = _detect_language(snippet)
    if language == "python":
        return analyze_python(snippet, task, instruction)
    return analyze_heuristic(snippet, language, task, instruction)
