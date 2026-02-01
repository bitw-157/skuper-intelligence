"""Data models for Emergency Stockout Resolver Agent"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StockoutRecord(BaseModel):
    """Individual stockout details"""

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
    """Surplus inventory at a location"""

    location_id: str
    total_available_qty: int
    safety_stock_qty: int
    excess_qty: int
    min_days_to_expiry: int
    has_near_expiry: bool
    handling_class: str


class TransportationLane(BaseModel):
    """Transportation route details"""

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
    """Results from simulating a transfer"""

    source: Dict[str, Any]
    destination: Dict[str, Any]
    transfer_qty: int
    lead_time_days: int


class Recommendation(BaseModel):
    """Final transfer recommendation"""

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


class EmergencyStockoutState(BaseModel):
    """Complete state for Emergency Stockout Resolver Agent"""

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


class AgentPriorityAnalysis(BaseModel):
    """Priority analysis when no surplus available"""
    summary: str
    highest_priority_location: str
    urgency_level: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    recommended_action: str


class AgentOutput(BaseModel):
    """Final structured output from agent"""
    output_type: str  # 'TRANSFER' or 'PRIORITY_ANALYSIS'
    transfers: List[AgentTransferRecommendation] = Field(default_factory=list)
    priority_analysis: Optional[AgentPriorityAnalysis] = None
