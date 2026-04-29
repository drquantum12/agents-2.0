"""
Rule-based text-matching patterns and helpers.

Used by intent_router to classify user input WITHOUT an LLM call.
All patterns are case-insensitive (applied after .lower()).
"""

import json
import re

# ---------------------------------------------------------------------------
# Pattern lists
# ---------------------------------------------------------------------------

YES_PATTERNS = [
    # "yes" optionally followed by one qualifier — catches "yes please", "yes sure", "yes go ahead"
    r"^yes(?:\s+(?:please|sure|ok(?:ay)?|do|go\s+ahead|definitely|absolutely|why\s+not|of\s+course|let'?s))?[\s!.,]*$",
    # Stand-alone affirmatives
    r"^(yeah|yep|yup|sure|ok(?:ay)?|absolutely|definitely|please|go\s+ahead)[\s!.,]*$",
    # Phrase-form affirmatives
    r"^(let'?s?\s+do\s+it|let'?s?\s+go|sounds?\s+good|why\s+not|of\s+course|i'?d?\s+(?:like|love)\s+(?:that|to))[\s!.]*$",
    # Action phrases that imply "yes, teach me"
    r"^(break\s+it\s+down|explain\s+(?:it|in\s+detail)|teach\s+me|tell\s+me\s+more|go\s+ahead|i\s+want\s+to\s+learn)",
    r"^haan$",  # Hindi "yes"
]

NO_PATTERNS = [
    r"^(no|nah|nope|not?\s+(?:really|now|thanks)|i'?m?\s+good|skip|never\s*mind|that'?s?\s+(?:enough|fine|okay|ok))[\s!.]*$",
    r"^(i\s+don'?t\s+(?:want|need)|no\s+thanks?|that'?s?\s+all)[\s!.]*$",
    r"^nahi$",  # Hindi "no"
]

STOP_PATTERNS = [
    r"^(stop|exit|enough|band\s+karo|quit|i'?m?\s+done|that'?s?\s+(?:all|enough)|finish)",
    r"^(that\s+was\s+enough|no\s+more|no\s+further)",
]

LEARNING_INTENT_PATTERNS = [
    r"\b(explain|teach|help me (?:learn|understand)|run me through|walk me through|break it down)\b",
    r"\b(tell me (?:about|something about)|what is|how does|how do|why does|why do)\b",
    r"\b(photosynthesis|trigonometry|algebra|chemistry|physics|biology|history|geography)\b",
]

# Markers in the previous AI turn that indicate a lesson was offered.
LESSON_OFFER_MARKERS = [
    "want me to run you through",
    "want me to break",
    "step by step",
    "detailed lesson",
]


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------

def is_yes(text: str) -> bool:
    text_lower = text.strip().lower()
    return any(re.search(p, text_lower) for p in YES_PATTERNS)


def is_no(text: str) -> bool:
    text_lower = text.strip().lower()
    return any(re.search(p, text_lower) for p in NO_PATTERNS)


def is_stop(text: str) -> bool:
    text_lower = text.strip().lower()
    return any(re.search(p, text_lower) for p in STOP_PATTERNS)


def is_learning_intent(text: str) -> bool:
    text_lower = text.strip().lower()
    return any(re.search(p, text_lower) for p in LEARNING_INTENT_PATTERNS)


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------

def extract_topic_from_text(text: str) -> str:
    """Strip common question prefixes to return a bare topic string."""
    cleaned = text.strip().strip("?.! ")
    lowered = cleaned.lower()
    prefixes = [
        "tell me something about ",
        "tell me about ",
        "explain ",
        "teach me ",
        "help me understand ",
        "what is ",
        "how does ",
        "why does ",
    ]
    for prefix in prefixes:
        if lowered.startswith(prefix):
            topic = cleaned[len(prefix):].strip()
            return topic if topic else cleaned
    return cleaned


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def extract_json_object(text: str) -> dict | None:
    """Tolerant JSON extraction: handles markdown fences and surrounding prose."""
    if not text:
        return None
    candidate = text.strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except Exception:
            return None
    return None
