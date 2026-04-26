"""
core/llm_client.py
─────────────────────────────────────────────────────────────────────────────
Thin abstraction over LLM providers. Swap provider in config without touching
agent code.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import re
from typing import Optional


class LLMClient:
    def __init__(self, config: dict):
        self.provider = config["llm"]["provider"]
        self.model = config["llm"]["model"]
        self.temperature = config["llm"]["temperature"]
        self.max_tokens = config["llm"]["max_tokens"]

    def complete(self, system: str, user: str) -> str:
        """Return the text content of the LLM response."""
        if self.provider == "groq":
            return self._groq(system, user)
        elif self.provider == "openai":
            return self._openai(system, user)
        elif self.provider == "anthropic":
            return self._anthropic(system, user)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def complete_json(self, system: str, user: str) -> dict:
        """Ask the LLM to return JSON and parse it safely."""
        raw = self.complete(system, user + "\n\nRespond with valid JSON only. No markdown fences.")
        # Strip any accidental ```json fences
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        
        try:
            # Use strict=False to allow control characters like literal newlines in strings
            return json.loads(cleaned, strict=False)
        except json.JSONDecodeError:
            # If standard parsing fails, try to find the JSON object block
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1), strict=False)
                except json.JSONDecodeError as e:
                    raise ValueError(f"LLM returned invalid JSON (even after extraction): {e}\n\nRaw response:\n{raw[:500]}")
            
            raise ValueError(f"LLM returned invalid JSON and no JSON block was found.\n\nRaw response:\n{raw[:500]}")

    # ── Provider implementations ──────────────────────────────────────────────

    def _groq(self, system: str, user: str) -> str:
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _openai(self, system: str, user: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _anthropic(self, system: str, user: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
