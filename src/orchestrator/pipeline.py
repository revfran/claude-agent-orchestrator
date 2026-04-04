from orchestrator.core.agent_base import BaseAgent


class Pipeline:
    """Builds the agent pipeline with QA feedback loops.

    Channel topology:
        pipeline_input → acquisition
        acquisition → arch_input → architect
        architect → arch_review → qa (architecture review)
        qa → arch_revision → architect (feedback loop)
        qa → dev_input → developer (approved)
        developer → code_review → qa (code review)
        qa → code_revision → developer (feedback loop)
        qa → report_input → reporting (approved)
        reporting → pipeline_output
    """

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self._acquisition: BaseAgent | None = None
        self._architect: BaseAgent | None = None
        self._qa: BaseAgent | None = None
        self._developer: BaseAgent | None = None
        self._reporting: BaseAgent | None = None

    def set_acquisition(self, agent: BaseAgent) -> "Pipeline":
        self._acquisition = agent
        return self

    def set_architect(self, agent: BaseAgent) -> "Pipeline":
        self._architect = agent
        return self

    def set_qa(self, agent: BaseAgent) -> "Pipeline":
        self._qa = agent
        return self

    def set_developer(self, agent: BaseAgent) -> "Pipeline":
        self._developer = agent
        return self

    def set_reporting(self, agent: BaseAgent) -> "Pipeline":
        self._reporting = agent
        return self

    def build(self) -> str:
        """Wire all channels and register agents. Returns the input channel name."""
        if not all(
            [
                self._acquisition,
                self._architect,
                self._qa,
                self._developer,
                self._reporting,
            ]
        ):
            raise ValueError("All 5 agents must be set before building the pipeline")

        # Acquisition: reads from pipeline_input, writes to arch_input
        self._acquisition.config.input_channels = ["pipeline_input"]
        self._acquisition.config.output_channels = ["arch_input"]

        # Architect: reads from arch_input + arch_revision, writes to arch_review
        self._architect.config.input_channels = ["arch_input", "arch_revision"]
        self._architect.config.output_channels = ["arch_review"]

        # QA: reads from arch_review + code_review
        # QA publishes directly via _publish_to (arch_revision, dev_input, code_revision, report_input)
        self._qa.config.input_channels = ["arch_review", "code_review"]
        self._qa.config.output_channels = []  # QA routes manually

        # Developer: reads from dev_input + code_revision, writes to code_review
        self._developer.config.input_channels = ["dev_input", "code_revision"]
        self._developer.config.output_channels = ["code_review"]

        # Reporting: reads from report_input, writes to pipeline_output
        self._reporting.config.input_channels = ["report_input"]
        self._reporting.config.output_channels = ["pipeline_output"]

        # Register all agents
        for agent in [
            self._acquisition,
            self._architect,
            self._qa,
            self._developer,
            self._reporting,
        ]:
            self.orchestrator.add_agent(agent)

        return "pipeline_input"
