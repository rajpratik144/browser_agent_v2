"""
Central place for LLM construction. Swap providers or models here without
touching agent/graph.py's wiring logic.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# gpt-4o-mini is natively multimodal, so the same model name covers
# ENABLE_VISION mode in agent/graph.py too — no separate vision model needed.
VISION_MODEL = "gpt-4o-mini"


def get_text_model(temperature: float = 0, max_tokens: int = 1024):
    """Return the configured provider's chat model without binding tools."""
    if LLM_PROVIDER == "openai":
        return ChatOpenAI(model=OPENAI_MODEL, temperature=temperature, max_tokens=max_tokens)
    if LLM_PROVIDER == "groq":
        if not os.environ.get("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY is not set in .env")
        from langchain_groq import ChatGroq
        return ChatGroq(model=GROQ_MODEL, temperature=temperature, max_tokens=max_tokens)
    raise ValueError("LLM_PROVIDER must be 'groq' or 'openai'")


def get_model(tools, vision: bool = False):
    if vision and LLM_PROVIDER == "groq":
        raise ValueError("Groq is configured for text-only tasks; set LLM_PROVIDER=openai for vision.")
    # parallel_tool_calls=False: forces the model to propose one action per
    # turn. Without this, it can (and did) batch multiple DOM-mutating
    # calls — e.g. two type_text calls — into a single turn, which
    # LangGraph's ToolNode then runs CONCURRENTLY via asyncio.gather. Two
    # simultaneous programmatic inputs against the same live page can race
    # against the site's own JS (focus/blur handlers, validation, autofill)
    # in ways a real sequential user action never would. One action per
    # turn also means get_state() is always re-checked before the next
    # move, instead of acting on a stale snapshot.
    return get_text_model(max_tokens=1024).bind_tools(
        tools, parallel_tool_calls=False
    )
