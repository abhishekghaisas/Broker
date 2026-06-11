import modal
import os

app = modal.App("broker-llm")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "anthropic==0.105.2",
    "fastapi[standard]",
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("broker-secrets")],
)
def call_claude(
    system_prompt: str,
    messages: list,
    tools: list = None,
    model: str = "claude-3-5-sonnet-20241022",
) -> dict:
    """Call Claude API and return structured response"""
    from anthropic import Anthropic
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    client = Anthropic(api_key=api_key)

    kwargs = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": messages,
    }

    if tools:
        kwargs["tools"] = tools

    response = client.messages.create(**kwargs)

    return {
        "content": response.content,
        "stop_reason": response.stop_reason,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("broker-secrets")],
)
@modal.fastapi_endpoint(method="POST")
def lm_endpoint(request: dict) -> dict:
    """HTTP endpoint for LLM calls"""
    system_prompt = request.get("system_prompt", "")
    messages = request.get("messages", [])
    tools = request.get("tools", None)
    model = request.get("model", "claude-3-5-sonnet-20241022")

    try:
        result = call_claude(system_prompt, messages, tools, model)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
