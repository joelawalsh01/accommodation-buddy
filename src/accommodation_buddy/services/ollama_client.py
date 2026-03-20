import json
import logging
from collections.abc import AsyncIterator

import httpx

from accommodation_buddy.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.ollama_url

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        images: list[str] | None = None,
        system: str | None = None,
        keep_alive: str | None = None,
        options: dict | None = None,
    ) -> str:
        model = model or settings.scaffolding_model
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = images
        if system:
            payload["system"] = system
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            result = data["response"]
            if not result.strip():
                logger.warning(
                    f"Empty response from {model}. "
                    f"done_reason={data.get('done_reason')}, "
                    f"eval_count={data.get('eval_count')}, "
                    f"prompt_eval_count={data.get('prompt_eval_count')}"
                )
            return result

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
        keep_alive: str | None = None,
    ) -> str | AsyncIterator[str]:
        model = model or settings.scaffolding_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        if stream:
            return self._stream_chat(payload)

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat", json=payload
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def _stream_chat(self, payload: dict) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if content := data.get("message", {}).get("content"):
                            yield content

    async def list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return resp.json().get("models", [])

    async def list_running_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/ps")
            resp.raise_for_status()
            return resp.json().get("models", [])

    async def unload_model(self, name: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{self.base_url}/api/generate",
                json={"model": name, "prompt": "", "keep_alive": "0"},
            )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


ollama_client = OllamaClient()
