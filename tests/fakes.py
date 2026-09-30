"""Fake Groq client: returns queued JSON replies and records the requests it received."""

import json
from types import SimpleNamespace
from typing import Any


class FakeChatClient:
    def __init__(self, replies: list[str | dict | Exception]):
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                prompt_tokens_details=SimpleNamespace(cached_tokens=40),
            ),
        )


def assert_groq_strict(schema: dict) -> None:
    """Groq strict mode: every object lists all its properties as required, no extras."""
    objects = [schema, *schema.get("$defs", {}).values()]
    for obj in objects:
        if obj.get("type") == "object":
            assert obj.get("additionalProperties") is False, obj.get("title")
            assert set(obj.get("required", [])) == set(obj["properties"]), obj.get("title")
