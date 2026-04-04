from enum import Enum


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
