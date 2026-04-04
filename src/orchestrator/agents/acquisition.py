from orchestrator.core.agent_base import BaseAgent
from orchestrator.models.messages import Message


class DataAcquisitionAgent(BaseAgent):
    """Gathers requirements, context, and data from the input query."""

    async def process(self, message: Message) -> dict | None:
        query = message.payload.get("query", "")
        sources = message.payload.get("sources", [])

        prompt = (
            f"You are given a task query and optional data sources. "
            f"Gather and organize the requirements, context, and relevant information.\n\n"
            f"Query: {query}\n"
            f"Sources: {', '.join(sources) if sources else 'none specified'}\n\n"
            f"Provide:\n"
            f"1. Clear requirements extracted from the query\n"
            f"2. Relevant context and background information\n"
            f"3. Key considerations for the solution"
        )

        result = await self.call_claude(prompt)

        return {
            "query": query,
            "requirements": result,
            "context": f"Sources consulted: {sources}",
        }
