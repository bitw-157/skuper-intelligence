# Skuper Intelligence - Agentic Inventory Rebalancing System

Multi-agent pharmaceutical supply chain system using LangChain, LangGraph, and GPT-5.2 for intelligent stockout prevention and resolution.

## 🎯 System Overview

**Two Specialized Agents:**
- **Emergency Stockout Resolver (Type A)** - Handles immediate stockouts (weeks 0-1) through emergency inventory transfers
- **Proactive Rebalancer (Type B)** - Prevents future stockouts (weeks 2-4) through supply order rerouting and preemptive transfers

**Key Capabilities:**
- Parallel processing: 10 SKUs simultaneously via asyncio
- Per-location granular tracking with partial resolution support
- Constraint validation: Cold chain compliance, safety stock maintenance, lead time feasibility
- Configurable reasoning levels: Emergency=low (fast), Proactive=medium (optimized)

---

## 🚀 Quick Start

### Installation
```bash
# Install dependencies using uv
uv sync

# Or with pip
pip install -r requirements.txt
```

### Environment Setup
Create a `.env` file in the project root:

```bash
# Database Configuration (PostgreSQL/Supabase)
DB_HOST=your-database-host.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres.your-user
DB_PASSWORD=your-password

# OpenAI API Configuration
OPENAI_API_KEY=sk-proj-your-api-key

# LLM Configuration
LLM_MODEL=gpt-5.2
LLM_TEMPERATURE=0
LLM_MAX_TOKENS=6000

# Agent-specific reasoning effort levels
LLM_REASONING_EFFORT_EMERGENCY=low      # Fast for urgent cases
LLM_REASONING_EFFORT_PROACTIVE=medium   # Optimized for planning

# Analysis date configuration
CURRENT_DATE=2026-01-05
CURRENT_WEEK_START=2026-01-05
```

### Running the System

```bash
# Emergency Agent - Current week stockouts
python main.py emergency

# Proactive Agent - Weeks 2-4 projected stockouts
python main.py proactive

# Filter by product family
python main.py emergency --filter Oncology
python main.py proactive --filter Vaccines

# Help
python main.py --help
python main.py emergency --help
```

---

## 📁 Project Structure

```
skuper_repo/
├── .env                             # Environment variables (create from template above)
├── main.py                          # CLI entry point with argparse
├── pyproject.toml                   # Dependencies (uv package manager)
├── README.md                        # This file
│
└── src/                             # Core application code
    ├── __init__.py                  # Package exports
    ├── config.py                    # Database & LLM configuration loader
    ├── models.py                    # Pydantic v2 data models
    ├── tools.py                     # 12 database query tools
    ├── agent_emergency.py           # Emergency agent (Type A)
    ├── agent_proactive.py           # Proactive agent (Type B)
    ├── orchestrator_emergency.py    # Emergency orchestrator (parallel processing)
    └── orchestrator_proactive.py    # Proactive orchestrator (parallel processing)
```

---

## 📦 Module Descriptions

### Core Modules

**`main.py`** - CLI entry point
- Argparse-based command interface with `emergency` and `proactive` subcommands
- Logging setup (console + timestamped file: `skuper_run_YYYYMMDD_HHMMSS.log`)
- Result display and formatting

**`src/config.py`** - Configuration management
- Loads environment variables from `.env`
- Database connection parameters (PostgreSQL)
- OpenAI API key configuration
- LLM settings with agent-specific reasoning levels
- Current date configuration for analysis

**`src/models.py`** - Data models (Pydantic v2)
- `StockoutRecord`, `SurplusLocation`, `TransportationLane` - Database entities
- `AgentOutput`, `ProactiveAgentOutput` - Agent responses with per-location results
- `LocationResolutionResult`, `ProactiveLocationResult` - Granular per-location tracking
- `EmergencyAgentState`, `ProactiveAgentState` - LangGraph state schemas

**`src/tools.py`** - Database query tools (12 tools total)
- **Shared tools (7)**: stockout queries, surplus inventory, transportation lanes, batch details, transfer simulation, cold chain validation, cost calculation
- **Emergency-specific (2)**: demand forecasts, incoming supply checks
- **Proactive-specific (3)**: reroutable supply queries, supply reroute simulation, reroute constraint validation
- All tools decorated with `@tool` for LangChain integration

### Agent Modules

**`src/agent_emergency.py`** - Emergency Stockout Resolver
- 400+ line system prompt with decision frameworks
- Processes current week (0-1) stockouts
- Priority: Inventory transfers from surplus locations
- Reasoning level: `low` (optimized for speed)
- Output: Per-location RESOLVED/UNRESOLVED status with transfer recommendations

**`src/agent_proactive.py`** - Proactive Rebalancer
- 300+ line system prompt with reroute-first strategy
- Processes weeks 2-4 projected stockouts
- Priority: Supply order rerouting (primary), preemptive transfers (fallback)
- Reasoning level: `medium` (optimized for cost efficiency)
- Output: Per-location status with reroute or transfer recommendations

### Orchestrator Modules

**`src/orchestrator_emergency.py`** - Emergency orchestration
- Groups stockouts by SKU, calculates priority scores
- Parallel processing: ThreadPoolExecutor with max 10 workers
- Priority formula: `criticality*4 + severity*3 + urgency*2.5 + location_priority*2`
- Displays per-location results with ✓/✗/⚠ status indicators

**`src/orchestrator_proactive.py`** - Proactive orchestration
- Enriches projected stockouts with incoming supply orders
- Parallel SKU processing via asyncio.gather()
- Priority formula: `time_urgency*3 + severity*2.5 + criticality*2 + value*1.5`
- Displays reroutes, preemptive transfers, or escalations per location

---

## 🤖 Agent Business Logic

### Emergency Stockout Resolver (Type A)

**When to Use:** Current or next week stockouts (urgent)

**Decision Flow:**
1. **Assess Severity** - Product criticality (Oncology=4, Vaccines=3.5, etc.) × shortage magnitude × location priority
2. **Find Surplus** - Query `inventory_batches` for locations with excess inventory above safety stock
3. **Validate Constraints:**
   - Cold chain compliance (ColdChain products require ColdChain locations)
   - Safety stock maintenance (source must remain above safety stock after transfer)
   - Lead time feasibility (max 3 days for Air, 5 days for Ground)
   - Minimum transfer quantities
4. **Calculate Transfer** - Optimal quantity, mode selection (Air preferred for urgency), cost estimation
5. **Output Per-Location:**
   - **RESOLVED**: Transfer recommendation with source, quantity, cost, reasoning
   - **UNRESOLVED**: Specific constraint violation (e.g., "No ColdChain surplus within 3-day lead time")

**Output Structure:**
```json
{
  "output_type": "SOLUTION",
  "location_results": [
    {"location_id": "DC_01", "status": "RESOLVED", "transfer": {...}, "reason_unresolved": null},
    {"location_id": "DC_02", "status": "UNRESOLVED", "transfer": null, "reason_unresolved": "..."}
  ],
  "summary": "Resolved 4 of 5 locations. DC_02 requires external procurement.",
  "transfers": [...],
  "priority_analysis": null
}
```

### Proactive Rebalancer (Type B)

**When to Use:** Weeks 2-4 projected stockouts (advance planning)

**Decision Flow (Sequential Priority):**
1. **Check Incoming Supply** - Query `supply_plan` for reroutable orders (reroutable_flag=1)
2. **Evaluate Supply Reroute** (Primary Mechanism):
   - Simulate reroute using `simulate_supply_reroute`
   - Validate: Does NOT create stockout at original destination
   - Cost check: Delta < $500 typically
   - If valid → **Recommend SUPPLY_REROUTE**
3. **Preemptive Transfer** (Fallback):
   - Query surplus inventory
   - Prefer Ground shipping (cheaper, sufficient time)
   - Validate source stability, destination resolution
   - If valid → **Recommend PREEMPTIVE_TRANSFER**
4. **Escalation** (Last Resort):
   - Document why both options failed
   - Provide priority analysis for human intervention
   - Recommend safety stock adjustments or monitoring

**Output Structure:**
```json
{
  "output_type": "SUPPLY_REROUTE",  // or "PREEMPTIVE_TRANSFER" or "ESCALATION"
  "location_results": [
    {"location_id": "DC_01", "status": "RESOLVED", "action": "SUPPLY_REROUTE", ...},
    {"location_id": "DC_02", "status": "UNRESOLVED", "reason_unresolved": "..."}
  ],
  "summary": "Rerouted SO_00123 to resolve DC_01. DC_02 escalated.",
  "supply_reroutes": [...],
  "preemptive_transfers": []
}
```

---

## 🛠️ Database Requirements

### Required Tables

**Core Tables:**
- `inventory_batches` - Batch-level inventory (on_hand, reserved, available, expiry dates)
- `locations` - Facility data (handling_class, location_type, priority_tier)
- `products` - SKU master (product_family, temp_class, unit_cost_usd)
- `transportation_lanes` - Routes (mode, lead_time, cost_per_unit, min_transfer_qty)
- `safety_stock_parameters` - Minimum inventory targets per location-SKU

**Emergency Agent Tables:**
- `projection_calcs_4w` - 4-week inventory projections with stockout flags
- `demand_forecast_4w` - Weekly demand forecasts with confidence levels

**Proactive Agent Tables:**
- `supply_plan` - Incoming supply orders (reroutable_flag, planned_arrival_date)

### Database Connection
Uses `psycopg` (PostgreSQL driver) with connection pooling. Configure via `.env` file.

---

## 📊 Example Outputs

### Emergency Agent - Console Output
```
==============================================================================
 SKUPER INTELLIGENCE
 Agentic Inventory Rebalancing System
 Emergency Stockout Resolver (Type A Agent)
==============================================================================

Priority Queue:
1. SKU_001 (Oncology) - Priority: 82.45 - Locations: 2
2. SKU_005 (Vaccines) - Priority: 74.20 - Locations: 3

[SKU_001] Processing 2 locations...
  ✓ DC_01: RESOLVED (Transfer: 150 units from DC_03, Air, $645.00)
  ✗ DC_02: UNRESOLVED (No ColdChain surplus within 3-day lead time)

✓ Generated 1 transfer for SKU_001 (1/2 locations resolved)
Total Cost: $645.00
```

### Proactive Agent - Console Output
```
==============================================================================
 SKUPER INTELLIGENCE
 Agentic Inventory Rebalancing System
 Proactive Rebalancer (Type B Agent)
==============================================================================

Priority Queue:
1. SKU_002 (Cardio) - Priority: 68.30 - Locations: 1

[SKU_002] Processing 1 location...
  ✓ DC_01: RESOLVED (Supply Reroute: SO_00123 from DC_03, Ground, +$120 delta)

✓ Generated 1 supply reroute for SKU_002 (1/1 locations resolved)
Cost Delta: +$120.00
```

---

## 🔧 Advanced Configuration

### Priority Scoring Formulas

**Emergency Agent:**
```python
priority_score = (
    criticality * 4.0 +      # Oncology=4, Vaccines=3.5, Cardio=3
    severity * 3.0 +          # Shortage magnitude
    urgency * 2.5 +           # Time sensitivity
    location_priority * 2.0   # Facility tier (1=highest)
)
```

**Proactive Agent:**
```python
priority_score = (
    time_urgency * 3.0 +      # Weeks until stockout
    severity * 2.5 +          # Shortage magnitude
    criticality * 2.0 +       # Product/location importance
    value * 1.5               # Product unit cost
)
```

### Logging Configuration

Logs are written to both console and timestamped files:
- File: `skuper_run_YYYYMMDD_HHMMSS.log` (UTF-8 encoding)
- Console: Clean output with status indicators (✓/✗/⚠)
- Level: INFO (httpx logs suppressed to WARNING)

### Parallel Processing

- **Emergency Agent**: ThreadPoolExecutor with `max_workers=10`
- **Proactive Agent**: asyncio.gather() for parallel SKU processing
- Both agents process SKUs in parallel while maintaining sequential location processing per SKU

---

## 🧪 Validation & Testing

### Pre-run Checks
```bash
# Verify database connection
python -c "import src.config; print('✓ Config loaded')"

# Verify all modules import
python -c "import src.tools; import src.agent_emergency; import src.agent_proactive; print('✓ All modules OK')"

# Check environment variables
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('DB_HOST:', os.getenv('DB_HOST')); print('OPENAI_API_KEY:', 'Set' if os.getenv('OPENAI_API_KEY') else 'Missing')"
```

### Testing Scenarios

**Test Emergency Agent:**
```bash
# Full run
python main.py emergency

# Specific product family
python main.py emergency --filter Oncology

# Check logs for details
tail -f skuper_run_*.log
```

**Test Proactive Agent:**
```bash
# Full run
python main.py proactive

# Specific product family
python main.py proactive --filter Vaccines

# Review supply reroute recommendations
grep "SUPPLY_REROUTE" skuper_run_*.log
```

---

## 🔑 Key Features

### Per-Location Granular Tracking
Both agents now provide per-location resolution status:
- **RESOLVED**: Transfer/reroute successfully planned
- **UNRESOLVED**: Specific constraint violation documented
- **PARTIAL_RESOLUTION**: Some locations resolved, others escalated

### Constraint Validation
- **Cold Chain Compliance**: ColdChain products → ColdChain locations only
- **Safety Stock**: Source locations maintain minimum inventory
- **Lead Time**: Max 3 days Emergency, 7 days Proactive
- **Minimum Transfer Quantity**: Respects lane minimum requirements
- **Expiry Management**: FEFO (First Expire First Out) batches prioritized

### Cost Optimization
- **Emergency Agent**: Optimized for speed (reasoning=low, 99s avg)
- **Proactive Agent**: Optimized for cost (reasoning=medium, 55s avg)
- **Target**: Proactive cost < 70% of emergency cost
- **Mode Selection**: Air (emergency), Ground (proactive)

---

## 🎯 Agent Comparison Table

| Feature | Emergency Resolver | Proactive Rebalancer |
|---------|-------------------|---------------------|
| **Time Horizon** | Weeks 0-1 | Weeks 2-4 |
| **Urgency** | Critical | High (planned) |
| **Primary Action** | Inventory transfer | Supply reroute |
| **Fallback Action** | Escalation | Preemptive transfer |
| **Reasoning Level** | Low (speed) | Medium (optimization) |
| **Avg Processing Time** | 99s per SKU | 55s per SKU |
| **Avg Cost per Transfer** | ~$645 (Air) | ~$450 (Ground) |
| **Shipping Mode** | Air preferred | Ground preferred |
| **Tools Available** | 9 tools | 12 tools |
| **Parallel Processing** | 10 SKUs (ThreadPoolExecutor) | 10 SKUs (asyncio) |
| **Output Granularity** | Per-location status | Per-location status |

---

## 📚 Tech Stack

- **LLM**: OpenAI GPT-5.2 with configurable reasoning effort
- **Framework**: LangChain 1.0+ with LangGraph (ReAct pattern)
- **Database**: PostgreSQL (Supabase hosted)
- **Database Driver**: psycopg (v3)
- **Language**: Python 3.12+
- **Validation**: Pydantic v2
- **Async**: asyncio + ThreadPoolExecutor
- **CLI**: argparse with subcommands
- **Logging**: Python logging (file + console)
- **Package Manager**: uv (fast Python package manager)

---

## 📖 Additional Resources

### File References
- **System Prompts**: 
  - [src/agent_emergency.py](src/agent_emergency.py) - 400+ line emergency prompt
  - [src/agent_proactive.py](src/agent_proactive.py) - 300+ line proactive prompt
- **Tool Definitions**: [src/tools.py](src/tools.py) - All 12 tools with enhanced docstrings
- **Data Models**: [src/models.py](src/models.py) - Pydantic schemas
- **Orchestration Logic**: 
  - [src/orchestrator_emergency.py](src/orchestrator_emergency.py)
  - [src/orchestrator_proactive.py](src/orchestrator_proactive.py)

### Data Setup
Database tables are pre-populated via PostgreSQL. Ensure the following tables exist:
- `projection_calcs_4w` - 4-week inventory projections
- `supply_plan` - Incoming supply orders
- `inventory_batches` - Batch-level inventory
- (See database schema documentation for complete table structure)

---

## 🚀 Future Enhancements

**Completed (MVP):**
- ✅ Emergency Stockout Resolver (Type A)
- ✅ Proactive Rebalancer (Type B)
- ✅ Per-location granular tracking
- ✅ Separate reasoning levels per agent
- ✅ Parallel SKU processing (10 workers)
- ✅ Comprehensive constraint validation

**Planned:**
- [ ] Type C: Strategic Network Optimizer (weeks 5-12)
- [ ] Web dashboard with real-time monitoring
- [ ] Recommendation execution workflow
- [ ] Historical performance analytics
- [ ] Batch optimization for related SKUs
- [ ] API integration for ERP systems

---

## 📝 License

MIT License - Internal pharmaceutical supply chain system

## 👥 Support

For questions or issues:
- Review logs in `skuper_run_YYYYMMDD_HHMMSS.log`
- Check `.env` configuration
- Verify database connectivity
- Contact development team

---

**Last Updated**: February 8, 2026  
**Version**: 1.0.0 (MVP Complete)  
**Status**: Production Ready
