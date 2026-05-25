from __future__ import annotations

from agile_team.agents.base import BaseAgent
from agile_team.shared.models import (
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskStatus,
)


class ScrumMasterAgent(BaseAgent):
    role = AgentRole.SCRUM_MASTER
    input_status = TaskStatus.BACKLOG
    output_status = TaskStatus.SPEC_READY
    artifact_type = ArtifactType.SPECIFICATION

    async def process(self, task: Task) -> Artifact:
        prompt = f"""Analyze this task and produce a structured breakdown:

TASK TITLE: {task.title}
TASK DESCRIPTION: {task.description}
PRIORITY: {task.priority}

Provide the following in your response:
1. **Refined Title**: A clear, concise task title
2. **User Story**: As a [user], I want [goal], so that [reason]
3. **Definition of Done**: Concrete criteria that must be met
4. **Estimated Complexity**: Low/Medium/High with brief justification
5. **Dependencies**: Any blockers or prerequisites
6. **Risk Assessment**: Potential risks and mitigation
"""
        content = await self.generate(prompt)
        return Artifact(
            task_id=task.id,
            artifact_type=self.artifact_type,
            content=content.strip(),
            created_by=self.role.value,
        )


class TechLeadAgent(BaseAgent):
    role = AgentRole.TECH_LEAD
    input_status = TaskStatus.SPEC_READY
    output_status = TaskStatus.ARCH_READY
    artifact_type = ArtifactType.SPECIFICATION

    async def process(self, task: Task) -> Artifact:
        scrum_notes = self._read_artifact(task, ArtifactType.SPECIFICATION) or ""
        feedback = "\n".join(task.feedback_notes) if task.feedback_notes else "None"

        prompt = f"""Write a detailed technical specification for this task:

TASK: {task.title}
DESCRIPTION: {task.description}
SCRUM NOTES: {scrum_notes}
PREVIOUS FEEDBACK: {feedback}

Your specification MUST include:
1. **Overview**: Summary of what needs to be built
2. **Functional Requirements**: Numbered list of specific features
3. **Non-Functional Requirements**: Performance, security, accessibility
4. **API/Interface Contracts**: Input/output schemas, endpoints if applicable
5. **Data Models**: Entities, fields, relationships
6. **Acceptance Criteria**: Testable conditions (Given/When/Then format)
7. **Edge Cases**: Boundary conditions and error scenarios
8. **Technical Constraints**: Language, framework, library restrictions

Be precise. Every requirement must be testable.
"""
        content = await self.generate(prompt)
        return Artifact(
            task_id=task.id,
            artifact_type=self.artifact_type,
            content=content.strip(),
            created_by=self.role.value,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state_path = self.workspace / "agents" / self.role.value / "state.json"


class ArchitectAgent(BaseAgent):
    role = AgentRole.ARCHITECT
    input_status = TaskStatus.ARCH_READY
    output_status = TaskStatus.CODE_READY
    artifact_type = ArtifactType.ARCHITECTURE

    async def process(self, task: Task) -> Artifact:
        spec = self._read_artifact(task, ArtifactType.SPECIFICATION) or ""
        feedback = "\n".join(task.feedback_notes) if task.feedback_notes else "None"

        prompt = f"""Design the system architecture for this task:

TASK: {task.title}
SPECIFICATION:
{spec}

PREVIOUS FEEDBACK: {feedback}

Your architecture design MUST include:
1. **System Overview**: High-level architecture diagram (ASCII art or Mermaid)
2. **Components**: List each component with its responsibility
3. **Interfaces**: How components communicate (REST, gRPC, events, etc.)
4. **Data Flow**: How data moves through the system
5. **Database Schema**: Tables/collections, key fields, relationships
6. **File Structure**: Recommended directory/file layout
7. **Technology Stack**: Specific libraries, versions, with justification
8. **Security Considerations**: Auth, data protection, threat model
9. **Scalability Notes**: Bottlenecks and scaling strategy

Output design that a developer can implement without ambiguity.
"""
        content = await self.generate(prompt)
        return Artifact(
            task_id=task.id,
            artifact_type=self.artifact_type,
            content=content.strip(),
            created_by=self.role.value,
        )


class CoderAgent(BaseAgent):
    role = AgentRole.CODER
    input_status = TaskStatus.CODE_READY
    output_status = TaskStatus.TEST_READY
    artifact_type = ArtifactType.SOURCE_CODE

    async def process(self, task: Task) -> Artifact:
        spec = self._read_artifact(task, ArtifactType.SPECIFICATION) or ""
        arch = self._read_artifact(task, ArtifactType.ARCHITECTURE) or ""
        feedback = "\n".join(task.feedback_notes) if task.feedback_notes else "None"

        prompt = f"""Implement the following task with production-ready code:

TASK: {task.title}

SPECIFICATION:
{spec}

ARCHITECTURE:
{arch}

PREVIOUS FEEDBACK: {feedback}

Output the COMPLETE implementation. For each file include:
```
// filename: path/to/file.ext
[full file contents]
```

Requirements:
- Use the exact technology choices from the architecture
- Include proper error handling and logging
- Add docstrings/comments for public APIs
- Follow the specified file structure
- Include import statements and dependencies
- Code must be complete and runnable
"""
        content = await self.generate(prompt)
        return Artifact(
            task_id=task.id,
            artifact_type=self.artifact_type,
            content=content.strip(),
            created_by=self.role.value,
        )


class QAAgent(BaseAgent):
    role = AgentRole.QA
    input_status = TaskStatus.TEST_READY
    output_status = TaskStatus.DEPLOY_READY
    artifact_type = ArtifactType.TEST_RESULTS

    async def process(self, task: Task) -> Artifact:
        spec = self._read_artifact(task, ArtifactType.SPECIFICATION) or ""
        code = self._read_artifact(task, ArtifactType.SOURCE_CODE) or ""

        prompt = f"""Review the implementation and produce test results:

TASK: {task.title}

SPECIFICATION (for acceptance criteria):
{spec}

SOURCE CODE:
{code}

Provide a comprehensive test report:
1. **Test Cases**: List all test cases with (Pass/Fail/Skip)
2. **Acceptance Criteria Verification**: Check each criterion from spec
3. **Edge Case Coverage**: Which edge cases were tested
4. **Bug Report**: Any issues found with severity (Critical/High/Medium/Low)
5. **Code Quality Notes**: Readability, maintainability, security
6. **Overall Verdict**: APPROVED or REJECTED
7. **If REJECTED**: Specific changes needed and why

If the code fails acceptance criteria, start your response with "REJECTED:" and explain why.
If all passes, start with "APPROVED:" and summarize.
"""
        content = await self.generate(prompt)
        return Artifact(
            task_id=task.id,
            artifact_type=self.artifact_type,
            content=content.strip(),
            created_by=self.role.value,
        )

    async def validate(self, artifact: Artifact) -> bool:
        if "REJECTED:" in artifact.content:
            return False
        return await super().validate(artifact)


class DevOpsAgent(BaseAgent):
    role = AgentRole.DEVOPS
    input_status = TaskStatus.DEPLOY_READY
    output_status = TaskStatus.DONE
    artifact_type = ArtifactType.DEPLOY_CONFIG

    async def process(self, task: Task) -> Artifact:
        arch = self._read_artifact(task, ArtifactType.ARCHITECTURE) or ""
        code = self._read_artifact(task, ArtifactType.SOURCE_CODE) or ""
        test_results = self._read_artifact(task, ArtifactType.TEST_RESULTS) or ""

        prompt = f"""Create deployment and CI/CD configuration:

TASK: {task.title}

ARCHITECTURE:
{arch}

SOURCE CODE:
{code}

TEST RESULTS:
{test_results}

Produce the following deployment artifacts:
1. **Dockerfile**: Multi-stage build if applicable
2. **docker-compose.yml**: If multiple services needed
3. **CI/CD Pipeline**: GitHub Actions or GitLab CI YAML
4. **Deployment Strategy**: Blue/green, rolling, canary recommendation
5. **Environment Config**: Required env vars, secrets management
6. **Monitoring/Logging**: Health check endpoints, log configuration
7. **Runbook**: Step-by-step deploy instructions
8. **Rollback Plan**: How to revert if deployment fails

Output each artifact with clear filenames using markdown code blocks.
"""
        content = await self.generate(prompt)
        return Artifact(
            task_id=task.id,
            artifact_type=self.artifact_type,
            content=content.strip(),
            created_by=self.role.value,
        )
