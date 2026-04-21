"""
Standalone Zoom AI Agent streaming client (no parent-agent dependencies).

Protocol:
  POST /api/ai/agent/personal/stream
  SSE lines: {"message": "...", "status": "pending|success|error"}
  Tool calls: model outputs <tool_call>{"name": "...", "input": {...}}</tool_call>
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

STREAM_PATH = "/api/ai/agent/personal/stream"
_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


# ── Shared response types ─────────────────────────────────────────────────────

@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    stop_reason: str          # "end_turn" | "tool_use"
    content: list[Any]        # list of TextBlock / ToolUseBlock


# ── Tool prompt builder ───────────────────────────────────────────────────────

def _build_tool_prompt(tools: list[dict]) -> str:
    if not tools:
        return ""
    lines = [
        "\n\n## Available Tools",
        "When you need to call a tool, output EXACTLY this format "
        "(one tool per response, wait for result before continuing):",
        '<tool_call>{"name": "tool_name", "input": {"param": "value"}}</tool_call>',
        "\nTool list:",
    ]
    for t in tools:
        props = t.get("input_schema", {}).get("properties", {})
        param_desc = ", ".join(
            f"{k}({v.get('type','any')}): {v.get('description','')}"
            for k, v in props.items()
        )
        lines.append(f"- **{t['name']}**: {t['description']} | params: {param_desc}")
    return "\n".join(lines)


def _build_question(
    messages: list[dict],
    system_prompt: str,
    tools: list[dict],
) -> str:
    parts: list[str] = []

    if system_prompt:
        parts.append(f"[System]\n{system_prompt}")

    tool_prompt = _build_tool_prompt(tools)
    if tool_prompt:
        parts.append(tool_prompt)

    has_tool_results = any(isinstance(m.get("content"), list) for m in messages)

    if has_tool_results:
        parts.append("\n[Conversation History]")
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if isinstance(content, str):
                label = "User" if role == "user" else "Assistant"
                parts.append(f"{label}: {content}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "tool_result":
                            parts.append(f"[Tool Result] {block.get('content', '')}")
                        elif btype == "text":
                            parts.append(f"Assistant: {block.get('text', '')}")
                        elif btype == "tool_use":
                            parts.append(
                                f"[Tool Call] {block.get('name')}("
                                f"{json.dumps(block.get('input', {}), ensure_ascii=False)})"
                            )
                    else:
                        if hasattr(block, "text"):
                            parts.append(f"Assistant: {block.text}")
                        elif hasattr(block, "name"):
                            parts.append(
                                f"[Tool Call] {block.name}("
                                f"{json.dumps(block.input, ensure_ascii=False)})"
                            )
        parts.append("\nPlease continue based on the conversation history and tool results above.")
    else:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        parts.append(f"\nUser: {last_user}")

    return "\n".join(parts)


# ── Client ────────────────────────────────────────────────────────────────────

class ZoomLLMClient:
    def __init__(
        self,
        token: str,
        agent_id: str,
        base_url: str = "https://eng.corp.zoom.com",
        conversation_id: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._agent_id = agent_id
        self._conversation_id = conversation_id  # empty string = new conversation

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict],
    ) -> LLMResponse:
        question = _build_question(messages, system_prompt, tools)
        raw = await self._stream(question)
        return self._parse(raw)

    async def _stream(self, question: str) -> str:
        payload: dict[str, Any] = {
            "agentId": self._agent_id,
            "question": question,
            "conversationId": self._conversation_id,
        }
        headers = {
            "Authorization": self._token,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

        url = self._base_url + STREAM_PATH
        chunks: list[str] = []

        async with httpx.AsyncClient(timeout=180, verify=False) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Zoom API error {resp.status_code}: "
                        f"{body.decode('utf-8', errors='replace')}"
                    )

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    status = obj.get("status", "")
                    message = obj.get("message", "")

                    if status == "success":
                        break
                    elif status == "pending" and message:
                        chunks.append(message)
                    elif status == "error":
                        error_msg = obj.get("errorMessage") or obj.get("message", "unknown error")
                        raise RuntimeError(f"Zoom API error: {error_msg}")

        return "".join(chunks)

    async def stream_complete(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
    ):
        """Async generator yielding text chunks as they arrive from Zoom SSE."""
        question = _build_question(messages, system_prompt, tools or [])
        payload: dict[str, Any] = {
            "agentId": self._agent_id,
            "question": question,
            "conversationId": "",
        }
        headers = {
            "Authorization": self._token,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        url = self._base_url + STREAM_PATH
        async with httpx.AsyncClient(timeout=120, verify=False) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Zoom API error {resp.status_code}: "
                        f"{body.decode('utf-8', errors='replace')}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status = obj.get("status", "")
                    message = obj.get("message", "")
                    if status == "pending" and message:
                        yield message
                    elif status == "success":
                        return
                    elif status == "error":
                        error_msg = obj.get("errorMessage") or obj.get("message", "unknown error")
                        raise RuntimeError(f"Zoom API error: {error_msg}")

    @staticmethod
    def _parse(raw_text: str) -> LLMResponse:
        tool_matches = _TOOL_CALL_RE.findall(raw_text)

        if not tool_matches:
            return LLMResponse(stop_reason="end_turn", content=[TextBlock(text=raw_text.strip())])

        content: list[Any] = []
        clean_text = _TOOL_CALL_RE.sub("", raw_text).strip()
        if clean_text:
            content.append(TextBlock(text=clean_text))

        for i, match in enumerate(tool_matches):
            try:
                call = json.loads(match.strip())
                content.append(ToolUseBlock(
                    id=f"zoom_{uuid.uuid4().hex[:8]}_{i}",
                    name=call["name"],
                    input=call.get("input", {}),
                ))
            except (json.JSONDecodeError, KeyError):
                pass  # skip malformed tool calls

        has_tool_use = any(isinstance(b, ToolUseBlock) for b in content)
        return LLMResponse(
            stop_reason="tool_use" if has_tool_use else "end_turn",
            content=content,
        )
