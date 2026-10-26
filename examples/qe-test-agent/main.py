"""QE Test Agent — generate pytest stubs from requirements text and validate structure."""

from __future__ import annotations

import ast
import os
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="TCS AI Harness — QE Test Agent",
    description="Generate pytest stubs from requirements; validate test module structure",
    version="1.0.0",
)


class InvokeBody(BaseModel):
    input: dict[str, Any] | str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None


def _normalize(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"action": "generate", "requirements": raw}
    if isinstance(raw, dict):
        return raw
    return {"requirements": str(raw)}


def _extract_requirements(text: str) -> list[str]:
    """Split requirements into atomic items (bullets, numbered, or sentences)."""
    items: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip bullet / number prefixes
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if len(line) > 8:
            items.append(line)
    if not items and text.strip():
        # Sentence split fallback
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        items = [p.strip() for p in parts if len(p.strip()) > 8]
    return items[:40]  # cap


def _slug(s: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    return (slug[:max_len] or "requirement").rstrip("_")


def generate_pytest_stubs(requirements_text: str, module_name: str = "test_generated") -> dict[str, Any]:
    reqs = _extract_requirements(requirements_text)
    if not reqs:
        raise HTTPException(status_code=400, detail="No requirements text provided")

    lines = [
        '"""Auto-generated pytest stubs from requirements — fill in assertions."""',
        "",
        "import pytest",
        "",
        "",
        "# Shared fixtures",
        "@pytest.fixture",
        "def context():",
        '    """Arrange shared test context / system under test."""',
        "    return {}",
        "",
        "",
    ]

    test_names: list[str] = []
    for i, req in enumerate(reqs, 1):
        name = f"test_{_slug(req)}"
        # Ensure uniqueness
        base = name
        n = 2
        while name in test_names:
            name = f"{base}_{n}"
            n += 1
        test_names.append(name)
        lines.append(f"def {name}(context):")
        lines.append(f'    """REQ-{i:03d}: {req[:120]}"""')
        lines.append("    # Arrange")
        lines.append("    # Act")
        lines.append("    # Assert — replace with real checks")
        lines.append(f'    assert context is not None, "Implement: {req[:60]}"')
        lines.append("")
        lines.append("")

    source = "\n".join(lines).rstrip() + "\n"
    return {
        "module_name": module_name if module_name.endswith(".py") else f"{module_name}.py",
        "test_count": len(test_names),
        "test_names": test_names,
        "requirements_mapped": [
            {"id": f"REQ-{i:03d}", "text": r, "test": t}
            for i, (r, t) in enumerate(zip(reqs, test_names), 1)
        ],
        "source": source,
    }


def validate_test_structure(source: str) -> dict[str, Any]:
    """Validate that a pytest module has a sensible structure (AST-based)."""
    issues: list[dict[str, Any]] = []
    checks = {
        "parses": False,
        "has_test_functions": False,
        "has_assert_or_pytest": False,
        "imports_pytest": False,
        "naming_ok": True,
    }

    try:
        tree = ast.parse(source)
        checks["parses"] = True
    except SyntaxError as exc:
        return {
            "valid": False,
            "checks": checks,
            "issues": [
                {
                    "code": "SYNTAX_ERROR",
                    "message": str(exc.msg),
                    "line": exc.lineno,
                }
            ],
            "test_functions": [],
        }

    test_fns: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                test_fns.append(node.name)
            elif any(
                isinstance(d, ast.Name) and d.id == "pytest"
                or (isinstance(d, ast.Attribute) and d.attr == "mark")
                for d in node.decorator_list
                for d in ([d] if not isinstance(d, list) else d)
            ):
                pass
            elif not node.name.startswith("_") and "test" in node.name.lower():
                checks["naming_ok"] = False
                issues.append(
                    {
                        "code": "BAD_NAME",
                        "message": f"Function '{node.name}' looks like a test but does not start with test_",
                        "line": node.lineno,
                    }
                )

    checks["has_test_functions"] = len(test_fns) > 0
    if not checks["has_test_functions"]:
        issues.append(
            {
                "code": "NO_TESTS",
                "message": "No functions named test_* found",
                "line": None,
            }
        )

    src_lower = source.lower()
    checks["imports_pytest"] = "import pytest" in source or "from pytest" in source
    checks["has_assert_or_pytest"] = "assert " in source or "pytest." in source
    if not checks["has_assert_or_pytest"]:
        issues.append(
            {
                "code": "NO_ASSERTIONS",
                "message": "No assert statements or pytest.* calls found",
                "line": None,
            }
        )

    # Empty test bodies
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            body = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(getattr(n, "value", None), ast.Constant)]
            # allow docstring-only + pass
            meaningful = [
                n
                for n in node.body
                if not (
                    isinstance(n, ast.Pass)
                    or (
                        isinstance(n, ast.Expr)
                        and isinstance(getattr(n, "value", None), ast.Constant)
                        and isinstance(n.value.value, str)
                    )
                )
            ]
            if not meaningful:
                issues.append(
                    {
                        "code": "EMPTY_TEST",
                        "message": f"Test '{node.name}' has empty body",
                        "line": node.lineno,
                    }
                )

    valid = checks["parses"] and checks["has_test_functions"] and checks["has_assert_or_pytest"]
    return {
        "valid": valid,
        "checks": checks,
        "issues": issues,
        "test_functions": test_fns,
        "score": round(
            sum(1 for v in checks.values() if v) / max(len(checks), 1),
            2,
        ),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "qe-test-agent"}


@app.post("/invoke")
def invoke(body: InvokeBody) -> dict[str, Any]:
    started = time.perf_counter()
    payload = _normalize(body.input)
    action = str(payload.get("action") or payload.get("task") or "generate").lower()

    if action in ("generate", "stubs", "create"):
        reqs = str(
            payload.get("requirements")
            or payload.get("text")
            or payload.get("spec")
            or ""
        )
        module = str(payload.get("module_name") or "test_generated")
        result = generate_pytest_stubs(reqs, module)
        output = {"action": "generate", **result}
        message = f"Generated {result['test_count']} pytest stubs"
    elif action in ("validate", "check", "lint"):
        source = str(payload.get("source") or payload.get("code") or payload.get("test_code") or "")
        if not source:
            raise HTTPException(status_code=400, detail="Provide source/code for validate")
        result = validate_test_structure(source)
        output = {"action": "validate", **result}
        message = f"Validation {'passed' if result['valid'] else 'failed'} ({len(result['issues'])} issues)"
    else:
        raise HTTPException(
            status_code=400,
            detail="action must be 'generate' or 'validate'",
        )

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "output": output,
        "messages": [{"role": "assistant", "content": message}],
        "metadata": {
            "latency_ms": latency_ms,
            "model": "qe-stub-generator",
            "run_id": str(uuid.uuid4()),
            "agent_id": body.agent_id or "qe-test",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8083")),
        reload=False,
    )
