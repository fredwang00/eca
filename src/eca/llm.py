"""Shared LLM caller for ECA processors."""

from __future__ import annotations


DEFAULT_MODEL = "claude-sonnet-4-6"


def run_analysis(
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Call LLM API to produce the candor analysis.

    Supports two modes:
    - OpenAI-compatible gateway: set ECA_API_KEY and ECA_BASE_URL
    - Direct Anthropic: set ANTHROPIC_API_KEY
    """
    import os

    api_key = os.environ.get("ECA_API_KEY")
    base_url = os.environ.get("ECA_BASE_URL")

    if api_key:
        if not base_url:
            raise RuntimeError("ECA_API_KEY is set but ECA_BASE_URL is missing")
        # OpenAI-compatible gateway endpoint with custom apikey header
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"apikey": api_key},
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        result = response.choices[0].message.content
    else:
        # Direct Anthropic SDK -- uses ANTHROPIC_API_KEY env var
        import anthropic

        client = anthropic.Anthropic()
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        result = message.content[0].text

    if not result:
        raise RuntimeError(f"Model returned no text content (model={model})")
    return result
