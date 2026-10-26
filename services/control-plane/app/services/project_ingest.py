"""Ingest local paths and uploaded agent projects for framework detection."""

from __future__ import annotations

import io
import os
import shutil
import uuid
import zipfile
from pathlib import Path

from app.core.config import get_settings
from app.services.framework_detector import DetectionResult, detect_framework_at_path


def _allowed_roots() -> list[Path]:
    settings = get_settings()
    roots: list[Path] = []
    # Explicit allowlist from env (colon-separated)
    raw = os.getenv("HARNESS_PROJECT_ALLOWLIST", "") or getattr(
        settings, "project_allowlist", ""
    )
    if raw:
        for part in raw.split(":"):
            part = part.strip()
            if part:
                roots.append(Path(part).expanduser().resolve())
    # Default: workspace parent of control-plane (…/AI-Harness)
    here = Path(__file__).resolve()
    # services/control-plane/app/services/project_ingest.py → AI-Harness
    workspace = here.parents[4] if len(here.parents) >= 5 else here.parents[-1]
    roots.append(workspace.resolve())
    # Also allow examples under cwd
    roots.append(Path.cwd().resolve())
    # Dedupe
    uniq: list[Path] = []
    for r in roots:
        if r not in uniq:
            uniq.append(r)
    return uniq


def assert_path_allowed(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    allowed = _allowed_roots()
    ok = False
    for root in allowed:
        try:
            resolved.relative_to(root)
            ok = True
            break
        except ValueError:
            if resolved == root:
                ok = True
                break
    if not ok:
        raise PermissionError(
            f"Path {resolved} is outside the allowlisted project roots. "
            f"Set HARNESS_PROJECT_ALLOWLIST or place the project under {allowed[0]}"
        )
    if not resolved.is_dir():
        raise NotADirectoryError(f"Expected a project directory, got file: {resolved}")
    return resolved


def upload_root() -> Path:
    settings = get_settings()
    base = Path(os.getenv("HARNESS_UPLOAD_DIR", "") or getattr(settings, "upload_dir", "") or "data/uploads")
    if not base.is_absolute():
        # relative to control-plane service root
        base = Path(__file__).resolve().parents[2] / base
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_upload_zip(tenant_id: str, filename: str, content: bytes) -> tuple[str, Path]:
    if not filename.lower().endswith(".zip"):
        raise ValueError("Only .zip project uploads are supported")
    if len(content) > 40 * 1024 * 1024:
        raise ValueError("Upload exceeds 40MB limit")

    upload_id = str(uuid.uuid4())
    dest = upload_root() / tenant_id / upload_id
    dest.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Zip-slip protection
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise ValueError(f"Illegal zip path: {info.filename}")
            zf.extractall(dest)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError("Invalid zip archive") from exc

    # If zip contained a single top-level folder, use that as project root
    children = [p for p in dest.iterdir() if p.name != "__MACOSX"]
    project_root = children[0] if len(children) == 1 and children[0].is_dir() else dest
    # Write marker
    (dest / ".harness_upload.json").write_text(
        f'{{"upload_id":"{upload_id}","filename":{filename!r},"project_root":"{project_root}"}}',
        encoding="utf-8",
    )
    return upload_id, project_root


def resolve_upload_project(tenant_id: str, upload_id: str) -> Path:
    dest = upload_root() / tenant_id / upload_id
    if not dest.exists():
        raise FileNotFoundError(f"Unknown upload_id: {upload_id}")
    marker = dest / ".harness_upload.json"
    if marker.exists():
        import json

        data = json.loads(marker.read_text(encoding="utf-8"))
        root = Path(data.get("project_root") or dest)
        if root.exists():
            return root
    children = [p for p in dest.iterdir() if p.name not in {"__MACOSX", ".harness_upload.json"}]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return dest


def detect_path(path: str) -> DetectionResult:
    root = assert_path_allowed(Path(path))
    return detect_framework_at_path(root)


def detect_upload(tenant_id: str, upload_id: str) -> DetectionResult:
    root = resolve_upload_project(tenant_id, upload_id)
    return detect_framework_at_path(root)
