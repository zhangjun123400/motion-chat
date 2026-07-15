"""LLM API proxy — streaming calls + code block extraction."""
import json
import re
from typing import AsyncGenerator

import httpx

from backend.config import config


class LLMProxy:
    def __init__(self) -> None:
        self.url = config.llm_api_url
        self.key = config.llm_api_key
        self.model = config.llm_model
        self.designer_prompt = config.designer_prompt_path.read_text()
        self.fixer_prompt = config.fixer_prompt_path.read_text()

    async def _stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Low-level streaming call to LLM API (Anthropic-compatible format)."""
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": 16384,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self.url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("delta", {})
                            text = delta.get("text", "")
                            if not text and "choices" in chunk:
                                text = (
                                    chunk["choices"][0]
                                    .get("delta", {})
                                    .get("content", "")
                                )
                            if text:
                                yield text
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    async def generate_stream(
        self, user_message: str, context: str | None = None
    ) -> AsyncGenerator[str, None]:
        """First-time generation: designer prompt + optional context + user message."""
        messages: list[dict] = [
            {"role": "system", "content": self.designer_prompt},
        ]
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": user_message})
        async for text in self._stream(messages):
            yield text

    async def fix_stream(
        self, errors: str, script: str
    ) -> AsyncGenerator[str, None]:
        """Fix iteration: fixer prompt + error details + current script."""
        user_content = f"""## 质检错误

{errors}

## 需要修复的脚本

```python
{script}
```

请输出修复后的完整 Python 脚本。"""
        messages = [
            {"role": "system", "content": self.fixer_prompt},
            {"role": "user", "content": user_content},
        ]
        async for text in self._stream(messages):
            yield text

    @staticmethod
    def extract_code(full_output: str) -> str:
        """Extract Python code block from LLM output."""
        pattern = r"```python\s*\n(.*?)```"
        matches = re.findall(pattern, full_output, re.DOTALL)
        if matches:
            return matches[-1].strip()
        pattern = r"```\s*\n(.*?)```"
        matches = re.findall(pattern, full_output, re.DOTALL)
        if matches:
            return matches[-1].strip()
        raise ValueError("No code block found in LLM output")
