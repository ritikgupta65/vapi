import json
import os
import time
import uuid
from datetime import datetime
from flask import Flask, Response, jsonify, request, stream_with_context
from dotenv import load_dotenv

try:
    from azure.ai.inference import ChatCompletionsClient  # type: ignore
    from azure.ai.inference.models import (
        SystemMessage,
        UserMessage,
        AssistantMessage,
        DeveloperMessage,
        ToolMessage,
    )  # type: ignore
    from azure.core.credentials import AzureKeyCredential  # type: ignore
    from azure.core.exceptions import HttpResponseError  # type: ignore
except ImportError as exc:  # pragma: no cover - guard for missing dependencies
    raise RuntimeError(
        "Required Azure AI SDK packages are not installed."
    ) from exc

app = Flask(__name__)

# -------------------------
# CONFIGURATION
# -------------------------
load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-4.1-mini")

if not LLM_API_KEY or not LLM_BASE_URL:
    raise RuntimeError("LLM_API_KEY and LLM_BASE_URL must be set in the environment")

llm_client = ChatCompletionsClient(
    endpoint=LLM_BASE_URL,
    credential=AzureKeyCredential(LLM_API_KEY)
)

SAFE_CONTENT_FILTER = {
    "hate": {"filtered": False, "severity": "safe"},
    "self_harm": {"filtered": False, "severity": "safe"},
    "sexual": {"filtered": False, "severity": "safe"},
    "violence": {"filtered": False, "severity": "safe"},
    "protected_material_code": {"filtered": False, "detected": False},
    "protected_material_text": {"filtered": False, "detected": False},
    "jailbreak": {"filtered": False, "detected": False},
}


# -------------------------
# HELPER FUNCTIONS
# -------------------------
def _normalize_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        normalized_parts = []
        for part in content:
            if isinstance(part, dict):
                text_value = part.get("text")
                if text_value:
                    normalized_parts.append(text_value)
            elif part is not None:
                normalized_parts.append(str(part))
        return "\n".join(normalized_parts)
    if content is None:
        return ""
    return str(content)


def _to_sdk_messages(messages):
    sdk_messages = []
    for message in messages:
        role = str(message.get("role", "user")).lower()
        content = _normalize_content(message.get("content"))

        if role == "system":
            sdk_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            sdk_messages.append(AssistantMessage(content=content))
        elif role == "developer":
            sdk_messages.append(DeveloperMessage(content=content))
        elif role == "tool":
            tool_call_id = message.get("tool_call_id")
            if tool_call_id:
                sdk_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id))
            else:
                sdk_messages.append(UserMessage(content=content))
        else:
            sdk_messages.append(UserMessage(content=content))

    return sdk_messages


def _extract_response_text(llm_response):
    if not llm_response.choices:
        return ""

    assistant_message = llm_response.choices[0].message
    content = getattr(assistant_message, "content", "")

    if isinstance(content, list):
        normalized_parts = []
        for part in content:
            if isinstance(part, dict):
                text_value = part.get("text")
                if text_value:
                    normalized_parts.append(text_value)
            elif part is not None:
                normalized_parts.append(str(part))
        return "\n".join(normalized_parts)

    if content is None:
        return ""

    return str(content)


def call_llm(messages, model_name):
    sdk_messages = _to_sdk_messages(messages)
    response = llm_client.complete(
        model=model_name,
        messages=sdk_messages,
        temperature=0.7,
        max_tokens=512,
    )
    return response


def _coerce_usage(usage_obj):
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    if usage_obj is None:
        return usage

    def _maybe_get(attr_name):
        if hasattr(usage_obj, attr_name):
            return getattr(usage_obj, attr_name)
        if isinstance(usage_obj, dict):
            return usage_obj.get(attr_name)
        return None

    def _coerce_int(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    prompt_tokens = _maybe_get("prompt_tokens") or _maybe_get("input_tokens")
    completion_tokens = _maybe_get("completion_tokens") or _maybe_get("output_tokens")
    total_tokens = _maybe_get("total_tokens")

    prompt_int = _coerce_int(prompt_tokens)
    if prompt_int is not None:
        usage["prompt_tokens"] = prompt_int

    completion_int = _coerce_int(completion_tokens)
    if completion_int is not None:
        usage["completion_tokens"] = completion_int

    total_int = _coerce_int(total_tokens)
    if total_int is not None:
        usage["total_tokens"] = total_int

    if usage["total_tokens"] == 0:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    return usage


def _normalize_finish_reason(reason):
    if reason is None:
        return "stop"
    value = getattr(reason, "value", None)
    if value:
        return value
    if isinstance(reason, str):
        return reason
    return str(reason)


def _build_choice_payload(content, finish_reason):
    finish_reason_value = _normalize_finish_reason(finish_reason)
    return {
        "index": 0,
        "message": {
            "role": "assistant",
            "content": content,
            "refusal": None,
            "annotations": [],
        },
        "logprobs": None,
        "finish_reason": finish_reason_value,
        "content_filter_results": SAFE_CONTENT_FILTER,
    }


def _build_chat_response(llm_resp, model_name, content):
    response_id = getattr(llm_resp, "id", f"chatcmpl-{uuid.uuid4().hex}")
    created_raw = getattr(llm_resp, "created", None)
    if isinstance(created_raw, datetime):
        created = int(created_raw.timestamp())
    elif created_raw is not None:
        try:
            created = int(created_raw)
        except (TypeError, ValueError):
            created = int(time.time())
    else:
        created = int(time.time())
    finish_reason = None
    if getattr(llm_resp, "choices", None):
        finish_reason = getattr(llm_resp.choices[0], "finish_reason", None)

    usage = _coerce_usage(getattr(llm_resp, "usage", None))
    model_used = getattr(llm_resp, "model", model_name)
    system_fingerprint = getattr(llm_resp, "system_fingerprint", None)

    response_payload = {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model_used,
        "choices": [
            _build_choice_payload(content, finish_reason)
        ],
        "usage": usage,
        "prompt_filter_results": [
            {
                "prompt_index": 0,
                "content_filter_results": SAFE_CONTENT_FILTER,
            }
        ],
    }

    if system_fingerprint:
        response_payload["system_fingerprint"] = system_fingerprint

    return response_payload


def _chunk_text(content, chunk_size=80):
    if not content:
        return [""]
    return [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]


def _streaming_response(response_payload, content, finish_reason):
    response_id = response_payload["id"]
    model_used = response_payload["model"]
    created = response_payload["created"]
    usage = response_payload.get("usage", {})
    finish_value = _normalize_finish_reason(finish_reason)

    @stream_with_context
    def event_stream():
        first_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_used,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "logprobs": None,
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(first_chunk)}\n\n"

        for chunk in _chunk_text(content):
            if not chunk:
                continue
            data = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_used,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": chunk,
                        },
                        "logprobs": None,
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(data)}\n\n"

        final_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_used,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "logprobs": None,
                    "finish_reason": finish_value,
                    "content_filter_results": SAFE_CONTENT_FILTER,
                }
            ],
            "usage": usage,
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "Connection": "keep-alive",
    }

    return Response(event_stream(), headers=headers)


# -------------------------
# ROUTES
# -------------------------
@app.route("/", methods=["GET"])
def home():
    return "Flask server is running!", 200


@app.route("/chat/completions", methods=["POST"])
def chat_completions():
    try:
        data = request.get_json()
        print("Incoming payload from Vapi:", data)

        if not data or "messages" not in data:
            return jsonify({"error": "Invalid input, expecting 'messages'"}), 400

        messages = data["messages"]
        model_name = data.get("model", DEFAULT_MODEL)
        stream = bool(data.get("stream", False))
        print("Using model:", model_name)

        llm_resp = call_llm(messages, model_name)
        print("LLM response:", llm_resp)

        content = _extract_response_text(llm_resp)
        if content == "":
            return jsonify({"error": "Empty response from LLM"}), 502

        formatted = _build_chat_response(llm_resp, model_name, content)

        if stream:
            finish_reason = formatted["choices"][0].get("finish_reason")
            return _streaming_response(formatted, content, finish_reason)

        return jsonify(formatted)

    except HttpResponseError as http_err:
        return jsonify({
            "error": "LLM HTTP error",
            "detail": str(http_err),
            "response": getattr(http_err, "message", "")
        }), 502

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": "Internal error", "detail": str(e)}), 500


# -------------------------
# RUN APP
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
