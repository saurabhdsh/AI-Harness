"""Real LangGraph AD Code Engineering agent powered by OpenAI."""

from __future__ import annotations

import ast
import json
import operator
import os
import re
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from llm_config import build_chat_model, deployment_or_model, llm_configured, llm_provider

SAMPLE = Path(__file__).resolve().parent.parent / "sample_repo" / "snippet.py"

AGENT_META = {
    "id": "ad-openai-code-engineer",
    "name": "AD OpenAI Code Engineer",
    "framework": "langgraph",
    "model_env": "OPENAI_MODEL",
    "capabilities": [
        "code_analysis",
        "security_review",
        "unified_diff_patches",
        "openai_llm",
        "langgraph_state_graph",
    ],
    "description": (
        "LangGraph StateGraph agent that analyzes code, proposes improvements, "
        "and returns structured engineering results via OpenAI."
    ),
}


class AgentState(TypedDict):
    task: str
    instruction: str
    snippet: str
    language: str
    static_findings: dict[str, Any]
    llm_analysis: dict[str, Any]
    proposed_patch: str
    summary: str
    messages: Annotated[list, operator.add]
    errors: Annotated[list[str], operator.add]


def _detect_language(snippet: str) -> str:
    if re.search(r"^\s*(def |class |import |from \w+ import)", snippet, re.M):
        return "python"
    if re.search(r"^\s*(function |const |let |var |export )", snippet, re.M):
        return "javascript"
    return "unknown"


def _static_python(snippet: str) -> dict[str, Any]:
    findings: dict[str, Any] = {
        "issues": [],
        "metrics": {},
        "hints": [],
    }
    try:
        tree = ast.parse(snippet)
    except SyntaxError as exc:
        findings["issues"].append(
            {"code": "syntax_error", "severity": "high", "message": str(exc)}
        )
        return findings

    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    findings["metrics"] = {
        "functions": len(funcs),
        "classes": sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef)),
        "lines": len(snippet.splitlines()),
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings["issues"].append(
                {
                    "code": "bare_except",
                    "severity": "high",
                    "message": f"Bare except at line {node.lineno}",
                    "line": node.lineno,
                }
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # heuristic: string concat into SQL-like queries
            pass

    if "SELECT" in snippet.upper() and ("+" in snippet or "f\"" in snippet or "f'" in snippet):
        findings["issues"].append(
            {
                "code": "sql_injection_risk",
                "severity": "critical",
                "message": "Possible SQL string concatenation / interpolation",
            }
        )
        findings["hints"].append("Use parameterized queries")

    if "for " in snippet and snippet.count("for ") >= 2:
        findings["hints"].append("Nested iteration detected — check complexity")

    return findings


def _llm():
    # OpenAI or Azure OpenAI — json_object mode reduces malformed responses
    return build_chat_model(temperature=0.1, json_mode=True)


def node_ingest(state: AgentState) -> dict[str, Any]:
    snippet = state.get("snippet") or ""
    if not snippet.strip():
        raise ValueError("snippet is required (or use_sample=true)")
    language = _detect_language(snippet)
    return {
        "language": language,
        "messages": [
            {
                "role": "system",
                "content": f"Ingested {len(snippet)} chars as {language}",
                "node": "ingest",
            }
        ],
    }


def node_static(state: AgentState) -> dict[str, Any]:
    if state["language"] == "python":
        findings = _static_python(state["snippet"])
    else:
        findings = {
            "issues": [],
            "metrics": {"lines": len(state["snippet"].splitlines())},
            "hints": ["Non-python static analysis limited"],
        }
    return {
        "static_findings": findings,
        "messages": [
            {
                "role": "assistant",
                "content": f"Static analysis found {len(findings.get('issues', []))} issues",
                "node": "static_analysis",
            }
        ],
    }


def node_llm_review(state: AgentState) -> dict[str, Any]:
    task = state.get("task") or "analyze"
    instruction = state.get("instruction") or ""
    static = state.get("static_findings") or {}

    system = SystemMessage(
        content=(
            "You are an Application Development code engineering agent. "
            "Return STRICT JSON with keys: "
            "summary (string), issues (array of {code,severity,message,line?}), "
            "recommendations (array of strings), "
            "proposed_patch (unified diff string or empty), "
            "risk_score (0-100 integer). "
            "Be concrete. Prefer security and correctness findings."
        )
    )
    human = HumanMessage(
        content=(
            f"Task: {task}\n"
            f"Extra instruction: {instruction or 'none'}\n"
            f"Language: {state.get('language')}\n"
            f"Static findings JSON:\n{json.dumps(static)}\n\n"
            f"Source code:\n```\n{state['snippet']}\n```\n"
        )
    )

    last_error: Exception | None = None
    parsed: dict[str, Any] | None = None
    for attempt in range(2):
        try:
            resp = _llm().invoke([system, human])
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            parsed = _extract_json(text)
            break
        except Exception as exc:  # noqa: BLE001 — retry once, then surface real failure
            last_error = exc
            human = HumanMessage(
                content=(
                    f"Your previous answer was invalid JSON ({exc}). "
                    "Return ONLY a valid JSON object with keys summary, issues, "
                    "recommendations, proposed_patch, risk_score.\n\n"
                    f"Task: {task}\nLanguage: {state.get('language')}\n"
                    f"Static findings:\n{json.dumps(static)}\n\n"
                    f"Source:\n```\n{state['snippet']}\n```\n"
                )
            )

    if parsed is None:
        return {
            "llm_analysis": {},
            "errors": [f"llm_review_failed: {last_error}"],
            "messages": [
                {
                    "role": "assistant",
                    "content": f"LLM review failed: {last_error}",
                    "node": "llm_review",
                    "status": "error",
                }
            ],
        }

    patch = parsed.get("proposed_patch") or ""
    return {
        "llm_analysis": parsed,
        "proposed_patch": patch if isinstance(patch, str) else "",
        "summary": str(parsed.get("summary") or ""),
        "messages": [
            {
                "role": "assistant",
                "content": str(parsed.get("summary") or "LLM review complete")[:400],
                "node": "llm_review",
            }
        ],
    }


def node_synthesize(state: AgentState) -> dict[str, Any]:
    static = state.get("static_findings") or {}
    llm = state.get("llm_analysis") or {}
    issues = list(static.get("issues") or [])
    for item in llm.get("issues") or []:
        if isinstance(item, dict):
            issues.append(item)

    summary = state.get("summary") or llm.get("summary") or "Analysis complete"
    if state.get("errors"):
        summary = f"{summary} (with errors: {'; '.join(state['errors'])})"

    return {
        "summary": summary,
        "llm_analysis": {
            **llm,
            "merged_issues": issues,
            "static_metrics": static.get("metrics") or {},
            "static_hints": static.get("hints") or [],
        },
        "messages": [
            {
                "role": "assistant",
                "content": "Synthesized engineering profile",
                "node": "synthesize",
            }
        ],
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError("LLM did not return parseable JSON")


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("ingest", node_ingest)
    g.add_node("static_analysis", node_static)
    g.add_node("llm_review", node_llm_review)
    g.add_node("synthesize", node_synthesize)
    g.set_entry_point("ingest")
    g.add_edge("ingest", "static_analysis")
    g.add_edge("static_analysis", "llm_review")
    g.add_edge("llm_review", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def resolve_snippet(payload: dict[str, Any]) -> str:
    snippet = (
        payload.get("repo_snippet")
        or payload.get("code")
        or payload.get("snippet")
        or payload.get("source")
    )
    if snippet:
        return str(snippet)
    if payload.get("use_sample") or payload.get("sample"):
        return SAMPLE.read_text(encoding="utf-8")
    raise ValueError("Missing repo_snippet (or set use_sample=true)")


def run_agent(payload: dict[str, Any]) -> dict[str, Any]:
    if not llm_configured():
        raise RuntimeError(
            "No LLM credentials — set OPENAI_API_KEY or "
            "AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT. Refusing to mock responses."
        )

    snippet = resolve_snippet(payload)
    task = str(payload.get("task") or "analyze").lower()
    instruction = str(payload.get("instruction") or "")

    initial: AgentState = {
        "task": task,
        "instruction": instruction,
        "snippet": snippet,
        "language": "",
        "static_findings": {},
        "llm_analysis": {},
        "proposed_patch": "",
        "summary": "",
        "messages": [],
        "errors": [],
    }

    result = get_graph().invoke(initial)
    llm = result.get("llm_analysis") or {}
    output = {
        "agent_id": AGENT_META["id"],
        "task": task,
        "language": result.get("language"),
        "summary": result.get("summary"),
        "issues": llm.get("merged_issues") or llm.get("issues") or [],
        "recommendations": llm.get("recommendations") or [],
        "proposed_patch": result.get("proposed_patch") or llm.get("proposed_patch") or "",
        "risk_score": llm.get("risk_score"),
        "metrics": llm.get("static_metrics") or {},
        "hints": llm.get("static_hints") or [],
        "model": deployment_or_model(),
        "llm_provider": llm_provider(),
        "framework": "langgraph",
        "errors": result.get("errors") or [],
    }
    return {
        "output": output,
        "messages": result.get("messages") or [],
        "metadata": {
            "model": output["model"],
            "llm_provider": output["llm_provider"],
            "agent_id": AGENT_META["id"],
            "framework": "langgraph",
            "openai": output["llm_provider"] in {"openai", "azure"},
            "nodes": ["ingest", "static_analysis", "llm_review", "synthesize"],
        },
    }
