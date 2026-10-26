"""Detect agent frameworks from source trees (path or uploaded project).

Real static analysis of Python/JS/config files — no invented cloud discovery.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Directories skipped during scan
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".tox",
    ".idea",
    ".cursor",
}

_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".md",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
}


@dataclass
class FrameworkSignal:
    framework: str
    weight: float
    evidence: str
    file: str | None = None


@dataclass
class DetectionResult:
    root: str
    frameworks: list[dict[str, Any]] = field(default_factory=list)
    primary: str | None = None
    confidence: float = 0.0
    recommended_connector: str | None = None
    invoke_hints: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    files_scanned: int = 0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    cloud_targets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "frameworks": self.frameworks,
            "primary": self.primary,
            "confidence": self.confidence,
            "recommended_connector": self.recommended_connector,
            "invoke_hints": self.invoke_hints,
            "entrypoints": self.entrypoints,
            "files_scanned": self.files_scanned,
            "evidence": self.evidence[:40],
            "cloud_targets": self.cloud_targets,
            "notes": self.notes,
        }


# framework -> connector type mapping
CONNECTOR_FOR_FRAMEWORK = {
    "langgraph": "langgraph",
    "langchain": "langgraph",  # invoke via REST/LangGraph-style surface when exposed
    "crewai": "crewai",
    "autogen": "generic_rest",
    "semantic_kernel": "generic_rest",
    "llamaindex": "generic_rest",
    "fastapi_agent": "generic_rest",
    "bedrock": "aws_bedrock",
    "bedrock_agentcore": "aws_bedrock",
    "azure_foundry": "azure_foundry",
    "azure_ai_agent": "azure_foundry",
    "copilot_studio": "generic_rest",
    "openai_assistants": "generic_rest",
    "servicenow": "servicenow",
    "service_now": "servicenow",
    "mulesoft": "mulesoft",
    "anypoint": "mulesoft",
    "agent_fabric": "mulesoft",
}


def _iter_source_files(root: Path, limit: int = 400) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if path.stat().st_size > 1_500_000:
            continue
        files.append(path)
        if len(files) >= limit:
            break
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _score_python_imports(path: Path, text: str) -> list[FrameworkSignal]:
    signals: list[FrameworkSignal] = []
    try:
        tree = ast.parse(text)
        mods: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
                mods.add(node.module)
    except SyntaxError:
        mods = set(re.findall(r"^\s*(?:from|import)\s+([\w\.]+)", text, re.M))

    mapping = [
        ("langgraph", {"langgraph"}, 0.95, "import langgraph"),
        ("langchain", {"langchain", "langchain_core", "langchain_openai"}, 0.55, "import langchain*"),
        ("crewai", {"crewai"}, 0.95, "import crewai"),
        ("autogen", {"autogen", "autogen_agentchat"}, 0.9, "import autogen"),
        ("semantic_kernel", {"semantic_kernel"}, 0.9, "import semantic_kernel"),
        ("llamaindex", {"llama_index", "llamaindex"}, 0.85, "import llama_index"),
        ("bedrock", {"boto3", "bedrock_agent", "bedrock_agent_runtime"}, 0.45, "AWS Bedrock SDK usage"),
        ("azure_foundry", {"azure", "azure.ai", "azure.ai.projects", "azure.ai.agents"}, 0.5, "Azure AI SDK"),
        ("fastapi_agent", {"fastapi"}, 0.35, "FastAPI service surface"),
    ]
    for framework, keys, weight, evidence in mapping:
        if any(m == k or m.startswith(k + ".") for m in mods for k in keys):
            signals.append(
                FrameworkSignal(framework, weight, evidence, str(path))
            )

    # Stronger LangGraph graph APIs
    if "StateGraph" in text or "langgraph.graph" in text:
        signals.append(
            FrameworkSignal("langgraph", 0.98, "StateGraph / langgraph.graph usage", str(path))
        )
    if "Crew(" in text or "Agent(" in text and "crewai" in text.lower():
        signals.append(FrameworkSignal("crewai", 0.92, "Crew/Agent construct", str(path)))
    if re.search(r"bedrock[-_]agent|invoke_agent|AmazonBedrock", text, re.I):
        signals.append(FrameworkSignal("bedrock", 0.85, "Bedrock agent API usage", str(path)))
    if re.search(r"AIProjectClient|AzureAIAgent|azure\.ai\.agents", text):
        signals.append(
            FrameworkSignal("azure_foundry", 0.9, "Azure AI Foundry / Agents SDK", str(path))
        )
    if "@app.post" in text and ("/invoke" in text or "/runs" in text):
        signals.append(
            FrameworkSignal("fastapi_agent", 0.7, "FastAPI /invoke or /runs endpoint", str(path))
        )
    return signals


def _score_manifests(path: Path, text: str) -> list[FrameworkSignal]:
    signals: list[FrameworkSignal] = []
    name = path.name.lower()
    lower = text.lower()
    if name in {"requirements.txt", "pyproject.toml", "package.json", "poetry.lock"}:
        checks = [
            ("langgraph", "langgraph", 0.9),
            ("langchain", "langchain", 0.5),
            ("crewai", "crewai", 0.9),
            ("autogen", "autogen", 0.85),
            ("llamaindex", "llama-index", 0.8),
            ("bedrock", "boto3", 0.35),
            ("azure_foundry", "azure-ai", 0.7),
            ("fastapi_agent", "fastapi", 0.4),
        ]
        for framework, needle, weight in checks:
            if needle in lower:
                signals.append(
                    FrameworkSignal(
                        framework, weight, f"{name} dependency: {needle}", str(path)
                    )
                )
    if name.endswith((".yml", ".yaml", ".json")) and "bedrock" in lower:
        signals.append(FrameworkSignal("bedrock", 0.6, "Config mentions bedrock", str(path)))
    if "copilot studio" in lower or "copilotstudio" in lower:
        signals.append(
            FrameworkSignal("copilot_studio", 0.7, "Copilot Studio reference", str(path))
        )
    if "service-now" in lower or "servicenow" in lower or "sn_aia" in lower:
        signals.append(
            FrameworkSignal("servicenow", 0.75, "ServiceNow / AI Agent Studio reference", str(path))
        )
    if "mulesoft" in lower or "anypoint" in lower or "agent fabric" in lower:
        signals.append(
            FrameworkSignal("mulesoft", 0.75, "MuleSoft / Agent Fabric reference", str(path))
        )
    return signals


def _find_entrypoints(root: Path, files: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in files:
        if path.name in {"main.py", "app.py", "server.py", "agent.py", "graph.py"}:
            hits.append(str(path.relative_to(root)))
        text = _read_text(path) if path.suffix == ".py" else ""
        if "uvicorn" in text and "FastAPI" in text:
            rel = str(path.relative_to(root))
            if rel not in hits:
                hits.append(rel)
    return hits[:12]


def _invoke_hints(root: Path, files: list[Path], primary: str | None) -> list[str]:
    hints: list[str] = []
    for path in files:
        if path.suffix != ".py":
            continue
        text = _read_text(path)
        for route in ("/invoke", "/runs", "/agent", "/chat", "/predict"):
            if f'"{route}"' in text or f"'{route}'" in text or f"/{route.strip('/')}" in text:
                hints.append(route)
    # dedupe
    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    if primary == "langgraph" and "/invoke" not in out:
        out.insert(0, "/invoke")
    if primary == "crewai" and "/invoke" not in out:
        out.append("/invoke")
    return out[:8]


def detect_framework_at_path(root: str | Path) -> DetectionResult:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Path does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root_path}")

    files = _iter_source_files(root_path)
    signals: list[FrameworkSignal] = []
    for path in files:
        text = _read_text(path)
        if path.suffix == ".py":
            signals.extend(_score_python_imports(path, text))
        signals.extend(_score_manifests(path, text))

    # Aggregate scores
    scores: dict[str, float] = {}
    evidence: list[dict[str, Any]] = []
    for sig in signals:
        scores[sig.framework] = max(scores.get(sig.framework, 0.0), sig.weight)
        # accumulate slight boost for repeated evidence
        scores[sig.framework] = min(1.0, scores[sig.framework] + 0.02)
        evidence.append(
            {
                "framework": sig.framework,
                "weight": sig.weight,
                "evidence": sig.evidence,
                "file": sig.file,
            }
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    frameworks = [{"id": k, "score": round(v, 3)} for k, v in ranked]
    primary = ranked[0][0] if ranked else None
    confidence = float(ranked[0][1]) if ranked else 0.0

    cloud_targets: list[str] = []
    if "bedrock" in scores:
        cloud_targets.append("aws_bedrock")
    if "azure_foundry" in scores or "azure_ai_agent" in scores:
        cloud_targets.append("azure_foundry")
    if "copilot_studio" in scores:
        cloud_targets.append("copilot_studio")
    if "servicenow" in scores or "service_now" in scores:
        cloud_targets.append("servicenow")
    if "mulesoft" in scores or "anypoint" in scores or "agent_fabric" in scores:
        cloud_targets.append("mulesoft")

    notes: list[str] = []
    if not primary:
        notes.append(
            "No known agent framework fingerprints found. "
            "You can still onboard via Generic REST if the project exposes HTTP."
        )
    if primary in {"bedrock", "azure_foundry", "servicenow", "mulesoft"}:
        notes.append(
            "Platform-hosted agent detected. "
            "Provide platform credentials/secret_ref and instance/runtime URL — "
            "Harness will not invent discovery results."
        )
    if primary in {"langgraph", "crewai", "fastapi_agent", "langchain"}:
        notes.append(
            "Local/source agent project detected. Provide the running base URL "
            "(or start the service) so Harness can validate and register it without rewriting code."
        )

    connector = CONNECTOR_FOR_FRAMEWORK.get(primary or "", "generic_rest")
    entrypoints = _find_entrypoints(root_path, files)
    hints = _invoke_hints(root_path, files, primary)

    return DetectionResult(
        root=str(root_path),
        frameworks=frameworks,
        primary=primary,
        confidence=round(confidence, 3),
        recommended_connector=connector,
        invoke_hints=hints,
        entrypoints=entrypoints,
        files_scanned=len(files),
        evidence=evidence,
        cloud_targets=cloud_targets,
        notes=notes,
    )
