"""Skuper Intelligence - Agentic Inventory Rebalancing"""

from .agent_emergency import (
                              EMERGENCY_RESOLVER_SYSTEM_PROMPT,
                              create_emergency_agent,
                              create_emergency_workflow,
)
from .agent_proactive import (
                              PROACTIVE_RESOLVER_SYSTEM_PROMPT,
                              create_proactive_agent,
                              create_proactive_resolver_agent,
                              create_proactive_workflow,
)
from .config import CURRENT_DATE, DB_CONFIG, LLM_CONFIG, OPENAI_API_KEY
from .models import (
                              EmergencyAgentState,
                              EmergencyStockoutState,
                              ProactiveAgentState,
                              ProactiveRebalanceState,
                              ProactiveRecommendation,
                              Recommendation,
                              SKUProblem,
                              StockoutRecord,
                              SurplusLocation,
                              TransportationLane,
)
from .orchestrator_emergency import StockoutOrchestrator
from .orchestrator_proactive import ProactiveOrchestrator
from .tools import ALL_TOOLS

__all__ = [
    "DB_CONFIG",
    "OPENAI_API_KEY",
    "LLM_CONFIG",
    "CURRENT_DATE",
    "StockoutRecord",
    "SurplusLocation",
    "TransportationLane",
    "Recommendation",
    "EmergencyStockoutState",  # Legacy Pydantic model
    "EmergencyAgentState",  # New TypedDict state
    "ProactiveRebalanceState",  # Legacy Pydantic model
    "ProactiveAgentState",      # New TypedDict state
    "ProactiveRecommendation",
    "SKUProblem",
    "ALL_TOOLS",
    "EMERGENCY_RESOLVER_SYSTEM_PROMPT",
    "create_emergency_agent",     # New create_agent approach
    "create_emergency_workflow",  # Legacy wrapper
    "PROACTIVE_RESOLVER_SYSTEM_PROMPT",
    "create_proactive_agent",     # New create_agent approach
    "create_proactive_resolver_agent",
    "create_proactive_workflow",  # Legacy wrapper
    "StockoutOrchestrator",
    "ProactiveOrchestrator",
]
