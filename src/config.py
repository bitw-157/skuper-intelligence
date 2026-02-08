"""Configuration for Skuper Intelligence supply chain agent"""

import os

from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", "gpt-5.2"),
    "temperature": int(os.getenv("LLM_TEMPERATURE", "0")),
    "reasoning": {
        "emergency": os.getenv("LLM_REASONING_EFFORT_EMERGENCY", "low"),
        "proactive": os.getenv("LLM_REASONING_EFFORT_PROACTIVE", "medium"),
    },
}

# Current date for stockout analysis
# Set to first week in the data so weeks 2-4 align with available projection data
CURRENT_DATE = os.getenv("CURRENT_DATE", "2026-01-05")
CURRENT_WEEK_START = os.getenv("CURRENT_WEEK_START", "2026-01-05")
