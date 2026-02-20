# Voice & Text-to-Speech Guidelines

This document outlines the constraints and best practices for generating text that will be converted to speech in the NeuroSattva Guided Learning Agent.

## 1. Length Constraints

*   **Explanations**: Maximum **50 words**. This ensures the audio response is snappy and keeps the user engaged without long monologues.
*   **Feedback**: Maximum **20 words**. Praise or correction should be immediate and brief.

## 2. Formatting Constraints (CRITICAL)

The text-to-speech engine reads exactly what is written. Therefore, strict formatting rules apply:

*   **NO Special Symbols**:
    *   ❌ Avoid `*`, `#`, `-`, `_`, `~`, `|`, `>`
    *   ❌ Markdown headers (`## Topic`) are forbidden.
    *   ❌ Bullet points (`- point`) are forbidden.
    *   ✅ Use full sentences or comma-separated lists instead.
*   **NO Formatting**:
    *   ❌ **Bold** and *Italics* markers will be read as "asterisk asterisk". Do not use them.
*   **Plain Text Only**: Write as if you are writing a script for a radio host.

## 3. Content Guidelines

*   **No User Names**: Do not mistakenly insert placeholders like `{user_name}` or ask the LLM to use the user's name, as this can sound robotic if repeated.
*   **Conversation Flow**:
    *   Always end explanations with a **question** to prompt the user's turn.
    *   Feedback (e.g., "Great job") is prepended to the explanation automatically by the code.

## 4. Prompt Engineering

When modifying prompts (`app/agents/prompts.py`), always include these instructions:

```text
- Keep response under 50 words.
- DO NOT use any special symbols like asterisks (*), hashtags (#), dashes (-).
- Write in full, plain sentences only.
- NO headings or markdown formatting.
```
