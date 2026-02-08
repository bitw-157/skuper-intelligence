"""Data models for Emergency Stockout Resolver Agent"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import NotRequired


class StockoutRecord(BaseModel):
    """Stockout record from projection_calcs_4w table."""

    location_id: str
    sku_id: str
    week_start_date: str
    end_inv_qty: int
    safety_stock_qty: int
    projected_stockout_flag: int
    demand_fcst_qty: int
    product_family: str
    target_service_level: float
    temp_class: str
    unit_cost_usd: float
    location_type: str
    priority_tier: int
    handling_class: str


class SurplusLocation(BaseModel):
    """Surplus inventory details."""

    location_id: str
    total_available_qty: int
    safety_stock_qty: int
    excess_qty: int
    min_days_to_expiry: int
    has_near_expiry: bool
    handling_class: str


class TransportationLane(BaseModel):
    """Transportation route from transportation_lanes table."""

    lane_id: str
    from_location_id: str
    to_location_id: str
    mode: str  # 'Air' or 'Ground'
    standard_lead_time_days: int
    max_lead_time_days: int
    min_transfer_qty: int
    transfer_cost_per_unit_usd: float
    co2_kg_per_unit: float
    allowed_flag: int


class TransferImpactSimulation(BaseModel):
    """Transfer impact simulation results."""

    source: Dict[str, Any]
    destination: Dict[str, Any]
    transfer_qty: int
    lead_time_days: int


class Recommendation(BaseModel):
    """Transfer recommendation with action details and rationale."""

    recommendation_id: str
    recommendation_type: str  # 'Emergency Transfer'
    priority: str  # 'CRITICAL', 'HIGH', 'STANDARD'
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW'

    # Action details
    from_location_id: str
    to_location_id: str
    sku_id: str
    recommended_qty: int
    transportation_lane: str
    mode: str
    estimated_cost: float
    lead_time_days: int
    arrival_date: str

    # Rationale
    rationale: Dict[str, Any]
    validation_checks: Dict[str, str]
    alternatives_considered: List[Dict[str, Any]]
    risks: List[str]
    backup_plan: Optional[List[str]] = None

    # Metadata
    created_on: str
    agent_version: str


# TypedDict for agent state (required by create_agent)
class EmergencyState(TypedDict, total=False):
    """State schema for Emergency Stockout Resolver Agent (TypedDict for create_agent)"""

    # Required fields from AgentState
    messages: List[Any]  # Required by LangChain agents

    # Input from Orchestrator
    sku_id: str
    product_details: Dict[str, Any]
    stockout_locations: List[StockoutRecord]
    available_inventory: Dict[str, int]  # {location_id: excess_qty}

    # Problem Assessment
    current_focus: NotRequired[Optional[StockoutRecord]]
    severity_score: NotRequired[float]
    criticality_level: NotRequired[str]  # 'CRITICAL', 'HIGH', 'STANDARD'
    urgency_level: NotRequired[str]  # 'EMERGENCY', 'URGENT', 'STANDARD'

    # Discovery Phase
    surplus_candidates: NotRequired[List[SurplusLocation]]
    selected_source: NotRequired[Optional[SurplusLocation]]
    transportation_options: NotRequired[List[TransportationLane]]
    selected_route: NotRequired[Optional[TransportationLane]]

    # Calculation Phase
    recommended_transfer_qty: NotRequired[int]
    transfer_cost: NotRequired[float]

    # Validation Phase
    source_impact: NotRequired[Optional[TransferImpactSimulation]]
    destination_impact: NotRequired[Optional[TransferImpactSimulation]]
    constraint_violations: NotRequired[List[str]]
    cold_chain_compliant: NotRequired[bool]

    # Output Phase
    final_recommendations: NotRequired[List[Recommendation]]
    alternatives_considered: NotRequired[List[Dict[str, Any]]]
    confidence_level: NotRequired[str]

    # Control Flow & Auditing
    reasoning_trace: NotRequired[List[Any]]
    tools_called: NotRequired[List[Dict[str, Any]]]
    needs_escalation: NotRequired[bool]
    escalation_reason: NotRequired[Optional[str]]
    current_step: NotRequired[str]
    iteration_count: NotRequired[int]

    # Structured output (if using response_format)
    structured_response: NotRequired[Optional["AgentOutput"]]


# Legacy Pydantic model for backward compatibility
class EmergencyStockoutState(BaseModel):
    """Complete state for Emergency Stockout Resolver Agent (Pydantic - Legacy)"""

    # Input from Orchestrator
    sku_id: str
    product_details: Dict[str, Any]
    stockout_locations: List[StockoutRecord]
    available_inventory: Dict[str, int]  # {location_id: excess_qty}

    # Problem Assessment
    current_focus: Optional[StockoutRecord] = None
    severity_score: float = 0.0  # 0-100
    criticality_level: str = "STANDARD"  # 'CRITICAL', 'HIGH', 'STANDARD'
    urgency_level: str = "STANDARD"  # 'EMERGENCY', 'URGENT', 'STANDARD'

    # Discovery Phase
    surplus_candidates: List[SurplusLocation] = Field(default_factory=list)
    selected_source: Optional[SurplusLocation] = None
    transportation_options: List[TransportationLane] = Field(default_factory=list)
    selected_route: Optional[TransportationLane] = None

    # Calculation Phase
    recommended_transfer_qty: int = 0
    transfer_cost: float = 0.0

    # Validation Phase
    source_impact: Optional[TransferImpactSimulation] = None
    destination_impact: Optional[TransferImpactSimulation] = None
    constraint_violations: List[str] = Field(default_factory=list)
    cold_chain_compliant: bool = True

    # Output Phase
    final_recommendations: List[Recommendation] = Field(default_factory=list)
    alternatives_considered: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_level: str = "MEDIUM"

    # Control Flow & Auditing
    reasoning_trace: List[Any] = Field(
        default_factory=list
    )  # Step-by-step reasoning log
    tools_called: List[Dict[str, Any]] = Field(
        default_factory=list
    )  # Tool call history
    needs_escalation: bool = False
    escalation_reason: Optional[str] = None
    current_step: str = "start"  # Track which node we're in
    iteration_count: int = 0  # Prevent infinite loops

    # LLM Messages
    messages: List[Any] = Field(default_factory=list)  # Conversation history with LLM

    class Config:
        arbitrary_types_allowed = True  # Allow LangChain message types


class SKUProblem(BaseModel):
    """Input format for a single SKU problem from Orchestrator"""

    sku_id: str
    priority_score: float
    stockouts: List[StockoutRecord]
    product_info: Dict[str, Any]


# MVP Structured Outputs for Agent
class AgentTransferRecommendation(BaseModel):
    """Structured transfer recommendation from agent"""

    from_location: str
    to_location: str
    quantity: int
    reasoning: str
    estimated_cost: float


class LocationResolutionResult(BaseModel):
    """Per-location resolution result"""

    location_id: str
    shortage_qty: int  # Negative inventory amount
    status: str  # 'RESOLVED', 'UNRESOLVED'
    transfer: Optional[AgentTransferRecommendation] = None
    reason_unresolved: Optional[str] = None  # If status='UNRESOLVED'


class AgentPriorityAnalysis(BaseModel):
    """Priority analysis when no surplus available"""

    summary: str
    highest_priority_location: str
    urgency_level: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    recommended_action: str


class AgentOutput(BaseModel):
    """Final structured output from agent (supports per-location granularity)"""

    output_type: str  # 'SOLUTION', 'ESCALATION'
    location_results: List[LocationResolutionResult] = Field(default_factory=list)
    summary: str = ""  # Human-readable summary (e.g., "Resolved 2/3 locations")

    # Legacy fields for backward compatibility
    transfers: List[AgentTransferRecommendation] = Field(default_factory=list)
    priority_analysis: Optional[AgentPriorityAnalysis] = None


# ============================================================================
# MODELS FOR TYPE B: PROACTIVE REBALANCER
# ============================================================================


class ProactiveRebalanceState(BaseModel):
    """State for Proactive Rebalancer agent (Type B)"""

    # Input context
    sku_id: str
    projected_stockout_locations: List[Dict[str, Any]]  # Week 2-4 stockouts
    current_inventory_snapshot: Dict[str, int]  # {location_id: available_qty}
    incoming_supply_orders: List[Dict[str, Any]]  # Supply orders for this SKU
    product_details: Dict[str, Any]

    # Agent workflow state
    messages: List[Any] = Field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 3

    # Discovery phase
    reroute_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    selected_reroute: Optional[Dict[str, Any]] = None
    transfer_candidates: List[Dict[str, Any]] = Field(default_factory=list)

    # Decision phase
    recommendation_type: Optional[str] = (
        None  # 'SUPPLY_REROUTE', 'PREEMPTIVE_TRANSFER', 'ESCALATION'
    )
    confidence_level: str = "MEDIUM"  # 'HIGH', 'MEDIUM', 'LOW'

    # Output
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    escalations: List[Dict[str, Any]] = Field(default_factory=list)
    processing_complete: bool = False

    # Auditing
    reasoning_trace: List[str] = Field(default_factory=list)
    tools_called: List[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


class ProactiveRecommendation(BaseModel):
    """Proactive rebalancing recommendation (Type B output)"""

    recommendation_id: str
    recommendation_type: str  # 'SUPPLY_REROUTE', 'PREEMPTIVE_TRANSFER', 'ESCALATION'
    created_at: str

    # Target context
    sku_id: str
    target_location_id: str
    projected_stockout_week: str
    current_severity: int  # Magnitude of projected shortage

    # Supply reroute specific fields
    supply_order_id: Optional[str] = None
    original_destination: Optional[str] = None
    new_destination: Optional[str] = None
    reroute_cost_delta: Optional[float] = None
    eta_change_days: Optional[int] = None

    # Preemptive transfer specific fields
    source_location_id: Optional[str] = None
    transfer_quantity: Optional[int] = None
    recommended_transport_mode: Optional[str] = None
    transfer_cost: Optional[float] = None

    # Assessment & rationale
    reasoning: str
    confidence_level: str  # 'HIGH', 'MEDIUM', 'LOW'
    risk_assessment: str
    alternative_options_considered: List[str] = Field(default_factory=list)

    # Validation flags
    maintains_source_safety_stock: bool = True
    arrives_before_stockout: bool = True
    cost_vs_emergency_ratio: Optional[float] = None  # Should be < 0.70

    # Metadata
    forecast_confidence: Optional[float] = None  # From demand_forecast_4w
    agent_version: str = "1.0-proactive"


class AgentSupplyReroute(BaseModel):
    """Structured supply reroute recommendation from agent"""

    supply_order_id: str
    original_destination: str
    new_destination: str
    reasoning: str
    cost_delta: float
    confidence_level: str


class AgentPreemptiveTransfer(BaseModel):
    """Structured preemptive transfer recommendation from agent"""

    from_location: str
    to_location: str
    quantity: int
    transport_mode: str
    reasoning: str
    estimated_cost: float
    confidence_level: str


class AgentEscalation(BaseModel):
    """Escalation when no proactive action is viable"""

    summary: str
    highest_priority_location: str
    projected_stockout_week: str
    recommended_action: str
    reasons_no_solution: List[str]


class ProactiveLocationResult(BaseModel):
    """Per-location resolution result for proactive agent"""

    location_id: str
    projected_shortage_qty: int  # Negative projected inventory amount
    stockout_week: str  # Week of projected stockout (e.g., "2026-01-19")
    status: str  # 'RESOLVED', 'UNRESOLVED'
    supply_reroute: Optional[AgentSupplyReroute] = None
    preemptive_transfer: Optional[AgentPreemptiveTransfer] = None
    reason_unresolved: Optional[str] = None  # If status='UNRESOLVED'


class ProactiveAgentOutput(BaseModel):
    """Final structured output from proactive agent (supports per-location granularity)"""

    output_type: str  # 'SOLUTION', 'ESCALATION'
    location_results: List[ProactiveLocationResult] = Field(default_factory=list)
    summary: str = (
        ""  # Human-readable summary (e.g., "Resolved 2/3 locations via reroute")
    )

    # Legacy fields for backward compatibility
    supply_reroutes: List[AgentSupplyReroute] = Field(default_factory=list)
    preemptive_transfers: List[AgentPreemptiveTransfer] = Field(default_factory=list)
    escalation: Optional[AgentEscalation] = None


# ============================================================================
# AGENT STATE FOR create_agent (TypedDict-based)
# ============================================================================


class EmergencyAgentState(TypedDict):
    """State schema for Emergency Agent using create_agent.

    Note: 'messages' field uses add_messages reducer for proper message accumulation.
    Other fields are optional (NotRequired).

    Additional fields for emergency stockout resolution:
    """

    # Messages (managed by create_agent with add_messages reducer)
    messages: Annotated[list[AnyMessage], add_messages]

    # Input from Orchestrator
    sku_id: NotRequired[str]
    product_details: NotRequired[Dict[str, Any]]
    stockout_locations: NotRequired[List[Any]]  # List of StockoutRecord objects
    available_inventory: NotRequired[Dict[str, int]]

    # Reasoning and audit trail
    reasoning_trace: NotRequired[List[str]]
    tools_called: NotRequired[List[Dict[str, Any]]]
    iteration_count: NotRequired[int]

    # Structured output (set by response_format)
    structured_response: NotRequired[AgentOutput]


class ProactiveAgentState(TypedDict):
    """State schema for Proactive Agent using create_agent.

    Note: 'messages' field uses add_messages reducer for proper message accumulation.
    Other fields are optional (NotRequired).
    """

    # Messages (managed by create_agent with add_messages reducer)
    messages: Annotated[list[AnyMessage], add_messages]

    # Input from Orchestrator
    sku_id: NotRequired[str]
    projected_stockout_locations: NotRequired[List[Dict[str, Any]]]
    current_inventory_snapshot: NotRequired[Dict[str, int]]
    incoming_supply_orders: NotRequired[List[Dict[str, Any]]]
    product_details: NotRequired[Dict[str, Any]]

    # Reasoning and audit trail
    reasoning_trace: NotRequired[List[str]]
    tools_called: NotRequired[List[Dict[str, Any]]]
    iteration_count: NotRequired[int]

    # Structured output (set by response_format)
    structured_response: NotRequired[ProactiveAgentOutput]
