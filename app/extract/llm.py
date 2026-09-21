from __future__ import annotations
import json
from typing import TypeVar

from groq import Groq
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)

_client: Groq | None = None


def client() -> Groq:
    global _client
    if _client is None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=settings.groq_api_key)
    return _client


SYSTEM = """You extract fields from Indian business documents.

Rules:
- Return ONLY a JSON object matching the requested schema. No prose, no markdown.
- Copy values exactly as printed. Do not correct, reformat, or complete them.
- If a field is not present in the document, use null. Never guess.
- Strip surrounding whitespace and label text; return the value only.
"""


def structure(text: str, schema: type[T], hint: str, attempts: int = 2) -> T | None:
    """Turn document text into a validated model. Returns None on failure."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                f"{hint}\n\n"
                f"JSON schema:\n{json.dumps(schema.model_json_schema(), indent=2)}\n\n"
                f"Document text:\n---\n{text}\n---"
            ),
        },
    ]

    for i in range(attempts):
        raw = client().chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        ).choices[0].message.content

        try:
            return schema.model_validate_json(raw)
        except ValidationError as e:
            if i == attempts - 1:
                return None
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user",
                 "content": f"That did not validate. Fix these errors and return "
                            f"corrected JSON only:\n{e}"},
            ]
    return None