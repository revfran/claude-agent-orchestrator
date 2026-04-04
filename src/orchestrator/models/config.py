from pydantic import BaseModel


class AgentConfig(BaseModel):
    agent_id: str
    agent_type: str
    claude_model: str = "claude-sonnet-4-20250514"
    system_prompt: str = ""
    input_channels: list[str] = []
    output_channels: list[str] = []
    max_revisions: int = 2


class OrchestratorConfig(BaseModel):
    agents: list[AgentConfig] = []
    anthropic_api_key: str | None = None
    log_level: str = "INFO"
