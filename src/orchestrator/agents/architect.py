from orchestrator.core.agent_base import BaseAgent
from orchestrator.models.messages import Message


class ArchitectAgent(BaseAgent):
    """Designs solution architecture and addresses QA risk findings."""

    def __init__(self, config, claude_client):
        super().__init__(config, claude_client)
        self._revision_count = 0

    async def process(self, message: Message) -> dict | None:
        if message.msg_type == "revision_request":
            return await self._handle_revision(message)
        return await self._handle_initial(message)

    async def _handle_initial(self, message: Message) -> dict:
        self._revision_count = 0
        requirements = message.payload.get("requirements", "")
        context = message.payload.get("context", "")
        query = message.payload.get("query", "")

        prompt = (
            f"Design a solution architecture for the following:\n\n"
            f"Query: {query}\n"
            f"Requirements: {requirements}\n"
            f"Context: {context}\n\n"
            f"Provide:\n"
            f"1. High-level architecture design\n"
            f"2. Key design decisions and their rationale\n"
            f"3. Component breakdown\n"
            f"4. Data flow description"
        )

        result = await self.call_claude(prompt)

        return {
            "architecture": result,
            "design_decisions": result,
            "query": query,
            "requirements": requirements,
            "review_type": "architecture",
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
        risk_assessment = message.payload.get("risk_assessment", "")
        original_architecture = message.payload.get("architecture", "")
        query = message.payload.get("query", "")
        requirements = message.payload.get("requirements", "")

        prompt = (
            f"Revise the architecture to address the following risk assessment:\n\n"
            f"Original Architecture:\n{original_architecture}\n\n"
            f"Risk Assessment:\n{risk_assessment}\n\n"
            f"Address all HIGH and MEDIUM severity risks. Explain what changes you made and why."
        )

        result = await self.call_claude(prompt)

        if self.monitor:
            self.monitor.record_revision(self.agent_id)

        return {
            "architecture": result,
            "design_decisions": result,
            "query": query,
            "requirements": requirements,
            "review_type": "architecture",
            "revision_count": self._revision_count,
            "addressed_risks": risk_assessment,
        }
