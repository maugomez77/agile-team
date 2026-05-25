from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "ollama"
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096


class PipelineStage(BaseModel):
    """A single column in the kanban board."""
    id: str
    label: str
    color: str = "#8b949e"
    wip_limit: int = 0


class TaskField(BaseModel):
    """A custom field on task cards."""
    key: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = []
    default: str = ""


class AgentDefinition(BaseModel):
    """Definition of a specialized agent, optionally with a team under them."""
    id: str
    name: str
    icon: str = "?"
    role: str = ""
    input_stage: str = ""
    output_stage: str = ""
    artifact_type: str = ""
    system_prompt: str = ""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    enabled: bool = True
    team: list[AgentDefinition] = Field(default_factory=list)
    team_mode: str = "parallel"
    review_required: bool = True
    output_stages: list[str] = Field(default_factory=list)
    replicas: int = 1
    min_replicas: int = 1
    max_replicas: int = 1

    @property
    def is_lead(self) -> bool:
        return len(self.team) > 0

    def get_output_stages(self) -> list[str]:
        if self.output_stages:
            return self.output_stages
        if self.output_stage:
            return [self.output_stage]
        return []

    @property
    def total_members(self) -> int:
        return 1 + sum(m.total_members for m in self.team)


class TeamConfig(BaseModel):
    """Fully configurable agile team: pipeline, agents, and task fields."""
    name: str = "Agile Team"
    description: str = ""
    pipeline: list[PipelineStage] = Field(default_factory=list)
    agents: list[AgentDefinition] = Field(default_factory=list)
    task_fields: list[TaskField] = Field(default_factory=list)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @property
    def stage_ids(self) -> list[str]:
        return [s.id for s in self.pipeline]

    @property
    def enabled_agents(self) -> list[AgentDefinition]:
        return [a for a in self.agents if a.enabled]

    def get_agent(self, agent_id: str) -> Optional[AgentDefinition]:
        for a in self.agents:
            if a.id == agent_id:
                return a
        return None

    def get_stage(self, stage_id: str) -> Optional[PipelineStage]:
        for s in self.pipeline:
            if s.id == stage_id:
                return s
        return None

    @classmethod
    def default(cls) -> TeamConfig:
        """Default 7-stage pipeline with 6 agents."""
        return cls(
            name="Full Agile Team",
            description="Complete software development pipeline",
            pipeline=[
                PipelineStage(id="backlog", label="Backlog", color="#8b949e"),
                PipelineStage(id="spec_ready", label="Spec Ready", color="#58a6ff"),
                PipelineStage(id="arch_ready", label="Arch Ready", color="#bc8cff"),
                PipelineStage(id="code_ready", label="Code Ready", color="#3fb950"),
                PipelineStage(id="test_ready", label="Test Ready", color="#d29922"),
                PipelineStage(id="deploy_ready", label="Deploy Ready", color="#f0883e"),
                PipelineStage(id="done", label="Done", color="#3fb950"),
                PipelineStage(id="blocked", label="Blocked", color="#f85149"),
            ],
            agents=[
                AgentDefinition(
                    id="scrum_master", name="Scrum Master", icon="SM",
                    role="Backlog refinement & prioritization",
                    input_stage="backlog", output_stage="spec_ready",
                    artifact_type="specification",
                    system_prompt="You are a Scrum Master. Manage the backlog, prioritize tasks, facilitate standups, and ensure the team is unblocked.",
                ),
                AgentDefinition(
                    id="tech_lead", name="Tech Lead", icon="TL",
                    role="Leads specification & design",
                    input_stage="spec_ready", output_stage="arch_ready",
                    artifact_type="specification",
                    system_prompt="You are a Technical Lead. Write detailed, implementable technical specs with acceptance criteria and edge cases.",
                    team=[
                        AgentDefinition(
                            id="senior_dev_1", name="Senior Dev Alpha", icon="S1",
                            role="Backend specialist",
                            system_prompt="You are a Senior Backend Engineer. Focus on API design and data modeling.",
                        ),
                        AgentDefinition(
                            id="senior_dev_2", name="Senior Dev Beta", icon="S2",
                            role="Frontend specialist",
                            system_prompt="You are a Senior Frontend Engineer. Focus on UI components and state management.",
                        ),
                    ],
                    team_mode="parallel",
                ),
                AgentDefinition(
                    id="architect", name="Architect", icon="AR",
                    role="System architecture design",
                    input_stage="arch_ready", output_stage="code_ready",
                    artifact_type="architecture",
                    system_prompt="You are a Software Architect. Design system architecture with component boundaries, data models, API contracts.",
                ),
                AgentDefinition(
                    id="coder", name="Coder", icon="CD",
                    role="Implementation",
                    input_stage="code_ready", output_stage="test_ready",
                    artifact_type="source_code",
                    system_prompt="You are a Senior Software Engineer. Write clean, production-ready code with error handling and logging.",
                ),
                AgentDefinition(
                    id="qa", name="QA Lead", icon="QL",
                    role="Leads testing & quality",
                    input_stage="test_ready", output_stage="deploy_ready",
                    artifact_type="test_results",
                    system_prompt="You are a QA Lead. Write comprehensive tests and report bugs clearly with reproduction steps.",
                    team=[
                        AgentDefinition(
                            id="tester_1", name="Tester Alpha", icon="T1",
                            role="Integration & E2E testing",
                            system_prompt="You are a Test Engineer. Focus on integration and end-to-end testing.",
                        ),
                    ],
                    team_mode="review",
                ),
                AgentDefinition(
                    id="devops", name="DevOps", icon="DO",
                    role="CI/CD & deployment",
                    input_stage="deploy_ready", output_stage="done",
                    artifact_type="deploy_config",
                    system_prompt="You are a DevOps Engineer. Handle CI/CD, Docker configs, infrastructure as code, and deployment strategies.",
                ),
            ],
            task_fields=[
                TaskField(key="title", label="Title", type="text", required=True),
                TaskField(key="description", label="Description", type="textarea"),
                TaskField(key="priority", label="Priority", type="number", default="5"),
                TaskField(key="assignee", label="Assignee", type="text"),
                TaskField(key="story_points", label="Story Points", type="number"),
            ],
        )

    @classmethod
    def minimal(cls) -> TeamConfig:
        """Minimal 3-stage pipeline with 2 agents (simple demo)."""
        return cls(
            name="Minimal Team",
            description="Simple build-test-deploy pipeline",
            pipeline=[
                PipelineStage(id="backlog", label="Backlog", color="#8b949e"),
                PipelineStage(id="building", label="Building", color="#3fb950"),
                PipelineStage(id="testing", label="Testing", color="#d29922"),
                PipelineStage(id="done", label="Done", color="#3fb950"),
            ],
            agents=[
                AgentDefinition(
                    id="coder", name="Developer", icon="DV",
                    role="Builds features",
                    input_stage="backlog", output_stage="testing",
                    artifact_type="source_code",
                    system_prompt="You are a developer. Implement features from the backlog.",
                ),
                AgentDefinition(
                    id="qa", name="Tester", icon="QA",
                    role="Validates work",
                    input_stage="testing", output_stage="done",
                    artifact_type="test_results",
                    system_prompt="You are a tester. Validate implementations against requirements.",
                ),
            ],
            task_fields=[
                TaskField(key="title", label="Title", type="text", required=True),
                TaskField(key="description", label="Description", type="textarea"),
                TaskField(key="priority", label="Priority", type="number", default="3"),
            ],
        )

    @classmethod
    def load(cls, path: Path | str | None = None) -> TeamConfig:
        """Load config from a JSON file or return default."""
        search_paths = [
            Path(path) if path else None,
            Path("agile-team.json"),
            Path(".agile-team/config.json"),
            Path(".agile-team/team.json"),
        ]
        for p in search_paths:
            if p and p.exists():
                return cls(**json.loads(p.read_text()))
        return cls.default()

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2, exclude_none=True))
