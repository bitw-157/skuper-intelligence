# Skuper Intelligence - Agentic System Roadmap

## System Architecture Overview

Three-tier agentic system for pharmaceutical inventory rebalancing:

- **Type A (IMPLEMENTED)**: Emergency Stockout Resolver - Reactive (0-7 days)
- **Type B (PLANNED)**: Proactive Rebalancer - Preventive (2-4 weeks)
- **Type C (PLANNED)**: Strategic Optimizer - Network-wide (1-3 months)

---

## Type A: Emergency Stockout Resolver ✅ COMPLETE

**Status**: Production-ready (v1.0)

**Scope**: Current week stockouts requiring immediate inventory transfers

**Key Features**:
- Per-SKU sequential processing with priority queue
- ReAct pattern with 9 database tools
- Structured JSON output (transfers or priority analysis)
- GPT-5.2 with reasoning effort "low"
- Max 2 iterations per SKU

**Output Types**:
1. `TRANSFER` - Inventory redistribution recommendations
2. `PRIORITY_ANALYSIS` - Urgency assessment when no surplus available

**Database Tables Used**:
- `projection_calcs_4w` (stockouts)
- `inventory_batches` (current inventory)
- `transportation_lanes` (routes/costs)
- `SafetyStock_Params` (targets)
- `products`, `locations`

**Tech Stack**:
- LangChain + LangGraph (ReAct workflow)
- PostgreSQL (Supabase)
- Pydantic v2 (validation)
- Rich (terminal UI)

---

## Type B: Proactive Rebalancer 🚧 NEXT PRIORITY

### Problem Statement
Prevent stockouts 2-4 weeks ahead by rerouting inbound supply or initiating preemptive transfers before emergency situations arise.

### Time Horizon
- **Look-ahead**: 2-4 weeks (weeks 2-4 in `projection_calcs_4w`)
- **Action window**: 3-5 days (enough time to reroute supply orders)

### Key Differences from Type A
| Aspect | Type A (Emergency) | Type B (Proactive) |
|--------|-------------------|-------------------|
| **Trigger** | Stockout NOW | Projected stockout in 2-4 weeks |
| **Urgency** | CRITICAL | HIGH/MEDIUM |
| **Mechanism** | Transfer existing inventory | Reroute supply orders + transfers |
| **Cost tolerance** | High (emergency) | Moderate (preventive) |
| **Complexity** | Medium | High (more options) |

### Agent Capabilities

#### 1. Supply Order Rerouting (PRIMARY)
**Tools Required**:
```python
@tool
def query_incoming_supply(sku_id: str, weeks_ahead: int = 4) -> List[Dict]:
    """
    Query supply_plan for incoming orders
    Returns: order_id, sku_id, destination, quantity, eta_week, source_facility
    """
    
@tool
def simulate_supply_reroute(order_id: str, from_location: str, to_location: str) -> Dict:
    """
    Calculate impact of rerouting a supply order
    Returns: new_eta, cost_delta, both_locations_inventory_impact
    """

@tool
def validate_supply_reroute(order_id: str, new_destination: str) -> Dict:
    """
    Check if reroute is feasible (manufacturing constraints, lead times)
    Returns: is_feasible, constraints_violated, alternative_options
    """
```

#### 2. Preemptive Inventory Transfer
- Same tools as Type A but with **lower urgency weighting**
- Focus on **optimal cost** vs Type A's focus on **speed**
- Can use slower transportation modes (Ground vs Air)

### Scope Definition
**IN SCOPE**:
- Week 2-4 projected stockouts (`projected_stockout_flag = 1` AND `week_start_date > current_week`)
- Rerouting supply orders already in `supply_plan`
- Preemptive transfers when supply reroute insufficient
- Cost optimization (not emergency pricing)

**OUT OF SCOPE**:
- Current week stockouts → Type A handles
- Creating new supply orders → Strategic agent
- Network-wide optimization → Type C

### Decision Logic
```
FOR each projected stockout (weeks 2-4):
    1. Check incoming supply orders to ANY location
    2. IF supply order exists for same SKU:
        - Calculate reroute feasibility
        - Simulate impact on BOTH locations
        - IF cost-effective AND doesn't create secondary stockouts:
            → RECOMMEND reroute
        ELSE:
            → Look for preemptive transfer
    3. ELSE (no supply orders):
        - Query surplus at other locations (current + week 1)
        - Calculate transfer with GROUND transport preference
        - IF available AND cost < threshold:
            → RECOMMEND transfer
        ELSE:
            → Escalate to Strategic agent
```

### Output Schema
```python
class ProactiveRecommendation(BaseModel):
    recommendation_type: str  # "SUPPLY_REROUTE" or "PREEMPTIVE_TRANSFER"
    sku_id: str
    target_location: str
    projected_stockout_week: str
    current_severity: int
    
    # For supply reroute
    supply_order_id: Optional[str]
    original_destination: Optional[str]
    new_destination: Optional[str]
    reroute_cost_delta: Optional[float]
    
    # For preemptive transfer
    source_location: Optional[str]
    transfer_quantity: Optional[int]
    recommended_mode: Optional[str]
    transfer_cost: Optional[float]
    
    reasoning: str
    confidence_level: str  # "HIGH", "MEDIUM", "LOW"
    risk_assessment: str
```

### System Prompt Key Points
```
You are the Proactive Rebalancer - prevent stockouts 2-4 weeks ahead.

PRIORITY ORDER:
1. Reroute existing supply orders (lowest cost, minimal disruption)
2. Preemptive inventory transfer (moderate cost)
3. Escalate to Strategic agent if neither viable

DECISION CRITERIA:
- Cost efficiency (not emergency, optimize for value)
- Source location stability (don't create new problems)
- Lead time feasibility (can action arrive in time?)
- Risk mitigation (what if demand spikes?)

CONSTRAINTS:
- Must maintain source location safety stock
- Transport lead time must be < weeks until stockout
- Total cost must be < 70% of emergency response cost
```

### Implementation Priority
1. ✅ Reuse Type A database connection and models
2. ✅ Add 3 new tools for supply order management
3. ✅ Create new system prompt focused on proactive logic
4. ✅ Modify priority scoring (use `projected_stockout_week` not `end_inv_qty`)
5. ✅ Update orchestrator to filter for weeks 2-4
6. ✅ Add supply reroute logic to recommendation processing

**Estimated Effort**: 2-3 days for hackathon MVP

---

## Type C: Strategic Optimizer 🔮 FUTURE ENHANCEMENT

### Problem Statement
Optimize network-wide inventory positioning for 1-3 month horizon, balancing cost, service levels, and network efficiency.

### Time Horizon
- **Look-ahead**: 1-3 months
- **Optimization cycle**: Weekly batch run
- **Implementation**: Gradual (over weeks)

### Key Capabilities

#### 1. Network Rebalancing
- Identify chronic imbalances (locations always overstocked/understocked)
- Recommend permanent safety stock adjustments
- Suggest facility role changes (e.g., DC → RDC)

#### 2. Demand Pattern Analysis
**Tools Required**:
```python
@tool
def analyze_demand_trends(sku_id: str, location_id: str, weeks_back: int = 12) -> Dict:
    """
    Uses historical_demand_8w and demand_forecast_4w
    Returns: trend (increasing/decreasing/stable), seasonality, volatility
    """

@tool
def identify_demand_clusters(sku_id: str) -> List[Dict]:
    """
    Find locations with similar demand patterns
    Returns: cluster_id, locations, shared_characteristics
    """
```

#### 3. Safety Stock Optimization
```python
@tool
def recommend_safety_stock_adjustment(sku_id: str, location_id: str) -> Dict:
    """
    Based on service level targets and demand variability
    Returns: current_ss, recommended_ss, rationale, expected_cost_impact
    """
```

#### 4. Strategic Sourcing
- Identify optimal supplier-location pairings
- Recommend transportation lane investments
- Suggest inventory pooling opportunities

### Decision Framework
```
FOR each SKU:
    1. Analyze 12-week demand history
    2. Identify chronic issues:
        - Repeated stockouts → Increase safety stock or add supplier
        - Persistent overstock → Reduce safety stock or consolidate
        - High transport costs → Optimize sourcing lanes
    3. Calculate network-wide impact
    4. Generate strategic recommendations with ROI estimates
```

### Output Schema
```python
class StrategicRecommendation(BaseModel):
    recommendation_type: str  # "SAFETY_STOCK_ADJUST", "SOURCING_CHANGE", "NETWORK_REDESIGN"
    scope: str  # "SKU_LEVEL", "LOCATION_LEVEL", "NETWORK_LEVEL"
    
    affected_skus: List[str]
    affected_locations: List[str]
    
    current_state_metrics: Dict[str, float]  # cost, service_level, inventory_turns
    proposed_state_metrics: Dict[str, float]
    
    implementation_steps: List[str]
    estimated_implementation_time: str
    estimated_cost: float
    estimated_annual_savings: float
    roi_months: int
    
    reasoning: str
    risk_factors: List[str]
```

### System Prompt Approach
```
You are the Strategic Optimizer - a network design advisor.

FOCUS AREAS:
1. Cost reduction through structural improvements
2. Service level optimization via smart positioning
3. Risk mitigation through demand analysis
4. Long-term efficiency gains

DECISION CRITERIA:
- ROI > 300% in 12 months
- No service level degradation
- Implementation feasible within 90 days
- No single point of failure introduced

You DON'T handle:
- Immediate stockouts → Type A
- Near-term shortages → Type B
- Operational execution → Human planners
```

### Implementation Notes
- **Batch processing**: Run weekly, not per-SKU
- **ML integration**: Consider predictive models for demand forecasting
- **Optimization solver**: May need OR-Tools or PuLP for complex network problems
- **Human-in-loop**: Strategic changes require approval workflow

**Estimated Effort**: 5-7 days for MVP, requires more sophisticated algorithms

---

## Orchestration Layer (All Agents)

### Multi-Agent Coordination

```python
class MasterOrchestrator:
    def __init__(self):
        self.type_a = EmergencyStockoutResolver()
        self.type_b = ProactiveRebalancer()
        self.type_c = StrategicOptimizer()
    
    def run_daily_cycle(self):
        """Execute agents in priority order"""
        
        # 1. Emergency (always first)
        emergency_results = self.type_a.run()
        
        # 2. Proactive (skip if too many emergencies)
        if len(emergency_results['transfers']) < 10:
            proactive_results = self.type_b.run()
        
        # 3. Strategic (weekly only)
        if datetime.today().weekday() == 0:  # Monday
            strategic_results = self.type_c.run()
        
        return {
            'emergency': emergency_results,
            'proactive': proactive_results,
            'strategic': strategic_results
        }
```

### Conflict Resolution
- Type A overrides Type B if same SKU-location
- Type B recommendations update Type C baseline
- Type C changes require human approval before execution

---

## Database Schema Additions (Required for Type B/C)

### New Tables

#### 1. `agent_recommendations`
```sql
CREATE TABLE agent_recommendations (
    recommendation_id SERIAL PRIMARY KEY,
    agent_type VARCHAR(20),  -- 'TYPE_A', 'TYPE_B', 'TYPE_C'
    sku_id VARCHAR(50),
    created_at TIMESTAMP,
    status VARCHAR(20),  -- 'PENDING', 'APPROVED', 'EXECUTED', 'REJECTED'
    recommendation_json JSONB,
    estimated_cost DECIMAL,
    estimated_savings DECIMAL,
    approved_by VARCHAR(100),
    executed_at TIMESTAMP
);
```

#### 2. `supply_reroutes` (for Type B)
```sql
CREATE TABLE supply_reroutes (
    reroute_id SERIAL PRIMARY KEY,
    original_order_id VARCHAR(50),
    sku_id VARCHAR(50),
    from_destination VARCHAR(50),
    to_destination VARCHAR(50),
    reroute_date TIMESTAMP,
    cost_delta DECIMAL,
    reason TEXT,
    agent_recommendation_id INTEGER REFERENCES agent_recommendations(recommendation_id)
);
```

---

## Technology Stack Consistency

**All Agents Use**:
- Python 3.12+
- LangChain + LangGraph (ReAct pattern)
- PostgreSQL (Supabase)
- Pydantic v2
- Rich (terminal UI)
- GPT-5.2 with reasoning

**Agent-Specific**:
- Type A: Max 2 iterations, "low" reasoning effort
- Type B: Max 3 iterations, "medium" reasoning effort
- Type C: Max 5 iterations, "high" reasoning effort (complex optimization)

---

## Hackathon Demo Flow

### Scenario: "Live Agent Showcase"

1. **Setup**: Load sample data with current week stockouts + projected future stockouts
2. **Demo Part 1** (Type A):
   - Show 4 emergency stockouts
   - Agent generates PRIORITY_ANALYSIS for each (no surplus)
   - Highlight CRITICAL urgency levels
   
3. **Demo Part 2** (Type B) - *IF IMPLEMENTED*:
   - Show projected stockout in Week 3
   - Agent finds supply order to different location
   - Recommends reroute with cost savings vs emergency transfer
   
4. **Demo Part 3** (Type C) - *OPTIONAL*:
   - Show slide with strategic recommendations
   - Mock output: "Increase safety stock for SKU_002 at RDC_05 → Prevents 12 annual emergencies, ROI 450%"

**Presentation Focus**:
- Emphasize **agentic autonomy** (not just automation)
- Highlight **reasoning transparency** (show JSON outputs)
- Demonstrate **cost savings** (emergency avoidance)
- Show **production-ready** code quality

---

## MVP Completion Checklist

### Type A (Emergency) ✅
- [x] ReAct workflow with 9 tools
- [x] Structured JSON output
- [x] Priority queue orchestration
- [x] Rich terminal UI
- [x] Error handling & logging
- [x] Database integration
- [x] Environment config

### Type B (Proactive) 🎯
- [ ] Supply order query tools (3 new)
- [ ] Proactive system prompt
- [ ] Week 2-4 filtering logic
- [ ] Supply reroute simulation
- [ ] Cost optimization logic
- [ ] Integration with Type A orchestrator
- [ ] Test with sample supply_plan data

### Type C (Strategic) 📋
- [ ] Demand trend analysis tools
- [ ] Safety stock recommendation logic
- [ ] Network-wide batch processing
- [ ] ROI calculation
- [ ] Approval workflow (mock)
- [ ] Presentation slides

---

## File Structure (Projected)

```
skuper_repo/
├── src/
│   ├── agents/
│   │   ├── type_a_emergency.py      # ✅ Current agent.py
│   │   ├── type_b_proactive.py      # 🚧 To implement
│   │   └── type_c_strategic.py      # 📋 Future
│   ├── tools/
│   │   ├── inventory_tools.py       # ✅ Current tools.py
│   │   ├── supply_tools.py          # 🚧 For Type B
│   │   └── analytics_tools.py       # 📋 For Type C
│   ├── orchestrators/
│   │   ├── emergency_orchestrator.py    # ✅ Current orchestrator.py
│   │   ├── proactive_orchestrator.py    # 🚧 To implement
│   │   └── master_orchestrator.py       # 📋 Multi-agent coordinator
│   ├── models.py                    # ✅ Shared Pydantic models
│   ├── config.py                    # ✅ Env config
│   └── __init__.py
├── main.py                          # ✅ Entry point
├── main_proactive.py                # 🚧 Type B entry point
├── main_strategic.py                # 📋 Type C entry point
├── .env                             # ✅ Secrets
├── pyproject.toml                   # ✅ Dependencies
└── AGENT_ROADMAP.md                 # ✅ This file
```

---

## Next Steps (Priority Order)

1. **Complete Type A Polish** (1 day)
   - Implement `_get_available_inventory_for_sku()` with real queries
   - Add recommendation persistence to database
   - Create demo data with surplus inventory

2. **Implement Type B MVP** (2-3 days)
   - Add supply order tools
   - Create proactive agent prompt
   - Build separate orchestrator
   - Test end-to-end flow

3. **Strategic Demo Materials** (1 day)
   - Create presentation slides
   - Mock Type C outputs
   - Prepare hackathon pitch deck

4. **Integration & Testing** (1 day)
   - Test all agents with same dataset
   - Verify no recommendation conflicts
   - Performance optimization

**Total Estimate**: 5-6 days for complete hackathon-ready system

---

## Success Metrics

**Type A**: Response time < 30 sec/SKU, 100% JSON parse success
**Type B**: 30% cost reduction vs emergency transfers
**Type C**: 3+ strategic recommendations with clear ROI

**Overall**: Demonstrates "thinking" not just "doing" - the hallmark of true agents!
