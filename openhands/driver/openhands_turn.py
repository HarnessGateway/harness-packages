#!/usr/bin/env python3
"""One headless turn of the OpenHands Software Agent SDK.

The SDK is a library, not a command-line program. This driver is the package's headless entry point: it
builds the SDK's own default CLI agent, runs one turn in the work folder, and prints one JSON object per
line on standard output for `run` to translate into Responses events.

Nothing else may reach standard output: everything the SDK and its libraries print is sent to standard
error, which is the turn's log.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import os
import re
import sys
import uuid

PROTOCOL = None


def emit(**line):
    """One protocol line, for `run` and no one else."""
    assert PROTOCOL is not None
    PROTOCOL.write(json.dumps(line, ensure_ascii=False) + "\n")
    PROTOCOL.flush()


def keep_stdout_clean():
    """Save the real standard output for the protocol, then point standard output at standard error."""
    global PROTOCOL
    duplicate = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    PROTOCOL = os.fdopen(duplicate, "w", buffering=1, encoding="utf-8")


def as_text(value):
    return value if isinstance(value, str) else ("" if value is None else str(value))


def safe_code(value):
    code = re.sub(r"[^a-z0-9_]+", "_", as_text(value).lower()).strip("_")
    return code[:60] or "error"


def unified(old, new):
    """The changed lines between two file contents, in apply_patch's -/+ form."""
    lines = []
    for line in difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(), n=0, lineterm=""):
        if line.startswith(("---", "+++", "@@")):
            continue
        lines.append(line)
    return "".join(line + "\n" for line in lines)


def added(text):
    return "".join("+" + line + "\n" for line in (text or "").splitlines())


class Translator:
    """The SDK's events in, the package's protocol out."""

    def __init__(self):
        # Imported here: the imports are the SDK's, which must come after standard output is redirected.
        from openhands.sdk.event import ActionEvent, MessageEvent, ObservationBaseEvent, UserRejectObservation
        from openhands.sdk.event.conversation_error import ConversationErrorEvent
        from openhands.sdk.llm import TextContent
        from openhands.sdk.mcp.definition import MCPToolAction
        from openhands.tools.file_editor.definition import FileEditorObservation
        from openhands.tools.terminal.definition import TerminalObservation

        self.ActionEvent = ActionEvent
        self.MessageEvent = MessageEvent
        self.ObservationBaseEvent = ObservationBaseEvent
        self.UserRejectObservation = UserRejectObservation
        self.ConversationErrorEvent = ConversationErrorEvent
        self.TextContent = TextContent
        self.MCPToolAction = MCPToolAction
        self.FileEditorObservation = FileEditorObservation
        self.TerminalObservation = TerminalObservation
        self.pending = {}          # tool_call_id -> ActionEvent, until its result arrives
        self.errors = []           # ConversationErrorEvent, newest last
        self.servers = []          # the request's MCP server labels, for splitting a tool name

    # ── reading the SDK's events ────────────────────────────────────────────────────────────────────────

    def on_event(self, event):
        if isinstance(event, self.MessageEvent):
            self.message(event)
        elif isinstance(event, self.ActionEvent):
            self.action(event)
        elif isinstance(event, self.ConversationErrorEvent):
            self.errors.append(event)
            emit(type="log", text=f"OpenHands error {event.code}: {event.detail}")
        elif isinstance(event, self.UserRejectObservation):
            previous = self.pending.pop(event.tool_call_id, None)
            if previous is not None:
                self.observation(previous, event, error=f"Action rejected: {event.rejection_reason}")
        elif isinstance(event, self.ObservationBaseEvent):
            previous = self.pending.pop(event.tool_call_id, None)
            if previous is None:
                if event.tool_name not in ("finish", "think"):
                    emit(type="log", text=f"an observation for {event.tool_name} had no matching action")
                return
            if getattr(event, "error", None):
                self.observation(previous, event, error=event.error)
            else:
                self.observation(previous, event)

    def message(self, event):
        if event.source != "agent":
            return
        reasoning = as_text(getattr(event, "reasoning_content", ""))
        if reasoning.strip():
            emit(type="think", text=reasoning)
        text = "".join(
            part.text for part in event.llm_message.content if isinstance(part, self.TextContent)
        )
        if text.strip():
            emit(type="say", text=text)

    def action(self, event):
        reasoning = as_text(getattr(event, "reasoning_content", ""))
        thought = " ".join(part.text for part in (event.thought or []) if isinstance(part, self.TextContent))
        if reasoning.strip():
            emit(type="think", text=reasoning)
        if thought.strip() and thought != reasoning:
            emit(type="think", text=thought)

        name = event.tool_name
        action = event.action
        if name == "finish":
            answer = as_text(getattr(action, "message", ""))
            if answer.strip():
                emit(type="say", text=answer)
            return
        if name == "think":
            logged = as_text(getattr(action, "thought", ""))
            if logged.strip():
                emit(type="think", text=logged)
            return
        self.pending[event.tool_call_id] = event

    def arguments(self, action_event):
        action = action_event.action
        if action is None:
            try:
                return json.loads(action_event.tool_call.arguments or "{}")
            except ValueError:
                return {"input": action_event.tool_call.arguments}
        if isinstance(action, self.MCPToolAction):
            return getattr(action, "data", None) or {}
        try:
            return action.model_dump(exclude_none=True)
        except Exception:
            return {}

    def observation(self, action_event, event, error=None):
        name = action_event.tool_name
        action = action_event.action
        given = self.arguments(action_event)
        observation = getattr(event, "observation", event)
        output = as_text(getattr(observation, "text", "")) if hasattr(observation, "text") else ""

        if name == "terminal":
            command = as_text(getattr(action, "command", given.get("command", "")))
            if error is None and isinstance(observation, self.TerminalObservation):
                exit_code = observation.exit_code
                if exit_code is None:
                    exit_code = getattr(observation.metadata, "exit_code", 0)
                emit(type="ran", command=command, stdout=output, stderr="",
                     exit_code=int(exit_code if exit_code is not None else 0))
            else:
                emit(type="ran", command=command, stdout="", stderr=error or output, exit_code=1)
            return

        if name == "file_editor":
            command = as_text(getattr(action, "command", ""))
            path = as_text(getattr(action, "path", ""))
            if error is not None or command == "view":
                emit(type="used", name="file_editor", input=json.dumps(given, ensure_ascii=False),
                     output=error or output)
            elif command == "create":
                content = as_text(getattr(action, "file_text", None))
                if not content and isinstance(observation, self.FileEditorObservation):
                    content = as_text(observation.new_content)
                emit(type="wrote", path=path, diff=added(content))
            else:
                old = getattr(observation, "old_content", None)
                new = getattr(observation, "new_content", None)
                emit(type="edited", path=path, diff=unified(old, new))
            return

        if isinstance(action, self.MCPToolAction):
            server, tool = self.split_mcp(name)
            emit(type="called", server=server, tool=tool, arguments=given,
                 output=None if error else output, error=error)
            return

        emit(type="used", name=name, input=json.dumps(given, ensure_ascii=False), output=error or output)

    def split_mcp(self, name):
        if len(self.servers) == 1:
            return self.servers[0], name
        for server in sorted(self.servers, key=len, reverse=True):
            if name.startswith(server + "_"):
                return server, name[len(server) + 1:]
        return "", name


def patch_anthropic_tools():
    """Omit Anthropic's newer `type: custom` marker on tool definitions.

    LiteLLM adds it to every function tool. Anthropic-compatible endpoints (DeepSeek's, among others)
    only accept the traditional tool shape, which has no `type` field. Removing the marker restores
    that shape: `name`, `description`, `input_schema`.
    """
    from litellm.llms.anthropic.chat.transformation import AnthropicConfig

    original = AnthropicConfig._map_tool_helper

    def without_custom_type(self, tool):
        mapped, mcp = original(self, tool)
        if isinstance(mapped, dict) and mapped.get("type") == "custom":
            mapped = dict(mapped)
            mapped.pop("type", None)
        return mapped, mcp

    AnthropicConfig._map_tool_helper = without_custom_type


def build_llm(body):
    from openhands.sdk import LLM
    from pydantic import SecretStr

    api = os.environ.get("HG_PROVIDER_API", "")
    prefix = {"anthropic": "anthropic", "openai-chat": "openai",
              "openai-responses": "openai", "gemini": "gemini"}.get(api, "openai")
    options = {
        "model": f"{prefix}/{os.environ['HG_MODEL']}",
        "api_key": SecretStr(os.environ["HG_PROVIDER_KEY"]),
        "base_url": os.environ.get("HG_PROVIDER_URL") or None,
        "usage_id": "agent",
        "stream": True,
        "drop_params": True,
    }
    if api == "openai-chat":
        options["api_mode"] = "chat"
    elif api == "openai-responses":
        options["api_mode"] = "responses"

    effort = body.get("reasoning", {}).get("effort") if isinstance(body.get("reasoning"), dict) else None
    if effort:
        options["reasoning_effort"] = effort
    else:
        # The SDK defaults to "high"; do not invent an effort the caller did not send.
        options["reasoning_effort"] = None
    for field in ("max_output_tokens", "temperature", "top_p"):
        if isinstance(body.get(field), (int, float)):
            options[field] = body[field]
    if body.get("text") is not None:
        emit(type="log", text="this package cannot enforce the request's text.format; the model is asked freely")
    return LLM(**options)


def build_mcp(body):
    from openhands.sdk.mcp.config import MCPServer
    from pydantic import SecretStr

    servers = {}
    for tool in body.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "mcp":
            continue
        label = tool.get("server_label")
        url = tool.get("server_url")
        if not label or not url:
            continue
        headers = tool.get("headers") or {}
        servers[label] = MCPServer(
            url=url,
            headers={name: SecretStr(as_text(value)) for name, value in headers.items()} or None,
        )
    return servers


def usage_now(conversation):
    try:
        usage = conversation.state.stats.get_combined_metrics().accumulated_token_usage
    except Exception:
        return (0, 0, 0)
    if usage is None:
        return (0, 0, 0)
    return (usage.prompt_tokens, usage.completion_tokens, usage.cache_read_tokens)


def usage_delta(before, after):
    prompt = max(0, after[0] - before[0])
    completion = max(0, after[1] - before[1])
    cached = min(max(0, after[2] - before[2]), prompt)
    if not (prompt or completion):
        return None
    return {
        "input_tokens": prompt,
        "output_tokens": completion,
        "input_tokens_details": {"cached_tokens": cached},
    }


def main():
    keep_stdout_clean()
    os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
    os.environ.setdefault("LOG_LEVEL", "WARNING")

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--session")
    arguments, _ = parser.parse_known_args()

    prompt = sys.stdin.read()

    from openhands.sdk import Conversation
    from openhands.sdk.conversation.exceptions import ConversationRunError
    from openhands.tools.preset.default import get_default_agent

    with open(os.path.join(os.environ["HG_TURN"], "request.json"), encoding="utf-8") as file:
        body = json.load(file)

    translator = Translator()
    if os.environ.get("HG_PROVIDER_API") == "anthropic":
        patch_anthropic_tools()
    llm = build_llm(body)
    mcp = build_mcp(body)
    translator.servers = list(mcp)
    persistence = os.path.join(os.environ["HG_MIND"], ".openhands", "conversations")

    def make(session_id, resume):
        common = {
            "workspace": os.environ["HG_WORK"],
            "persistence_dir": persistence,
            "conversation_id": uuid.UUID(session_id),
            "callbacks": [translator.on_event],
            "visualizer": None,
        }
        if resume:
            # The persisted agent is resumed as it was recorded; this request's MCP servers replace its
            # configuration. Its LLM is replaced after the conversation has registered its sessions, so
            # that this turn's tokens are counted in the same place as the earlier turns'.
            conversation = Conversation(agent=None, **common)
            conversation.agent = conversation.agent.model_copy(update={"mcp_config": mcp})
            with conversation.state:
                conversation.state.agent = conversation.agent
            return conversation
        agent = get_default_agent(llm=llm, cli_mode=True).model_copy(update={"mcp_config": mcp})
        return Conversation(agent=agent, **common)

    session = arguments.session
    resumed = bool(session)
    if not session:
        session = str(uuid.uuid4())
    try:
        conversation = make(session, resumed)
    except Exception as exc:
        if not resumed:
            emit(type="failed", code=safe_code(type(exc).__name__), message=as_text(exc)[:2000])
            return
        emit(type="log", text=f"OpenHands could not resume session {session}: {exc}; starting a new one")
        session, resumed = str(uuid.uuid4()), False
        try:
            conversation = make(session, False)
        except Exception as again:
            emit(type="failed", code=safe_code(type(again).__name__), message=as_text(again)[:2000])
            return

    # Save the session the moment it exists: a stopped turn must still be continued.
    emit(type="session", id=session, resumed=resumed)

    usage, failed = None, None
    try:
        conversation.send_message(prompt)
        if resumed:
            # After initialization the registry has a subscriber, so the swap is also what attaches this
            # turn's LLM (and its condenser) to the conversation's persisted metrics.
            conversation.switch_llm(llm)
        before = usage_now(conversation)
        try:
            conversation.run()
        except ConversationRunError as exc:
            failed = exc
        except Exception as exc:
            failed = exc
        status = conversation.state.execution_status
        usage = usage_delta(before, usage_now(conversation))
        if failed is None and as_text(getattr(status, "value", status)) == "error":
            failed = RuntimeError("OpenHands ended in an error state")
    finally:
        with contextlib.suppress(Exception):
            conversation.close()

    if failed is not None:
        detail = getattr(failed, "conversation_error", None)
        if detail is None and translator.errors:
            detail = translator.errors[-1]
        code = safe_code(getattr(detail, "code", None) or type(failed).__name__)
        message = as_text(getattr(detail, "detail", None) or str(failed))[:2000]
        emit(type="failed", code=code, message=message or "OpenHands failed without a message", usage=usage)
        return

    status_name = as_text(getattr(status, "value", status))
    if status_name == "stuck":
        emit(type="failed", code="stuck", message="OpenHands stopped: it detected it was stuck in a loop.",
             usage=usage)
        return
    emit(type="done", usage=usage)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit(type="failed", code=safe_code(type(exc).__name__), message=as_text(exc)[:2000] or "OpenHands failed")
