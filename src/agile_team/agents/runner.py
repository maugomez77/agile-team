from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import agile_team.llm.providers.ollama_provider  # noqa: F401 - registers provider
import agile_team.llm.providers.deepseek_provider  # noqa: F401 - registers provider

from agile_team.llm.base import LLMFactory
from agile_team.shared.config import AgentDefinition, LLMConfig, TeamConfig
from agile_team.shared.models import ActivityEntry, Artifact, ArtifactType, Task, TaskStatus


async def run_agent_on_task(
    task: Task,
    agent_def: AgentDefinition,
    config: TeamConfig,
) -> Artifact:
    """Execute an agent on a task: call LLM, produce artifact, return it."""

    llm_config = config.llm
    if agent_def.llm.provider != "ollama" or agent_def.llm.model != "llama3.2":
        llm_config = agent_def.llm

    api_key = llm_config.api_key.strip() if llm_config.api_key else ""
    provider = LLMFactory.create(
        provider=llm_config.provider,
        model=llm_config.model,
        base_url=llm_config.base_url,
        api_key=api_key,
        temperature=llm_config.temperature,
        max_tokens=llm_config.max_tokens,
    )

    context = _build_context(task, agent_def, config)

    system = agent_def.system_prompt or f"You are {agent_def.name}. {agent_def.role}."
    response = await provider.generate(context, system_prompt=system)

    artifact_type = ArtifactType(agent_def.artifact_type) if agent_def.artifact_type else ArtifactType.SPECIFICATION

    artifact = Artifact(
        task_id=task.id,
        artifact_type=artifact_type,
        content=response.strip(),
        created_by=agent_def.id,
    )
    return artifact


def _build_context(task: Task, agent_def: AgentDefinition, config: TeamConfig) -> str:
    """Build a rich context prompt for the agent with plan-first reasoning."""

    prev_artifacts = []
    has_open_questions = False
    for art in task.artifacts:
        prefix = ""
        if art.created_by == agent_def.id and "QUESTIONS:" in art.content[:100]:
            prefix = "⚠️ YOUR PREVIOUS UNANSWERED QUESTIONS: "
            has_open_questions = True
        prev_artifacts.append(
            f"{prefix}--- {art.artifact_type.value.upper()} (by {art.created_by}) ---\n{art.content[:2000]}"
        )

    feedback_lines = list(task.feedback_notes) if task.feedback_notes else []
    recent_comments = [e for e in task.activity_log if e.action in ("commented", "questions")]
    if recent_comments:
        for c in recent_comments[-5:]:
            feedback_lines.append(f"[{c.agent}]: {c.message}")

    feedback = "\n".join(f"  - {f}" for f in feedback_lines) if feedback_lines else "None"

    pipeline_info = ""
    for stage in config.pipeline:
        marker = " ← CURRENT" if stage.id == task.status.value else ""
        pipeline_info += f"  [{stage.label}]{marker}\n"

    output_options = agent_def.get_output_stages()
    stage_labels = {s.id: s.label for s in config.pipeline}
    routing_info = ""
    if len(output_options) > 1:
        routing_info = "\nAVAILABLE ROUTES (choose one):\n"
        for sid in output_options:
            routing_info += f"  OUTPUT_STAGE: {sid} → {stage_labels.get(sid, sid)}\n"
        routing_info += "\nSpecify your chosen route by including 'OUTPUT_STAGE: <id>' at the END of your response.\n"
    elif output_options:
        routing_info = f"\nYou will route the task to: {stage_labels.get(output_options[0], output_options[0])}\n"

    open_questions_warning = ""
    if has_open_questions:
        open_questions_warning = (
            "\n⚠️  YOU HAVE OPEN QUESTIONS from a previous run that have NOT been answered yet. "
            "DO NOT advance the task. Instead, re-iterate your questions or wait for responses. "
            "Only produce a final artifact when all questions are resolved.\n"
        )

    return f"""TASK: {task.title}
DESCRIPTION: {task.description}
PRIORITY: P{task.priority}
CURRENT STAGE: {task.status.value}
{open_questions_warning}
PIPELINE:
{pipeline_info}

YOUR ROLE: {agent_def.name} — {agent_def.role}
YOUR INPUT STAGE: {agent_def.input_stage}
YOU PRODUCE: {agent_def.artifact_type}
{routing_info}
PREVIOUS FEEDBACK & COMMENTS:
{feedback}

PREVIOUS ARTIFACTS:
{chr(10).join(prev_artifacts) if prev_artifacts else '(none - you are the first agent on this task)'}

---
REASONING PROTOCOL (follow this structure):

STEP 1 — PLAN:
Analyze the task and previous work. List 3-7 concrete steps you will take.
Start with: "PLAN:"

STEP 2 — REMOVE AMBIGUITY:
If anything is unclear or missing, STOP and ask instead of guessing.
Start with: "QUESTIONS:" (list numbered questions)

STEP 3 — EXECUTE:
Produce your {agent_def.artifact_type}. Start with your artifact type in caps
(e.g. "SPECIFICATION:", "ARCHITECTURE:", "CODE:", "TEST RESULTS:", "DEPLOY:")

STEP 4 — VERIFY:
Check your work against the spec and acceptance criteria. Note any risks.
Start with: "VERIFY:"

STEP 5 — ROUTE:
Choose the output stage. Include: "OUTPUT_STAGE: <id>"

Be thorough, specific, and actionable.
"""
