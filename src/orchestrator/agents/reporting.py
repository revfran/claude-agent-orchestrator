from orchestrator.core.agent_base import BaseAgent
from orchestrator.models.messages import Message


class ReportingAgent(BaseAgent):
    """Generates final structured report with architecture, code, tests, and risk log."""

    async def process(self, message: Message) -> dict | None:
        architecture = message.payload.get("architecture", "")
        code = message.payload.get("code", "")
        test_cases = message.payload.get("test_cases", [])
        query = message.payload.get("query", "")
        risk_log = message.payload.get("risk_log", {})

        # Retrieve full risk log from data handler if available
        full_risk_log = None
        if self.data_handler:
            full_risk_log = await self.data_handler.read("risk_log", [])

        prompt = (
            f"Generate a comprehensive structured report in markdown format.\n\n"
            f"Query: {query}\n\n"
            f"Architecture:\n{architecture}\n\n"
            f"Implementation:\n{code}\n\n"
            f"Test Cases:\n{test_cases}\n\n"
            f"Risk Log:\n{full_risk_log or risk_log}\n\n"
            f"The report should include:\n"
            f"1. Executive Summary\n"
            f"2. Architecture Overview\n"
            f"3. Implementation Details\n"
            f"4. Test Coverage\n"
            f"5. Risk Assessment Log (all risks found and how they were resolved)\n"
            f"6. Recommendations"
        )

        result = await self.call_claude(prompt)

        if self.data_handler:
            await self.data_handler.write(f"report:{query}", result)

        return {"report": result, "query": query}
