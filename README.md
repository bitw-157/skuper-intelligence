# Skuper Intelligence - Emergency Stockout Resolver

Agentic pharmaceutical inventory rebalancing system using LangGraph and GPT-5.2.

## 🚀 Quick Start

```bash
# Install dependencies
uv sync

# Run tests
uv run python test_system.py

# Run the system
uv run python main.py
```

## 📁 Project Structure

```
skuper_repo/
├── src/
│   ├── config.py          # Database & LLM configuration
│   ├── models.py          # TypedDict data models
│   ├── tools.py           # 9 database query tools
│   ├── agent.py           # Agent prompt & LangGraph workflow
│   ├── orchestrator.py    # Per-SKU priority queue
│   └── __init__.py        # Package exports
├── data/                  # CSV files
├── main.py                # CLI entry point
├── test_system.py         # Validation tests
├── pyproject.toml         # Dependencies (uv)
└── README.md
```

## 🔧 Configuration

Edit [src/config.py](src/config.py):

```python
DB_CONFIG = {
    "host": "your-database-host",
    "port": 5432,
    "dbname": "postgres",
    "user": "your-username",
    "password": "your-password",
}

OPENAI_API_KEY = "your-api-key"
```

## 🎯 Features

- **Agentic Reasoning**: LLM-powered decision making with ReAct pattern
- **Priority Queue**: CRITICAL drugs (Oncology, Vaccines) processed first
- **Per-SKU Processing**: Deep reasoning for each SKU (2-4K tokens/SKU)
- **9 Database Tools**: Inventory queries, route optimization, impact simulation
- **LangGraph Workflow**: Iterative tool calling with conditional edges
- **400+ Line System Prompt**: 6-phase decision framework

## 📊 Usage

```bash
# Process all stockouts
uv run python main.py

# Filter by product family
uv run python main.py Oncology
uv run python main.py Vaccines
```

## 🧪 Testing

```bash
uv run python test_system.py
```

## 📚 Documentation

- **Agent System Prompt**: [src/agent.py](src/agent.py) (lines 10-400)
- **Database Tools**: [src/tools.py](src/tools.py)
- **Data Models**: [src/models.py](src/models.py)

## 🏗️ Architecture

```
main.py
   ↓
StockoutOrchestrator
   ├── Queries stockouts from DB
   ├── Groups by SKU
   ├── Calculates priority scores
   └── For each SKU:
        ↓
   create_emergency_workflow()
        ├── Agent Node (LLM reasoning)
        ├── Tool Node (DB queries)
        └── Conditional Edge (continue/end)
             ↓
        Recommendation
```

## 🤖 System Prompt Phases

1. **Assess Severity**: Product criticality, magnitude, timing, location priority
2. **Find Surplus**: Prioritize near-expiry, validate stability
3. **Evaluate Transportation**: Lead time, cost, minimum quantity
4. **Calculate Quantity**: Shortage + safety buffer + forecast buffer
5. **Validate**: Simulate impact, check expiry/constraints
6. **Generate Recommendation**: Structured output with rationale

## 🔨 Tech Stack

- **LLM**: GPT-5.2-chat-latest (OpenAI)
- **Framework**: LangChain + LangGraph (ReAct pattern)
- **Database**: PostgreSQL (Supabase)
- **Language**: Python 3.12+
- **Package Manager**: uv

## 📝 License

MIT
