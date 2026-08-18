import json
import random
import re
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
                        "max_tokens": self.max_tokens,
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
        creative answer temperature makes the agent graph non-deterministic.
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
            return json.loads(raw)

        except json.JSONDecodeError:
            match = re.search(
                r"\{.*\}",
                raw,
                flags=re.DOTALL,
            )

            if not match:
                raise ValueError(
                    "The model did not return valid JSON. "
                    f"Raw output: {raw}"
                )

            return json.loads(
                match.group(0)
            )