# qwen-code

Qwen Code — the `qwen` CLI from the npm package `@qwen-code/qwen-code` — as its makers ship it, run headless
by HarnessGateway in the sandbox. Nothing is added to the agent: its own built-in tools, sub-agents, skills,
extensions and MCP support are what it uses.

- CLI version: **0.28.0** (pinned in `install`; package revision 1)
- Binary: `$HG_HARNESS/tools/node_modules/.bin/qwen`
- Mind: `$HOME/.qwen`
- Provider APIs: Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, Gemini (in that order in the
  manifest; the platform picks the first the request's provider offers)
- Node.js 22 or later and Python 3 are needed. The platform's default image has both.

## What it needs

| | |
|---|---|
| Image | Node.js **22+**, `npm`, `python3` (the kit's `run`). Nothing else; no root, no native build. |
| Install network | `registry.npmjs.org` only — already one of the registries every install reaches. |
| Turn network | The provider's host. Nothing else, unless the request names an MCP server: that server's host must be allowed too. |
| Settings | None required. |
| Secrets | None. The provider key is the platform's placeholder, passed to the CLI as its key. |

`install` runs `npm install --prefix $HG_HARNESS/tools --ignore-scripts @qwen-code/qwen-code@0.28.0` and checks
`qwen --version`. Its platform binaries arrive as optional dependencies; npm chooses the build, so the install
names no CPU architecture. The package declares no install scripts.

## The command

```
qwen --auth-type <type> --model <HG_MODEL> --yolo \
     --output-format stream-json --include-partial-messages \
     [--append-system-prompt <instructions>] [--mcp-config <json>] [--json-schema <schema>] [--resume <id>]
```

The prompt, including the handover line, the request's files and the user's text, goes on standard input
(`request.brief(instructions=False)`). `instructions` is passed with `--append-system-prompt`. `--yolo`
auto-approves tools; the platform's sandbox, not Qwen Code's own sandbox, is the boundary.

The provider is set by the auth type's variables:

| `HG_PROVIDER_API` | `--auth-type` | Base URL | Key | Model |
|---|---|---|---|---|
| `anthropic` | `anthropic` | `ANTHROPIC_BASE_URL=HG_PROVIDER_URL` | `ANTHROPIC_API_KEY` | `--model`, `ANTHROPIC_MODEL` |
| `openai-chat` | `openai` | `OPENAI_BASE_URL=HG_PROVIDER_URL` | `OPENAI_API_KEY` | `--model`, `OPENAI_MODEL` |
| `openai-responses` | `openai-responses` | `OPENAI_BASE_URL=HG_PROVIDER_URL` | `OPENAI_API_KEY` | `--model`, `OPENAI_MODEL` |
| `gemini` | `gemini` | `GOOGLE_GEMINI_BASE_URL=HG_PROVIDER_URL` | `GEMINI_API_KEY` | `--model`, `GEMINI_MODEL` |

The key the CLI receives is the platform's placeholder; the proxy substitutes the real one on the way out.
Auto-update, telemetry, usage statistics (which also stops the models.dev catalogue refresh) and the managed
memory/dream/skill background jobs are off in `seeds/mind/.qwen/settings.json`. Chat recording stays on: it is
what makes `--resume` work.

## The request, field by field

| Request | What happens |
|---|---|
| `input` (string or messages) | `request.prompt`, through `request.brief()` on stdin. |
| `input_file`, `input_image`, files by id | Placed in `inputs/` in the work folder and named in the prompt. The CLI opens them with its own tools. |
| `instructions` | `--append-system-prompt`, so the built-in prompt and `QWEN.md` memory still load. |
| handover line | First in the prompt. |
| `history` | Not sent: the handover line tells the agent where the previous harness's work is. |
| `model` | `--model` (and the provider's `*_MODEL` variable). A resumed session takes the model of this request. |
| provider / key / base URL | The environment variables in the table above. |
| `reasoning.effort` | Written as `model.reasoningEffort` into `$HOME/.qwen/settings.json` for this turn (`low`, `medium`, `high`, `xhigh`, `max`; the CLI clamps what the model supports). The CLI has no flag for it. |
| `tools` of type `mcp` | Serialised with `--mcp-config`: each server becomes `{"httpUrl": <server_url>, "headers": …, "includeTools": <allowed_tools>, "trust": true}`. It must speak Streamable HTTP, including the GET event stream (Qwen Code opens one after `initialize`); SSE-only servers do not connect. Its host must be allowed by the environment. |
| `text.format` = `json_schema` | `--json-schema`, so the CLI's `structured_output` tool enforces the schema. |
| `text.format` = `json_object` or anything else | Not enforceable by the CLI; a `hg.log` line says so. |
| `previous_response_id` | The platform restores the session; the CLI continues its own session from `hgkit.State`. |
| `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`, `tool_choice`, `parallel_tool_calls`, `background`, `store` | No CLI option here; left unapplied. The CLI uses its model defaults. `stream` and `background` are the platform's. |

A tool of any type other than `mcp` never reaches the package.

## What is printed

Qwen Code's `--output-format stream-json` lines are translated as follows:

| Qwen Code | Responses output |
|---|---|
| `stream_event` `text_delta`, then the finished message | one `message`, streamed (the completed `assistant` line is not printed twice) |
| `stream_event` `thinking_delta`, then the finished message | one `reasoning` item, streamed |
| `run_shell_command` and its tool result | `shell_call` + `shell_call_output` with the exit code |
| `write_file` and its result | `apply_patch_call` `create_file` + output |
| `edit` and its result | `apply_patch_call` `update_file` + output |
| `tool_call` naming `mcp__<server>__<tool>` | `mcp_call` with arguments and output (or error) |
| any other tool (`read_file`, `grep_search`, `glob`, `web_fetch`, `tool_search`, `agent`, …) | `custom_tool_call` + `custom_tool_call_output` |
| `system`/`init` | its `session_id` is saved with `state.set`; nothing is printed |
| `result` with `subtype: success` | `hg.done`, with usage |
| `result` with any other subtype, or `is_error` | `hg.failed`, code is the subtype, message is the CLI's error |
| any line that is not JSON of a kind above | `hg.log` |

Qwen Code combines a command's stdout and stderr in one `Output:` block. When it reports that block,
`shell_call_output.stdout` carries it and `stderr` is empty; the exit code is taken from the `Exit Code:`
line. When the CLI only returns the command's text, that text is the stdout and a failed tool is exit code 1.

Usage is this turn's, not the session's: Qwen Code's `result.usage` is the running total across `--resume`,
so the package adds up the usage each assistant message reports and reports that. Cache reads are added to
`input_tokens` and also given as `input_tokens_details.cached_tokens`.

## The session

Qwen Code keeps sessions in `$HOME/.qwen/projects/<sanitized-cwd>/chats/<session-id>.jsonl`, so they come back
with the mind. The `session_id` from the `system`/`init` line (and from `result`) is saved with `state.set` the
moment it is seen — a stopped turn still leaves it. The next turn passes `--resume <id>`.

If that resume fails (the CLI exits non-zero without a result, e.g. after a stopped turn left the record
unusable), the package logs it, clears the saved id and runs the turn again as a new session.

## Hosts

Every host the install and the trial turns asked for, beyond the package registries and the provider:

| Host | Why | Needed? |
|---|---|---|
| (none) | The install asked only for `registry.npmjs.org`; every turn asked only for the provider's host. | — |

An MCP server named in a request is contacted at its `server_url`; that host must be allowed by the
environment for the turn (and is outside this package's control).

## What could not be tried here

- Only the **Anthropic** provider was exercised end to end (the builder session's provider). The OpenAI Chat,
  OpenAI Responses and Gemini routes are wired to Qwen Code's documented variables and the OpenAI paths and
  auth headers were checked against a local mock, but no real model was run through them.
- `text.format` → `--json-schema` was not exercised with a model that returns a structured result.
- MCP was tried with one local Streamable HTTP server (including its GET event stream), not with a hosted
  server, SSE-only servers, or OAuth-protected servers.
- Qwen Code's own sandbox (`--sandbox`) is not used; the platform sandbox is the boundary.

## Tests

`tests/` holds the turns replayed by `harnessgateway package check`:

| Case | What it shows |
|---|---|
| `hello` | text only, `hg.done` |
| `command` | `write_file` and `run_shell_command` with its output |
| `resumed` | a later turn continued by `--resume` |
| `failure` | a provider error (`no-such-model`): text, then `hg.failed` with the provider's message |
| `mcp` | a `tool_search` call and an MCP `mcp_call` against a local Streamable HTTP server |

The stop path was tried by hand: a counting turn stopped after 5 seconds printed no terminal line, and the
next turn continued the same session.
