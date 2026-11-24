from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock
from openai import APITimeoutError, OpenAI
from PIL import Image


@dataclass(frozen=True)
class EvalRequest:
    sample_id: str
    probe: str
    messages: Sequence[Mapping[str, str]]
    defense: str = "D0"
    image: Path | str | None = None


@dataclass(frozen=True)
class Endpoint:
    provider: str
    model_id: str
    base_url: str
    region: str
    api_key_env: str
    thinking: bool = False


Transport = Callable[[Endpoint, list[dict], dict], Mapping]


def _openai_transport(endpoint: Endpoint, messages: list[dict], options: dict) -> Mapping:
    api_key = os.environ[endpoint.api_key_env]
    with OpenAI(api_key=api_key, base_url=endpoint.base_url, max_retries=0, timeout=60) as client:
        response = client.chat.completions.create(model=endpoint.model_id, messages=messages, **options)
    message = response.choices[0].message if response.choices else None
    return {
        "content": message.content if message else None,
        "reasoning_content": getattr(message, "reasoning_content", None),
        "usage": response.usage.model_dump() if response.usage is not None else None,
        "response_model": response.model,
    }


def _jpeg_bytes(path: Path | str, probe: str) -> bytes:
    expected_size = {"coco": (768, 768), "mind2web": (1024, 680)}.get(probe.split("_", 1)[0])
    with Image.open(path) as image, io.BytesIO() as buffer:
        if expected_size is not None and image.size != expected_size:
            width, height = expected_size
            raise ValueError(f"{probe} expects a {width}×{height} image, got {image.width}×{image.height}")
        image.convert("RGB").save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()


def _find_cached(stream, request_key: str) -> dict | None:
    """Read prior results and repair a partially written final record."""
    cached = None
    while True:
        offset = stream.tell()
        line = stream.readline()
        if not line:
            return cached
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            if line.endswith(b"\n"):
                raise ValueError(f"Invalid JSONL record at byte {offset}") from error
            stream.seek(offset)
            stream.truncate()
            return cached
        if record.get("request_key") == request_key and record.get("status") == "ok":
            cached = record
        if not line.endswith(b"\n"):
            stream.write(b"\n")
            return cached


def run_request(
    request: EvalRequest,
    endpoint: Endpoint,
    log_path: Path | str,
    *,
    transport: Transport = _openai_transport,
) -> dict:
    """Run or resume a request. One worker at a time may use each JSONL log."""
    messages = [dict(message) for message in request.messages]
    if request.probe == "gate_b" and (
        request.image is not None or any(not isinstance(message["content"], str) for message in messages)
    ):
        raise ValueError("Gate B accepts text-only requests")
    options = {
        "stream": False,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 1024 if endpoint.thinking else 128 if request.probe == "mind2web_plan" else 64,
    }
    jpeg = _jpeg_bytes(request.image, request.probe) if request.image is not None else None
    prompt = json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
    metadata = {
        "provider": endpoint.provider,
        "model_id": endpoint.model_id,
        "base_url": endpoint.base_url,
        "region": endpoint.region,
        "thinking": endpoint.thinking,
        "sample_id": request.sample_id,
        "probe": request.probe,
        "defense": request.defense,
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "image_sha256": hashlib.sha256(jpeg).hexdigest() if jpeg is not None else None,
    }
    key_data = json.dumps({**metadata, "options": options}, sort_keys=True).encode()
    request_key = hashlib.sha256(key_data).hexdigest()

    if jpeg is not None:
        if not messages or messages[-1]["role"] != "user":
            raise ValueError("An image request must end with a user message")
        encoded = base64.b64encode(jpeg).decode("ascii")
        messages[-1]["content"] = [
            {"type": "text", "text": messages[-1]["content"]},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
        ]

    log_path = Path(log_path).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(log_path) + ".lock"), log_path.open("a+b") as stream:
        stream.seek(0)
        cached = _find_cached(stream, request_key)
        if cached is not None:
            return cached

        response = {}
        error_info = None
        started = time.monotonic()
        for attempt in range(1, 4):
            try:
                response = transport(endpoint, messages, options)
            except Exception as error:
                status = getattr(error, "status_code", None)
                status = status if isinstance(status, int) else None
                retryable = (
                    isinstance(error, (TimeoutError, APITimeoutError))
                    or status == 429
                    or (status is not None and 500 <= status <= 599)
                )
                if retryable and attempt < 3:
                    time.sleep(2 ** (attempt - 1))
                    continue
                error_info = {"type": type(error).__name__, "http_status": status}
            break

        record = {
            **metadata,
            "request_key": request_key,
            "status": "error" if error_info else "ok",
            "content": response.get("content"),
            "reasoning_content": response.get("reasoning_content"),
            "response_model": response.get("response_model"),
            "usage": response.get("usage"),
            "attempts": attempt,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "error": error_info,
        }
        stream.write((json.dumps(record, ensure_ascii=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
        return record
