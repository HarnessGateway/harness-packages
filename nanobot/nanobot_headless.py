#!/usr/bin/env python3
"""One headless nanobot turn, as JSON lines on standard output.

nanobot's command line has no machine-readable mode: `nanobot agent -m` prints a rendered answer and
progress hints. Its makers do document a Python SDK over the same agent runtime, with typed streaming
events. This driver uses that SDK: it reads one turn's spec as JSON on standard input, runs the agent
once, and prints what happened as one JSON object per line. `run` translates those lines into the
platform's events.

The spec, on stdin:

    {"prompt": "...", "session_key": "cli:direct", "effort": null, "max_output_tokens": 8192,
     "temperature": 0.1, "mcp_servers": [{"label": "...", "url": "...", "headers": {...},
                                          "allowed_tools": ["..."]}]}

Lines, on stdout:

    {"event": "session", "session": "cli:direct"}
    {"event": "text", "text": "..."}                 a piece of the answer
    {"event": "reasoning", "text": "..."}            a piece of reasoning
    {"event": "tool", "phase": "start", ...}
    {"event": "tool", "phase": "end", "name": ..., "arguments": {...}, "ok": true,
     "result": "...", "error": null, "files": [{"path": "...", "action": "create",
                                                "diff": "+..."}]}
    {"event": "done", "content": "...", "stop_reason": "completed",
     "usage": {"input_tokens": 1, "output_tokens": 2, "cached_tokens": 0}}
    {"event": "error", "message": "...", "exception_type": "..."}

Nothing else is written to standard output. A turn that raises prints one `error` line and exits 0:
`run` decides what the caller is told.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from loguru import logger
from nanobot.agent.hook import AgentHook

from nanobot import Nanobot

DIFF_MAX = 100_000
_FILE_TOOLS = ("write_file", "edit_file", "apply_patch")
_REASONING_EFFORTS = {"minimal": "low", "low": "low", "medium": "medium", "high": "high",
                      "xhigh": "xhigh", "max": "max", "none": "none", "adaptive": "adaptive"}


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def text_of(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return str(result)
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def read_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def display_path(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def render_diff(before: str | None, after: str | None) -> str:
    before_lines = (before or "").replace("\r\n", "\n").splitlines()
    after_lines = (after or "").replace("\r\n", "\n").splitlines()
    lines = [line for line in difflib.unified_diff(before_lines, after_lines, lineterm="", n=3)
             if not line.startswith(("--- ", "+++ "))]
    return "".join(line + "\n" for line in lines)[:DIFF_MAX]


def file_changes(name: str, arguments: dict[str, Any], before: dict[str, str | None],
                 workspace: Path) -> list[dict[str, Any]]:
    """The files a write went into, as path/action/diff, from what was there before and is there now."""
    if name == "write_file" or name == "edit_file":
        raw = [arguments.get("path")]
    elif name == "apply_patch":
        raw = [edit.get("path") for edit in arguments.get("edits") or [] if isinstance(edit, dict)]
    else:
        return []
    changes = []
    seen = set()
    for value in raw:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = workspace / path
        was, now = before.get(str(path)), read_text(path)
        if now is None and was is None:
            continue
        action = "create" if was is None else ("delete" if now is None else "update")
        changes.append({"path": display_path(path, workspace), "action": action,
                        "diff": render_diff(was, now)})
    return changes


def build_config(spec: dict[str, Any]) -> Path:
    """Write the instance config the turn's provider needs, into the mind, and return its path."""
    home = Path(os.environ["HOME"])
    config_path = home / ".nanobot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            config = {}
    except (OSError, ValueError):
        config = {}

    api = os.environ.get("HG_PROVIDER_API", "")
    if api == "anthropic":
        name = "anthropic"
        settings: dict[str, Any] = {"apiKey": "${HG_PROVIDER_KEY}", "apiBase": "${HG_PROVIDER_URL}"}
    else:
        request_api = {"openai-chat": "chat_completions", "openai-responses": "responses"}.get(api)
        if request_api is None:
            raise ValueError(f"nanobot cannot speak the {api!r} provider API")
        name = "custom"
        settings = {"apiKey": "${HG_PROVIDER_KEY}", "apiBase": "${HG_PROVIDER_URL}",
                    "api": {"supportedApis": [request_api]}}
    providers = config.setdefault("providers", {})
    providers[name] = {**(providers.get(name) or {}), **settings}

    preset: dict[str, Any] = {"provider": name, "model": "${HG_MODEL}"}
    if isinstance(spec.get("max_output_tokens"), int) and spec["max_output_tokens"] > 0:
        preset["maxTokens"] = spec["max_output_tokens"]
    if isinstance(spec.get("temperature"), (int, float)):
        preset["temperature"] = spec["temperature"]
    config.setdefault("modelPresets", {})["harness"] = preset

    agents = config.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    defaults["modelPreset"] = "harness"
    defaults["workspace"] = os.environ["HG_WORK"]
    effort = _REASONING_EFFORTS.get(str(spec.get("effort") or "").lower())
    if effort:
        defaults["reasoningEffort"] = effort
    else:
        defaults.pop("reasoningEffort", None)         # a previous turn's effort is not this turn's

    servers = {}
    for server in spec.get("mcp_servers") or []:
        label, url = server.get("label"), server.get("url")
        if not label or not url:
            continue
        entry: dict[str, Any] = {"url": url, "enabledTools": server.get("allowed_tools") or ["*"]}
        if server.get("headers"):
            entry["headers"] = server["headers"]
        servers[label] = entry
    config.setdefault("tools", {})["mcpServers"] = servers     # exactly this request's servers

    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config_path


class EventHook(AgentHook):
    """Turn nanobot's agent hooks into JSON lines, with each tool's full result and file diffs."""

    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self.workspace = workspace
        self.before: dict[str, dict[str, str | None]] = {}
        self.changes: dict[str, list[dict[str, Any]]] = {}
        self.text_seen = False
        self.session = ""

    # The SDK asks a hook whether it wants the answer piece by piece; it does.
    def wants_streaming(self) -> bool:
        return True

    async def on_stream(self, context: Any, delta: str) -> None:
        if delta:
            self.text_seen = True
            emit({"event": "text", "text": delta})

    async def emit_reasoning(self, reasoning_content: str | None) -> None:
        if reasoning_content:
            emit({"event": "reasoning", "text": reasoning_content})

    def _paths(self, name: str, arguments: dict[str, Any]) -> list[Path]:
        if name == "write_file" or name == "edit_file":
            raw = [arguments.get("path")]
        elif name == "apply_patch":
            raw = [edit.get("path") for edit in arguments.get("edits") or [] if isinstance(edit, dict)]
        else:
            return []
        found = []
        for value in raw:
            if isinstance(value, str) and value:
                path = Path(value).expanduser()
                found.append(path if path.is_absolute() else self.workspace / path)
        return found

    async def before_execute_tool(self, context: Any, tool_call: Any, tool: Any, params: Any) -> None:
        if tool_call.name not in _FILE_TOOLS or not isinstance(params, dict):
            return
        self.before[str(tool_call.id)] = {
            str(path): read_text(path) for path in self._paths(tool_call.name, params)
        }

    async def after_execute_tool(self, context: Any, tool_call: Any, tool: Any, params: Any,
                                 result: Any) -> None:
        if tool_call.name not in _FILE_TOOLS or not isinstance(params, dict):
            return
        self.changes[str(tool_call.id)] = file_changes(
            tool_call.name, params, self.before.pop(str(tool_call.id), {}), self.workspace)

    async def on_tool_execution_event(self, context: Any) -> None:
        calls = list(context.tool_calls)
        if not context.tool_events:
            for call in calls:
                emit({"event": "tool", "phase": "start", "id": str(call.id), "name": call.name,
                      "arguments": call.arguments or {}})
            return
        for call, result, event in zip(calls, context.tool_results, context.tool_events, strict=False):
            key = str(call.id)
            ok = event.get("status") == "ok"
            emit({
                "event": "tool", "phase": "end", "id": key, "name": call.name,
                "arguments": call.arguments or {}, "ok": ok,
                "result": text_of(result),
                "error": None if ok else (text_of(result) or event.get("detail") or "tool failed"),
                "files": self.changes.pop(key, []),
            })
            self.before.pop(key, None)


def usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else lambda name, default=None: getattr(usage, name, default)
    return {
        "input_tokens": int(get("input_tokens", 0) or 0),
        "output_tokens": int(get("output_tokens", 0) or 0),
        "cached_tokens": int(get("cache_read_tokens", 0) or 0),
    }


async def turn(spec: dict[str, Any]) -> None:
    logger.remove()                       # standard error is the turn's log; nothing else belongs there
    config_path = build_config(spec)
    workspace = Path(os.environ["HG_WORK"]).resolve()
    key = str(spec.get("session_key") or f"cli:{uuid.uuid4().hex[:12]}")
    channel, _, chat_id = key.partition(":")
    emit({"event": "session", "session": key})

    hook = EventHook(workspace)
    async with Nanobot.from_config(config_path=config_path, workspace=workspace) as bot:
        result = await bot.run(
            str(spec.get("prompt") or ""),
            session_key=key,
            channel=channel or "cli",
            chat_id=chat_id or "direct",
            hooks=[hook],
        )
    usage = usage_dict(result.usage)
    if not hook.text_seen and result.content:
        emit({"event": "text", "text": result.content})
    emit({"event": "done", "content": result.content or "", "stop_reason": result.stop_reason or "completed",
          "error": result.error, "usage": usage})


def main() -> int:
    raw = sys.stdin.read()
    try:
        spec = json.loads(raw) if raw.strip() else {}
        if not isinstance(spec, dict):
            raise ValueError("the turn's spec must be a JSON object")
    except ValueError as exc:
        emit({"event": "error", "message": f"the turn's spec could not be read: {exc}",
              "exception_type": "ValueError"})
        return 0
    try:
        asyncio.run(turn(spec))
    except Exception as exc:                                  # the turn failed; run says so
        emit({"event": "error", "message": str(exc) or type(exc).__name__,
              "exception_type": type(exc).__name__})
    return 0


if __name__ == "__main__":
    sys.exit(main())
