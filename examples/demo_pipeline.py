"""
Demo: Run the full agent pipeline with QA feedback loops.

Usage:
    ANTHROPIC_API_KEY=sk-... python -m examples.demo_pipeline
"""

import asyncio

from orchestrator.agents.acquisition import DataAcquisitionAgent
from orchestrator.agents.architect import ArchitectAgent
from orchestrator.agents.developer import DeveloperAgent
from orchestrator.agents.qa import QAAgent
from orchestrator.agents.reporting import ReportingAgent
from orchestrator.models.config import AgentConfig, OrchestratorConfig
from orchestrator.models.messages import Message
from orchestrator.orchestrator import Orchestrator
from orchestrator.pipeline import Pipeline


async def main():
    config = OrchestratorConfig(log_level="INFO")
    orch = Orchestrator(config)
    client = orch.agent_manager.claude_client

    # Create agents with role-specific system prompts
    acquisition = DataAcquisitionAgent(
        AgentConfig(
            agent_id="acquirer",
            agent_type="acquisition",
            system_prompt="You are a data acquisition specialist. Gather and organize relevant requirements and context.",
        ),
        client,
    )

    architect = ArchitectAgent(
        AgentConfig(
            agent_id="architect",
            agent_type="architect",
            system_prompt="You are a software architect. Design clean, scalable architectures.",
        ),
        client,
    )

    qa = QAAgent(
        AgentConfig(
            agent_id="qa",
            agent_type="qa",
            max_revisions=2,
            system_prompt="You are a QA engineer. Identify risks, vulnerabilities, and generate test cases.",
        ),
        client,
    )

    developer = DeveloperAgent(
        AgentConfig(
            agent_id="developer",
            agent_type="developer",
            system_prompt="You are a senior software developer. Write clean, secure, well-tested code.",
        ),
        client,
    )

    reporting = ReportingAgent(
        AgentConfig(
            agent_id="reporter",
            agent_type="reporting",
            system_prompt="You are a technical writer. Generate clear, structured reports.",
        ),
        client,
    )

    # Build the pipeline with QA feedback loops
    pipe = Pipeline(orch)
    pipe.set_acquisition(acquisition)
    pipe.set_architect(architect)
    pipe.set_qa(qa)
    pipe.set_developer(developer)
    pipe.set_reporting(reporting)
    input_channel = pipe.build()

    # Subscribe to output before starting
    output_queue: asyncio.Queue = asyncio.Queue()
    orch.agent_manager.message_bus.subscribe("pipeline_output", output_queue)

    # Start the pipeline
    await orch.run()

    # Inject a query
    seed = Message(
        source="user",
        target=input_channel,
        payload={
            "query": "Design and implement a REST API for a task management system with user authentication",
            "sources": ["best practices", "OWASP guidelines", "REST API standards"],
        },
    )
    await orch.agent_manager.message_bus.publish(input_channel, seed)

    # Wait for the final report
    print("\nWaiting for pipeline to complete...\n")
    try:
        result = await asyncio.wait_for(output_queue.get(), timeout=300)
        print("=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        print(result.payload.get("report", "No report generated."))
    except asyncio.TimeoutError:
        print("Pipeline timed out after 5 minutes.")

    # Print metrics
    print("\n" + "=" * 60)
    print("METRICS")
    print("=" * 60)
    for agent_id, metrics in orch.monitor.summary().items():
        print(f"  {agent_id}: {metrics}")

    await orch.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
