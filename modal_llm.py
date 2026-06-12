import modal
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List

app = modal.App("broker-llm")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "anthropic==0.105.2",
    "fastapi[standard]",
)


class LLMRequest(BaseModel):
    system_prompt: str
    messages: List[dict]
    tools: Optional[List[dict]] = None
    model: str = "claude-haiku-4-5-20251001"
    cache_control: Optional[bool] = False


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("broker-secrets")],
)
@modal.asgi_app()
def create_app():
    """Create and return FastAPI app for Modal"""
    from anthropic import Anthropic
    import os

    fastapi_app = FastAPI()

    @fastapi_app.post("/")
    async def lm_endpoint(request: LLMRequest):
        """HTTP endpoint for LLM calls"""
        try:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            client = Anthropic(api_key=api_key)

            # Build system parameter with optional caching
            if request.cache_control:
                system = [
                    {
                        "type": "text",
                        "text": request.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                system = request.system_prompt

            kwargs = {
                "model": request.model,
                "max_tokens": 4096,
                "system": system,
                "messages": request.messages,
            }

            if request.tools:
                kwargs["tools"] = request.tools

            response = client.messages.create(**kwargs)

            return {
                "success": True,
                "result": {
                    "content": response.content,
                    "stop_reason": response.stop_reason,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    return fastapi_app
