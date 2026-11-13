# What `run` prints

One JSON object per line on standard output. The platform checks every line as it arrives, against the
OpenAI SDK's own type for that event, and fails the turn with `invalid_output` on the first bad one. The
kit's `hgkit.Emitter` prints all of these correctly; the raw lines are shown for a `run` in another
language, and so you know what the caller receives.

## With the kit

```python
emit = hgkit.Emitter()
emit.think("Looking at the tests")                       # a piece of reasoning
emit.say("Running them.")                                # a piece of the answer
emit.ran("pytest -q", stdout="3 passed\n", exit_code=0)  # a command, and how it ended (stderr= too)
emit.wrote("hello.py", "+print(1)\n")                    # a file created; the second argument is a diff
emit.edited("app.py", "-old line\n+new line\n")          # a file changed
emit.deleted("tmp.txt")                                  # a file removed
emit.called("github", "get_issue", {"n": 1}, output="…") # a tool of an MCP server (error="…" when it failed)
emit.used("WebSearch", '{"q": "x"}', "…")                # any other tool: its name, what it was given, what came back
emit.log("the CLI said: …")                              # the turn's log; the caller never sees it
emit.done(usage)                                         # exactly one of these three, last
emit.incomplete("max_output_tokens", usage)
emit.failed("provider_error", "The provider answered 429: rate limited.", usage)
```

Pieces of text arrive one after another and are gathered into one message; the same for reasoning. The item
ends when something of another kind is printed, or the turn ends. Everything else is printed whole, when it
is over: a CLI reports a tool's call and its result separately, so keep the call until its result arrives
(`/harness/run` keeps them by the CLI's own call id) and print both together.

Nothing can be printed after the terminal line: the kit raises.

## What each thing the agent does becomes

| The agent | Kit | Output items |
|---|---|---|
| answers | `emit.say` | one `message` with one `output_text` part, streamed |
| reasons | `emit.think` | one `reasoning` item with one `summary_text`, streamed |
| runs a command | `emit.ran` | `shell_call`, then `shell_call_output` with stdout, stderr and the exit code |
| creates, changes, removes a file | `emit.wrote`, `emit.edited`, `emit.deleted` | `apply_patch_call` (`create_file`, `update_file`, `delete_file`), then `apply_patch_call_output` |
| calls a tool of an MCP server | `emit.called` | one `mcp_call` |
| uses any other tool (search, fetch, a sub-agent, a to-do list) | `emit.used` | `custom_tool_call`, then `custom_tool_call_output` |

Use the most specific row. A CLI's own "bash" tool is `emit.ran`, not `emit.used`; its file tools are
`emit.wrote` and `emit.edited`. A tool that failed still happened: print it, with what it said.

What a CLI prints that is none of these (its banner, progress, its own bookkeeping) goes to `emit.log`, or
nowhere. A line of the CLI's that is not what you expected goes to `emit.log` too: never guess.

## The end of a turn

| | When | Kit |
|---|---|---|
| `hg.done` | The CLI finished its work | `emit.done(usage)` |
| `hg.incomplete` | It stopped short. `reason` is `max_output_tokens` or `content_filter`, nothing else. | `emit.incomplete(reason, usage)` |
| `hg.failed` | The CLI or the provider failed. `code` is a short lower-case name (letters, digits, `_`); `message` tells a person what went wrong and is never empty. | `emit.failed(code, message, usage)` |

`usage` is optional, in the shape of the Responses `usage` object. Give what the CLI reports:

```python
usage = {"input_tokens": 1200, "output_tokens": 340, "input_tokens_details": {"cached_tokens": 800}}
```

`input_tokens` counts all input, cached included: a CLI on the Anthropic API reports cache reads and cache
writes separately, so add them in. `total_tokens` and the details left out are filled in by the platform.

Always end with a terminal line. A CLI that exits without saying how it ended is `emit.failed("cli_exit", …)`
with its exit code in the message. `run` itself exits 0 whenever it printed a terminal line.

A turn that was stopped prints no terminal line: `run` is ending, and what it printed so far is kept.

## The raw lines

This is a whole turn: the agent says "Hello", runs a command, and finishes. Ids are the package's own: any
strings, each used once.

```jsonl
{"type": "response.output_item.added", "output_index": 0, "item": {"id": "msg_0001", "type": "message", "role": "assistant", "status": "in_progress", "content": []}}
{"type": "response.content_part.added", "item_id": "msg_0001", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}}
{"type": "response.output_text.delta", "item_id": "msg_0001", "output_index": 0, "content_index": 0, "delta": "Hel", "logprobs": []}
{"type": "response.output_text.delta", "item_id": "msg_0001", "output_index": 0, "content_index": 0, "delta": "lo", "logprobs": []}
{"type": "response.output_text.done", "item_id": "msg_0001", "output_index": 0, "content_index": 0, "text": "Hello", "logprobs": []}
{"type": "response.content_part.done", "item_id": "msg_0001", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "Hello", "annotations": []}}
{"type": "response.output_item.done", "output_index": 0, "item": {"id": "msg_0001", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "Hello", "annotations": []}]}}
{"type": "response.output_item.added", "output_index": 1, "item": {"id": "sh_0002", "type": "shell_call", "call_id": "call_0002", "status": "completed", "action": {"commands": ["pytest -q"]}}}
{"type": "response.output_item.done", "output_index": 1, "item": {"id": "sh_0002", "type": "shell_call", "call_id": "call_0002", "status": "completed", "action": {"commands": ["pytest -q"]}}}
{"type": "response.output_item.added", "output_index": 2, "item": {"id": "sho_0002", "type": "shell_call_output", "call_id": "call_0002", "status": "completed", "output": [{"stdout": "3 passed\n", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}}]}}
{"type": "response.output_item.done", "output_index": 2, "item": {"id": "sho_0002", "type": "shell_call_output", "call_id": "call_0002", "status": "completed", "output": [{"stdout": "3 passed\n", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}}]}}
{"type": "hg.log", "text": "the CLI's session is 7f3a"}
{"type": "hg.done", "usage": {"input_tokens": 1200, "output_tokens": 340, "input_tokens_details": {"cached_tokens": 800}}}
```

The other items, each printed as `response.output_item.added` and then `response.output_item.done` with
the next `output_index`:

```jsonl
{"type": "response.output_item.done", "output_index": 3, "item": {"id": "rs_0003", "type": "reasoning", "summary": [{"type": "summary_text", "text": "Looking at the tests"}]}}
{"type": "response.output_item.done", "output_index": 4, "item": {"id": "ap_0004", "type": "apply_patch_call", "call_id": "call_0004", "status": "completed", "operation": {"type": "create_file", "path": "hello.py", "diff": "+print(1)\n"}}}
{"type": "response.output_item.done", "output_index": 5, "item": {"id": "apo_0004", "type": "apply_patch_call_output", "call_id": "call_0004", "status": "completed"}}
{"type": "response.output_item.done", "output_index": 6, "item": {"id": "mcp_0005", "type": "mcp_call", "server_label": "github", "name": "get_issue", "arguments": "{\"n\": 1}", "output": "…", "status": "completed"}}
{"type": "response.output_item.done", "output_index": 7, "item": {"id": "ctc_0006", "type": "custom_tool_call", "call_id": "call_0006", "name": "WebSearch", "input": "{\"q\": \"x\"}"}}
{"type": "response.output_item.done", "output_index": 8, "item": {"id": "ctco_0006", "type": "custom_tool_call_output", "call_id": "call_0006", "status": "completed", "output": "…"}}
{"type": "hg.incomplete", "reason": "max_output_tokens"}
```

Reasoning streams as a message does, with `response.reasoning_summary_part.added`,
`response.reasoning_summary_text.delta`, `response.reasoning_summary_text.done` and
`response.reasoning_summary_part.done`, each carrying `summary_index` in place of `content_index`.

The items of the `response.output_item.done` lines, in order, become the response's `output`.

## What the platform refuses

- a line that is not a JSON object with a `type`, or is longer than 16 MiB;
- an event the Responses stream does not have, or one with a field missing or of the wrong type (a text
  delta without `logprobs`, an item without its `id`);
- `response.created`, `response.completed`, `response.failed`, `response.incomplete` or `error`: the platform
  writes those;
- `hg.log` with anything but `text`; a terminal line with a field it does not have;
- no terminal line although `run` exited 0, or `run` exiting with another code.

`/harness/tools/platform/bin/harnessgateway package check <folder>` makes the same checks on every recorded
case and names the line and the field.
