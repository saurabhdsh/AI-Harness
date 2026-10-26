"""Domain agents registry — AD / AMS / QE."""

from __future__ import annotations

from agents.change_assessor import AGENT_META as AMS_CHANGE
from agents.change_assessor import run as run_change
from agents.defect_triage import AGENT_META as QE_DEFECT
from agents.defect_triage import run as run_defect
from agents.incident_analyst import AGENT_META as AMS_INCIDENT
from agents.incident_analyst import run as run_incident
from agents.sprint_planner import AGENT_META as AD_SPRINT
from agents.sprint_planner import run as run_sprint
from agents.tech_design import AGENT_META as AD_TECH
from agents.tech_design import run as run_tech
from agents.test_designer import AGENT_META as QE_TEST
from agents.test_designer import run as run_test
from agents.user_story import AGENT_META as AD_STORY
from agents.user_story import run as run_story

AGENTS: dict[str, dict] = {
    AD_STORY["id"]: {"meta": AD_STORY, "run": run_story},
    AD_SPRINT["id"]: {"meta": AD_SPRINT, "run": run_sprint},
    AD_TECH["id"]: {"meta": AD_TECH, "run": run_tech},
    AMS_INCIDENT["id"]: {"meta": AMS_INCIDENT, "run": run_incident},
    AMS_CHANGE["id"]: {"meta": AMS_CHANGE, "run": run_change},
    QE_TEST["id"]: {"meta": QE_TEST, "run": run_test},
    QE_DEFECT["id"]: {"meta": QE_DEFECT, "run": run_defect},
}


def list_agent_metas() -> list[dict]:
    return [v["meta"] for v in AGENTS.values()]
