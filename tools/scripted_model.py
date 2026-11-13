#!/usr/bin/env python3
"""A model that follows a script, behind the three provider APIs the shipped harnesses speak.

It stands in for a provider so that a real CLI can be run end to end, and its real output recorded, without
a provider, a key that costs money, or an answer that changes from run to run. Standard library only.

    python3 scripted_model.py [port]           (default 8000)

    Anthropic Messages      POST /anthropic/v1/messages
    OpenAI Responses        POST /v1/responses
    OpenAI Chat Completions POST /v1/chat/completions

The script, applied to whatever conversation it is sent:

    - The newest thing the user said contains "RUN: <command>", and no tool result has come back since:
      it calls the shell tool the CLI offered, with that command.
    - A tool result has come back since: it answers "The command printed: <the result>".
    - Otherwise it answers "[turn N] You said: <what the user said>", where N counts what the user has said in
      this conversation. So N shows whether the CLI resumed its own session.

Every request must carry the key `scripted-model-key`; anything else is answered 401, which is how a test
knows the platform put the real key in. `GET /log` returns the requests it has been sent.
"""

import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "scripted-model-key"
SHELL_TOOLS = ("bash", "shell", "terminal", "exec_command", "shell_command", "local_shell", "run_shell_command",
               "execute_command", "container.exec")
LOG = []


def _text_of(content):
    """The text in a message's content, whatever shape the dialect gives it."""
    if isinstance(content, str):
        return content
    texts = []
    for part in content or []:
        if isinstance(part, dict) and part.get("type") in ("text", "input_text", "output_text"):
            texts.append(part.get("text", ""))
    return "\n".join(texts)


def _result_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_result_text(part.get("text", part.get("output", ""))) if isinstance(part, dict) else str(part)
                         for part in value)
    return json.dumps(value)


class Conversation:
    """What the script needs to know of a conversation: what the user said, and what a tool said since."""

    def __init__(self):
        self.said = []                 # each thing the user said, in order
        self.result = None             # the newest tool result after the newest thing the user said

    def user(self, text):
        text = text.strip()
        if text:
            self.said.append(text)
            self.result = None

    def tool(self, text):
        self.result = text

    def decide(self):
        """("call", command) or ("say", text)."""
        newest = self.said[-1] if self.said else ""
        if self.result is not None:
            return "say", f"The command printed: {self.result.strip()[:500]}"
        if "RUN:" in newest:
            return "call", newest.split("RUN:", 1)[1].strip().splitlines()[0]
        return "say", f"[turn {len(self.said)}] You said: {newest[-500:]}"


def _arguments(schema, command):
    """Arguments for a shell tool, shaped to the schema the CLI declared for it."""
    properties = (schema or {}).get("properties", {})
    for name in ("command", "cmd", "script", "commands"):
        if name in properties:
            wants_list = properties[name].get("type") == "array"
            return {name: ["bash", "-lc", command] if wants_list else command}
    return {"command": command}


def _shell_tool(tools, name_of, schema_of):
    for tool in tools or []:
        name = name_of(tool)
        if name and name.lower() in SHELL_TOOLS:
            return name, schema_of(tool)
    return None, None


# ── Anthropic Messages ─────────────────────────────────────────────────────────────────────────────────────

def anthropic(body):
    conversation = Conversation()
    for message in body.get("messages", []):
        content = message.get("content")
        if message.get("role") != "user":
            continue
        parts = content if isinstance(content, list) else [{"type": "text", "text": content}]
        results = [part for part in parts if isinstance(part, dict) and part.get("type") == "tool_result"]
        if results:
            conversation.tool(_result_text(results[-1].get("content")))
        else:
            texts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text"]
            real = [text for text in texts if not text.lstrip().startswith("<")]     # not the CLI's own reminders
            conversation.user(real[-1] if real else "")
    kind, value = conversation.decide()
    name, schema = _shell_tool(body.get("tools"), lambda t: t.get("name"), lambda t: t.get("input_schema"))
    message_id, model = f"msg_{uuid.uuid4().hex[:24]}", body.get("model", "scripted")
    usage = {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    if kind == "call" and name:
        block = {"type": "tool_use", "id": f"toolu_{uuid.uuid4().hex[:24]}", "name": name,
                 "input": _arguments(schema, value)}
        stop = "tool_use"
    else:
        block = {"type": "text", "text": value if kind == "say" else f"(no shell tool was offered to run: {value})"}
        stop = "end_turn"
    message = {"id": message_id, "type": "message", "role": "assistant", "model": model, "content": [block],
               "stop_reason": stop, "stop_sequence": None, "usage": usage}
    if not body.get("stream"):
        return "json", message

    def events():
        yield "message_start", {"type": "message_start", "message": {**message, "content": [], "stop_reason": None,
                                                                    "usage": {**usage, "output_tokens": 1}}}
        if block["type"] == "text":
            yield "content_block_start", {"type": "content_block_start", "index": 0,
                                          "content_block": {"type": "text", "text": ""}}
            for piece in _pieces(block["text"]):
                yield "content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": piece}}
        else:
            yield "content_block_start", {"type": "content_block_start", "index": 0,
                                          "content_block": {**block, "input": {}}}
            yield "content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {
                "type": "input_json_delta", "partial_json": json.dumps(block["input"])}}
        yield "content_block_stop", {"type": "content_block_stop", "index": 0}
        yield "message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                "usage": {"output_tokens": 20}}
        yield "message_stop", {"type": "message_stop"}
    return "sse", [(name, data) for name, data in events()]


# ── OpenAI Responses ───────────────────────────────────────────────────────────────────────────────────────

def responses(body):
    conversation = Conversation()
    given = body.get("input")
    for item in given if isinstance(given, list) else [{"type": "message", "role": "user", "content": given}]:
        kind = item.get("type", "message")
        if kind == "message" and item.get("role") == "user":
            text = _text_of(item.get("content"))
            if not text.lstrip().startswith("<"):                                  # not the CLI's own context
                conversation.user(text)
        elif kind.endswith("_call_output"):
            conversation.tool(_result_text(item.get("output")))
    kind, value = conversation.decide()
    tools = body.get("tools") or []
    name, schema = _shell_tool(tools, lambda t: t.get("name") if t.get("type") == "function" else None,
                               lambda t: t.get("parameters"))
    native = next((t for t in tools if t.get("type") in ("local_shell", "shell")), None)
    response_id, model = f"resp_{uuid.uuid4().hex[:24]}", body.get("model", "scripted")
    if kind == "call" and name:
        item = {"type": "function_call", "id": f"fc_{uuid.uuid4().hex[:24]}",
                "call_id": f"call_{uuid.uuid4().hex[:24]}", "name": name,
                "arguments": json.dumps(_arguments(schema, value)), "status": "completed"}
    elif kind == "call" and native and native["type"] == "local_shell":
        item = {"type": "local_shell_call", "id": f"lsh_{uuid.uuid4().hex[:24]}",
                "call_id": f"call_{uuid.uuid4().hex[:24]}", "status": "completed",
                "action": {"type": "exec", "command": ["bash", "-lc", value], "env": {}}}
    else:
        text = value if kind == "say" else f"(no shell tool was offered to run: {value})"
        item = {"type": "message", "id": f"msg_{uuid.uuid4().hex[:24]}", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}]}
    usage = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 20,
             "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 120}
    response = {"id": response_id, "object": "response", "created_at": int(time.time()), "status": "completed",
                "model": model, "output": [item], "usage": usage, "error": None, "incomplete_details": None,
                "instructions": None, "metadata": {}, "parallel_tool_calls": True, "tool_choice": "auto", "tools": []}
    if not body.get("stream"):
        return "json", response

    def events():
        started = {**response, "status": "in_progress", "output": [], "usage": None}
        yield "response.created", {"type": "response.created", "response": started}
        yield "response.in_progress", {"type": "response.in_progress", "response": started}
        if item["type"] == "message":
            text = item["content"][0]["text"]
            yield "response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": {
                **item, "status": "in_progress", "content": []}}
            yield "response.content_part.added", {
                "type": "response.content_part.added", "item_id": item["id"], "output_index": 0, "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []}}
            for piece in _pieces(text):
                yield "response.output_text.delta", {
                    "type": "response.output_text.delta", "item_id": item["id"], "output_index": 0,
                    "content_index": 0, "delta": piece}
            yield "response.output_text.done", {"type": "response.output_text.done", "item_id": item["id"],
                                                "output_index": 0, "content_index": 0, "text": text}
            yield "response.content_part.done", {
                "type": "response.content_part.done", "item_id": item["id"], "output_index": 0, "content_index": 0,
                "part": item["content"][0]}
        else:
            yield "response.output_item.added", {"type": "response.output_item.added", "output_index": 0,
                                                 "item": {**item, "status": "in_progress"}}
        yield "response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}
        yield "response.completed", {"type": "response.completed", "response": response}
    numbered = [(name, {**data, "sequence_number": number}) for number, (name, data) in enumerate(events())]
    return "sse", numbered


# ── OpenAI Chat Completions ────────────────────────────────────────────────────────────────────────────────

def chat(body):
    conversation = Conversation()
    for message in body.get("messages", []):
        if message.get("role") == "user":
            conversation.user(_text_of(message.get("content")))
        elif message.get("role") == "tool":
            conversation.tool(_result_text(message.get("content")))
    kind, value = conversation.decide()
    name, schema = _shell_tool(body.get("tools"), lambda t: (t.get("function") or {}).get("name"),
                               lambda t: (t.get("function") or {}).get("parameters"))
    completion_id, model, created = f"chatcmpl-{uuid.uuid4().hex[:24]}", body.get("model", "scripted"), int(time.time())
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    if kind == "call" and name:
        call = {"id": f"call_{uuid.uuid4().hex[:24]}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(_arguments(schema, value))}}
        message, finish = {"role": "assistant", "content": None, "tool_calls": [call]}, "tool_calls"
    else:
        text = value if kind == "say" else f"(no shell tool was offered to run: {value})"
        message, finish = {"role": "assistant", "content": text}, "stop"
    if not body.get("stream"):
        return "json", {"id": completion_id, "object": "chat.completion", "created": created, "model": model,
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage}

    def chunk(delta, finish_reason=None, **more):
        return {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}], **more}

    def events():
        yield chunk({"role": "assistant", "content": ""})
        if finish == "tool_calls":
            yield chunk({"tool_calls": [{"index": 0, **message["tool_calls"][0]}]})
        else:
            for piece in _pieces(message["content"]):
                yield chunk({"content": piece})
        yield chunk({}, finish)
        yield {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
               "choices": [], "usage": usage}
    return "sse", [(None, data) for data in events()] + [(None, "[DONE]")]


def _pieces(text, size=12):
    return [text[at:at + size] for at in range(0, len(text), size)] or [""]


ROUTES = {"/anthropic/v1/messages": anthropic, "/v1/messages": anthropic, "/v1/responses": responses,
          "/v1/chat/completions": chat}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        given = self.headers.get("x-api-key") or self.headers.get("authorization", "").removeprefix("Bearer ").strip()
        return given == KEY

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/log":
            return self._send(200, LOG)
        if path == "/healthz":
            return self._send(200, {"status": "ok"})
        if path.endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": "scripted", "object": "model", "created": 0,
                                                                "owned_by": "scripted-model"}]})
        self._send(404, {"error": {"message": f"no such path: {path}", "type": "not_found"}})

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("content-length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"error": {"message": "the body is not JSON", "type": "invalid_request_error"}})
        LOG.append({"path": path, "authorized": self._authorized(), "body": body})
        del LOG[:-200]
        if not self._authorized():
            return self._send(401, {"type": "error", "error": {
                "type": "authentication_error", "message": "the scripted model was not sent its key"}})
        if path.endswith("/count_tokens"):
            return self._send(200, {"input_tokens": 100})
        route = ROUTES.get(path)
        if route is None:
            return self._send(404, {"error": {"message": f"no such path: {path}", "type": "not_found"}})
        kind, answer = route(body)
        if kind == "json":
            return self._send(200, answer)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for name, data in answer:
            text = data if isinstance(data, str) else json.dumps(data)
            self.wfile.write(((f"event: {name}\n" if name else "") + f"data: {text}\n\n").encode())
            self.wfile.flush()
            time.sleep(0.01)
        self.close_connection = True

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
