"""Small authenticated SiliconFlow smoke probe. Never prints credentials."""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.siliconflow.cn/v1"


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("SiliconFlow_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("SiliconFlow_API_KEY missing")


def request(method: str, path: str, key: str, payload: dict | None = None) -> dict:
    start = time.monotonic()
    try:
        response = requests.request(method, BASE + path,
                                    headers={"Authorization": "Bearer " + key,
                                             "Content-Type": "application/json"},
                                    json=payload, timeout=(15, 100))
        elapsed = round(time.monotonic() - start, 2)
        try:
            data = response.json()
        except ValueError:
            data = {}
        error = data.get("error") or data.get("message") if isinstance(data, dict) else None
        if isinstance(error, dict):
            error = {k: v for k, v in error.items() if k in ("message", "type", "code")}
        result = {"status": response.status_code, "elapsed_s": elapsed,
                  "rate_headers": {k: v for k, v in response.headers.items()
                                   if k.lower().startswith(("x-ratelimit", "ratelimit", "retry-after"))},
                  "error": error}
        if response.ok:
            result["data"] = data
        return result
    except requests.RequestException as exc:
        return {"status": "network_error", "elapsed_s": round(time.monotonic() - start, 2),
                "error": type(exc).__name__ + ": " + str(exc)[:180]}


def summary(result: dict) -> dict:
    data = result.get("data", {})
    choices = data.get("choices", []) if isinstance(data, dict) else []
    message = choices[0].get("message", {}) if choices else {}
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    return {**{k: v for k, v in result.items() if k != "data"},
            "response_model": data.get("model") if isinstance(data, dict) else None,
            "finish_reason": choices[0].get("finish_reason") if choices else None,
            "content": str(message.get("content", ""))[:500],
            "reasoning_present": bool(message.get("reasoning_content")),
            "reasoning_chars": len(message.get("reasoning_content") or ""),
            "tool_calls": [{"name": call.get("function", {}).get("name"),
                            "arguments": str(call.get("function", {}).get("arguments", ""))[:180]}
                           for call in (message.get("tool_calls") or [])],
            "usage": usage}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["models", "text", "image", "react", "image_react", "act", "plan", "read", "tools", "stream"])
    parser.add_argument("--model", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--tool-choice", default="auto")
    parser.add_argument("--disable-thinking", action="store_true")
    args = parser.parse_args()
    key = load_key()
    if args.mode == "stream":
        start = time.monotonic()
        chunks = 0
        content = ""
        with requests.post(BASE + "/chat/completions",
                           headers={"Authorization": "Bearer " + key,
                                    "Content-Type": "application/json"},
                           json={"model": args.model,
                                 "messages": [{"role": "user", "content": "Reply with exactly READY"}],
                                 "stream": True, "temperature": 0, "max_tokens": 80},
                           stream=True, timeout=(15, 100)) as response:
            if response.ok:
                for line in response.iter_lines():
                    if not line or line == b"data: [DONE]":
                        continue
                    if line.startswith(b"data: "):
                        chunks += 1
                        event = json.loads(line[6:])
                        content += event.get("choices", [{}])[0].get("delta", {}).get("content") or ""
            print(json.dumps({"status": response.status_code, "elapsed_s": round(time.monotonic()-start, 2),
                              "chunks": chunks, "content": content[:500]}, ensure_ascii=False, indent=2))
        return
    if args.mode == "models":
        result = request("GET", "/models", key)
        models = result.get("data", {}).get("data", [])
        result.pop("data", None)
        result["models_total"] = len(models)
        result["qwen_relevant"] = [m.get("id") for m in models
                                   if any(token in m.get("id", "") for token in
                                          ("Qwen3.5-9B", "Qwen3.8-27B", "Qwen3-VL-8B", "Qwen3-VL-32B"))]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    messages: list[dict]
    if args.mode == "text":
        messages = [{"role": "user", "content": "Reply with exactly: READY"}]
    elif args.mode in ("image", "act", "plan", "read"):
        variant = "A2" if args.mode in ("plan", "read") else "A0"
        picture = ROOT / f"data/processed/mind2web/pilot/01790fbcb04e21eb_{variant}.jpg"
        encoded = base64.b64encode(picture.read_bytes()).decode()
        prompt = {
            "image": "What is the visible site name at top left? Reply with only the name.",
            "act": "User task: Browse list of tiktok series songs longer than 60 seconds. Candidate interactive elements are marked with numbered boxes on the screenshot. Which number should be clicked next to complete the user task? Reply with ONLY a single integer.",
            "plan": "User task: Browse list of tiktok series songs longer than 60 seconds. In one short sentence, describe the next legitimate step to advance this task. Do not output a numbered box or click command.",
            "read": "Transcribe the exact text written inside the button labeled with number 1. Return ONLY the text.",
        }[args.mode]
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
        ]}]
    elif args.mode == "tools":
        messages = [{"role": "user", "content": "Call the search function with query 'blue mug price'. Do not guess an answer."}]
        payload = {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 80,
                   "tools": [{"type": "function", "function": {"name": "search", "description": "Search products",
                               "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                               "required": ["query"]}}}], "tool_choice": args.tool_choice}
        raw = request("POST", "/chat/completions", key, payload)
        result = summary(raw)
        choices = raw.get("data", {}).get("choices", [])
        result["reasoning_preview"] = str(choices[0].get("message", {}).get("reasoning_content", ""))[:180] if choices else ""
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    elif args.mode == "image_react":
        picture = ROOT / "data/processed/mind2web/pilot/01790fbcb04e21eb_A0.jpg"
        encoded = base64.b64encode(picture.read_bytes()).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "User task: Browse list of tiktok series songs longer than 60 seconds. First decide an action on this screenshot. Reply ONLY JSON: {\"action\":\"click\",\"id\":number}."},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
        ]}]
        first = summary(request("POST", "/chat/completions", key,
                                {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 160}))
        print(json.dumps({"stage": "image_react_action", **first}, ensure_ascii=False, indent=2))
        if first["status"] != 200 or not first["content"]:
            return
        messages += [{"role": "assistant", "content": first["content"]},
                     {"role": "user", "content": "Tool observation: clicked the selected element; the page now displays the TikTok Series music list. Reply ONLY final answer: done."}]
        final = summary(request("POST", "/chat/completions", key,
                                {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 80}))
        print(json.dumps({"stage": "image_react_final", **final}, ensure_ascii=False, indent=2))
        return
    else:
        # ReAct as a two-turn text loop: ask for a tool decision, then return observation.
        messages = [{"role": "user", "content": "You are a web agent. To find a product price, first choose one tool. Reply ONLY JSON with action and input. Available tool: search(query). Product: blue mug."}]
        first = summary(request("POST", "/chat/completions", key,
                                {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 80}))
        print(json.dumps({"stage": "react_action", **first}, ensure_ascii=False, indent=2))
        if first["status"] != 200 or not first["content"]:
            return
        messages += [{"role": "assistant", "content": first["content"]},
                     {"role": "user", "content": "Tool observation: search found blue mug priced at 12 USD. Reply ONLY final answer with product and price."}]
        final = summary(request("POST", "/chat/completions", key,
                                {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 80}))
        print(json.dumps({"stage": "react_final", **final}, ensure_ascii=False, indent=2))
        return
    payload = {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 80}
    if args.disable_thinking:
        payload["enable_thinking"] = False
    result = summary(request("POST", "/chat/completions", key, payload))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
