import json

from orchestrator.core.agent_base import BaseAgent
from orchestrator.models.messages import Message


class QAAgent(BaseAgent):
    """Reviews architecture and code for risks; produces risk assessments and tests."""

    async def process(self, message: Message) -> dict | None:
        review_type = message.payload.get("review_type", "architecture")

        if review_type == "architecture":
            return await self._review_architecture(message)
        elif review_type == "code":
            return await self._review_code(message)
        return None

    async def _review_architecture(self, message: Message) -> dict:
        architecture = message.payload.get("architecture", "")
        query = message.payload.get("query", "")
        requirements = message.payload.get("requirements", "")
        revision_count = message.payload.get("revision_count", 0)
        max_revisions = self.config.max_revisions

        prompt = (
            f"Review this architecture for risks and potential issues:\n\n"
            f"Architecture:\n{architecture}\n\n"
            f"Analyze and provide a JSON response with this exact structure:\n"
            f'{{"risk_items": [{{"description": "...", "severity": "HIGH|MEDIUM|LOW", '
            f'"recommendation": "..."}}], '
            f'"has_blocking_risks": true/false, '
            f'"summary": "..."}}\n\n'
            f"Consider: scalability, security, coupling, single points of failure, "
            f"maintainability, and edge cases."
        )

        result = await self.call_claude(prompt)
        risk_data = self._parse_risk_response(result)
        has_blocking = risk_data.get("has_blocking_risks", False)
        needs_revision = has_blocking and revision_count < max_revisions

        if needs_revision:
            # Send back to architect for revision
            await self._publish_to(
                "arch_revision",
                {
                    "risk_assessment": result,
                    "architecture": architecture,
                    "query": query,
                    "requirements": requirements,
                    "revision_count": revision_count,
                },
                msg_type="revision_request",
            )
            return None  # Don't forward to next stage

        # Approved — forward to developer
        risk_log = {
            "architecture_risks": result,
            "revisions_made": revision_count,
            "verdict": "approved",
        }

        if self.data_handler:
            await self.data_handler.write("risk_log", [risk_log])

        await self._publish_to(
            "dev_input",
            {
                "architecture": architecture,
                "query": query,
                "requirements": requirements,
                "risk_log": risk_log,
            },
            msg_type="data",
        )
        return None

    async def _review_code(self, message: Message) -> dict:
        code = message.payload.get("code", "")
        query = message.payload.get("query", "")
        architecture = message.payload.get("architecture", "")
        revision_count = message.payload.get("revision_count", 0)
        max_revisions = self.config.max_revisions

        prompt = (
            f"Review this code implementation for risks and generate test cases:\n\n"
            f"Code:\n{code}\n\n"
            f"Provide a JSON response with this exact structure:\n"
            f'{{"risk_items": [{{"description": "...", "severity": "HIGH|MEDIUM|LOW", '
            f'"recommendation": "..."}}], '
            f'"has_blocking_risks": true/false, '
            f'"test_cases": ["test case description 1", "test case description 2"], '
            f'"summary": "..."}}\n\n'
            f"Consider: bugs, security vulnerabilities, race conditions, "
            f"missing error handling, and edge cases."
        )

        result = await self.call_claude(prompt)
        risk_data = self._parse_risk_response(result)
        has_blocking = risk_data.get("has_blocking_risks", False)
        test_cases = risk_data.get("test_cases", [])
        needs_revision = has_blocking and revision_count < max_revisions

        if needs_revision:
            await self._publish_to(
                "code_revision",
                {
                    "code_risks": result,
                    "test_cases": test_cases,
                    "code": code,
                    "query": query,
                    "architecture": architecture,
                    "revision_count": revision_count,
                },
                msg_type="revision_request",
            )
            return None

        # Approved — forward to reporting
        code_risk_log = {
            "code_risks": result,
            "test_cases": test_cases,
            "revisions_made": revision_count,
            "verdict": "approved",
        }

        if self.data_handler:
            existing_log = await self.data_handler.read("risk_log", [])
            existing_log.append(code_risk_log)
            await self.data_handler.write("risk_log", existing_log)

        await self._publish_to(
            "report_input",
            {
                "architecture": architecture,
                "code": code,
                "test_cases": test_cases,
                "query": query,
                "risk_log": code_risk_log,
            },
            msg_type="data",
        )
        return None

    def _parse_risk_response(self, response: str) -> dict:
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {"risk_items": [], "has_blocking_risks": False, "summary": response}
