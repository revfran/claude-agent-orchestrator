import json

from orchestrator.core.agent_base import BaseAgent
from orchestrator.models.messages import Message


class DeveloperAgent(BaseAgent):
    """Implements solution code and addresses QA risk findings."""

    def __init__(self, config, claude_client):
        super().__init__(config, claude_client)
        self._revision_count = 0

    async def process(self, message: Message) -> dict | None:
        if message.msg_type == "revision_request":
            return await self._handle_revision(message)
        return await self._handle_initial(message)

    async def _handle_initial(self, message: Message) -> dict:
        self._revision_count = 0
        architecture = message.payload.get("architecture", "")
        query = message.payload.get("query", "")
        requirements = message.payload.get("requirements", "")

        prompt = (
            f"Implement a solution based on the following architecture:\n\n"
            f"Query: {query}\n"
            f"Requirements: {requirements}\n"
            f"Architecture:\n{architecture}\n\n"
            f"Provide:\n"
            f"1. Complete implementation code\n"
            f"2. Implementation notes explaining key decisions\n"
            f"3. Any assumptions made\n"
            f"4. Documentation updates: list any project documentation "
            f"(README, ARCHITECTURE.md, CLAUDE.md, docstrings, inline comments) "
            f"that should be created or updated to reflect these changes. "
            f"For each, state the file, what section to update, and the new content."
        )

        result = await self.call_claude(prompt)

        return {
            "code": result,
            "implementation_notes": result,
            "doc_updates": result,
            "query": query,
            "architecture": architecture,
            "review_type": "code",
            "revision_count": 0,
        }

    async def _handle_revision(self, message: Message) -> dict:
        self._revision_count += 1
        if self.monitor:
            self.monitor.emit(
                "revision_started",
                agent=self.agent_id,
                revision_number=self._revision_count,
            )
        code_risks = message.payload.get("code_risks", "")
        test_cases = message.payload.get("test_cases", [])
        original_code = message.payload.get("code", "")
        query = message.payload.get("query", "")
        architecture = message.payload.get("architecture", "")

        prompt = (
            f"Revise the code to address the following QA findings:\n\n"
            f"Original Code:\n{original_code}\n\n"
            f"Risk Assessment:\n{code_risks}\n\n"
            f"Test Cases to Pass:\n{json.dumps(test_cases) if isinstance(test_cases, list) else test_cases}\n\n"
            f"Fix all HIGH and MEDIUM severity issues. Explain what changes you made.\n"
            f"Also update the documentation section: list any docs that need updating "
            f"to reflect the revised code."
        )

        result = await self.call_claude(prompt)

        if self.monitor:
            self.monitor.record_revision(self.agent_id)

        return {
            "code": result,
            "implementation_notes": result,
            "doc_updates": result,
            "query": query,
            "architecture": architecture,
            "review_type": "code",
            "revision_count": self._revision_count,
            "addressed_risks": code_risks,
        }
