"""Configuration for Skuper Intelligence supply chain agent"""

import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# PostgreSQL database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# LLM configuration
LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", "gpt-5.2"),
    "temperature": int(os.getenv("LLM_TEMPERATURE", "0")),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4000")),
    "reasoning": {
        "effort": os.getenv("LLM_REASONING_EFFORT", "low"),
    },
}

# Current date for stockout analysis
CURRENT_DATE = os.getenv("CURRENT_DATE", "2026-01-26")
CURRENT_WEEK_START = os.getenv("CURRENT_WEEK_START", "2026-01-26")
