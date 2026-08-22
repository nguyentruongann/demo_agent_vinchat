import json
import random
import time
from typing import Any

from litellm import completion
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from src.backend.config import get_settings


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()

        self.model = settings.llm_model
        self.api_key = settings.llm_api_key
        self.api_key_backup = settings.llm_api_key_backup
        self.base_url = settings.llm_base_url

        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.timeout = settings.llm_timeout
        self.max_retries = settings.llm_max_retries

    def text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        last_error: Exception | None = None

        api_keys = [
            key
            for key in [
                self.api_key,
                self.api_key_backup,
            ]
            if key
        ]

        if not api_keys:
            raise RuntimeError(
                "No LLM API key configured."
            )

        for key_index, api_key in enumerate(
            api_keys,
            start=1,
        ):
            for attempt in range(
                1,
                self.max_retries + 1,
            ):
                try:
                    kwargs: dict[str, Any] = {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": system_prompt,
                            },
                            {
                                "role": "user",
                                "content": user_prompt,
                            },
                        ],
                        "temperature": (
                            self.temperature if temperature is None else float(temperature)
                        ),
                        "max_tokens": self.max_tokens if max_tokens is None else int(max_tokens),
                        "timeout": self.timeout,
                        "api_key": api_key,
                    }

                    if self.base_url:
                        kwargs["api_base"] = self.base_url

                    response = completion(**kwargs)

                    content = (
                        response.choices[0]
                        .message
                        .content
                    )

                    if not content:
                        raise ValueError(
                            "LLM returned an empty response."
                        )

                    return content.strip()

                except (
                    RateLimitError,
                    ServiceUnavailableError,
                    APIConnectionError,
                    Timeout,
                    APIError,
                ) as exc:
                    last_error = exc

                    print(
                        f"Gemini key {key_index} "
                        f"failed: "
                        f"{type(exc).__name__} "
                        f"({attempt}/"
                        f"{self.max_retries})"
                    )

                    if attempt == self.max_retries:
                        break

                    wait_seconds = min(
                        5.0,
                        (2 ** attempt)
                        + random.uniform(0, 1),
                    )

                    time.sleep(wait_seconds)

            if key_index < len(api_keys):
                print(
                    "Switching to backup "
                    "Gemini API key..."
                )

        raise RuntimeError(
            "All Gemini API keys failed."
        ) from last_error

    def json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Run a structured control/judgement call deterministically by default.

        Free-form answer generation still uses ``self.temperature`` through
        :meth:`text`. JSON calls in this project are routing, intent, memory,
        sufficiency, triage, or grounding decisions; letting them inherit the
        creative answer temperature makes the agent graph non-deterministic. One
        compact repair attempt handles truncated control output safely.
        """
        raw = self.text(
            system_prompt=(
                system_prompt
                + "\nReturn valid JSON only. "
                + "Do not use Markdown code fences."
            ),
            user_prompt=user_prompt,
            temperature=temperature,
        )

        try:
            return self._parse_json_object(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            repair_raw = self.text(
                system_prompt=(
                    "Repair the supplied invalid or truncated output into one compact valid JSON object. "
                    "Keep only recoverable values, never reproduce long narrative text, and return JSON only."
                ),
                user_prompt="INVALID_OUTPUT:\n" + raw[:12000] + "\n\nReturn one compact JSON object.",
                temperature=0.0,
                max_tokens=min(max(self.max_tokens, 256), 600),
            )
            try:
                return self._parse_json_object(repair_raw)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise ValueError(
                    "The model returned invalid JSON after one bounded repair attempt "
                    f"(original_chars={len(raw)}, repaired_chars={len(repair_raw)})."
                ) from exc

    @staticmethod
    def _parse_json_object(raw: str) -> dict[str, Any]:
        text_value = str(raw or "").strip()
        if not text_value:
            raise ValueError("empty JSON response")
        decoder = json.JSONDecoder()
        starts = [0, *(i for i, character in enumerate(text_value) if character == "{")]
        last_error: Exception | None = None
        for start in dict.fromkeys(starts):
            try:
                value, _end = decoder.raw_decode(text_value[start:])
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(value, dict):
                return value
            last_error = ValueError("structured response is not a JSON object")
        if last_error is not None:
            raise last_error
        raise ValueError("no JSON object found")
