# dcode — Deep Agents Code

Deep Agents Code is LangChain's terminal coding agent, built on the Deep Agents SDK. This package runs the
CLI its makers publish on PyPI (`deepagents-code`) as a headless agent, and translates its ACP (Agent Client
Protocol) event stream into OpenAI Responses events.

- **CLI version:** `deepagents-code` 0.2.10 (pinned; package revision 1).
- **Entry point:** `dcode`, installed by `uv tool install` in an isolated Python 3.14 environment under
  `$HG_HARNESS/tools`.
- **Mode used:** `dcode --acp`, the JSON-RPC server the CLI ships for editor integrations. Its plain
  `-n`/`--quiet` mode writes only the assistant's text to standard output and keeps tool activity on the
  human-facing console, so it cannot report files, commands or tools as Responses items.
- **Model APIs:** Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, and the Gemini API.

## What it needs

**Image.** `python3` (3.8 or later) with the `venv` module, for the uv bootstrap the install uses. The CLI
itself runs on Python 3.14; uv provisions a managed 3.14 when the image has none. No other package, Node.js or
system library is needed.

**Install network.** The install reaches `pypi.org` and `files.pythonhosted.org` (the uv wheel, then the CLI
and its dependencies). When the image has no Python 3.14 it also reaches `github.com` and
`release-assets.githubusercontent.com` for a python-build-standalone release. The CLI's own
`dcode tools install` runs at the end (best effort) and, when the image has no `rg`, fetches its pinned
ripgrep from the same GitHub release hosts. All four are in the platform's package-manager list; no
`setup.egress` entry is needed. Nothing else is contacted. In this build the image already had `/usr/bin/rg`,
so the trial's install reached only PyPI.

**Turn network.** The turn reaches its provider's host (through the platform's proxy) and nothing else of its
own. The provider's host is chosen by the environment, not by this package; the trial reached only
`api.deepseek.com`. See "Hosts" below for what the agent itself may reach.

**Provider.** Any provider in one of the four APIs above. The request names it and the model in `model`; the
package maps `HG_PROVIDER_API`, `HG_PROVIDER_URL`, `HG_PROVIDER_KEY` and `HG_MODEL` onto dcode's provider
settings:

| `HG_PROVIDER_API` | dcode model spec | Variables |
|---|---|---|
| `anthropic` | `anthropic:<model>` | `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY` |
| `openai-chat` | `openai:<model>` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `openai-responses` | `openai:<model>` plus `use_responses_api` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `gemini` | `google_genai:<model>` | `GOOGLE_GEMINI_BASE_URL`, `GOOGLE_API_KEY` |

The provider key is handed over exactly as the CLI's own key; it is a placeholder, and the platform's proxy
puts the real key in on the way to the provider.

## The command

```
dcode --acp --model <provider>:<model> --no-tracing --shell-allow-list all [--mcp-config <file>|--no-mcp]
```

with `--model-params '{"use_responses_api": true}'` for `openai-responses`. The run then speaks ACP over the
CLI's standard input and output: `initialize`, `session/new` or `session/load`, `session/prompt`. The CLI
starts with:

- `DEEPAGENTS_HOME=$HOME/.deepagents`, so the session store is always the mind folder the platform saves;
- `DEEPAGENTS_CODE_NO_UPDATE_CHECK=1`, `DEEPAGENTS_CODE_AUTO_UPDATE=0`, `DEEPAGENTS_CODE_OFFLINE=1` — no update
  check, no price refresh, no managed-tool download during a turn;
- `--no-tracing`, so nothing goes to LangSmith;
- `--shell-allow-list all`, so the coding agent can run commands. Tool calls that need approval are answered
  **approve** by the package: a headless turn has no human, and the CLI otherwise waits (this is the same
  effect as its `-n` mode, which also runs with no approvals).

## The request, field by field

| Request | What happens |
|---|---|
| `input` (string or messages) | The user's text is the ACP prompt. |
| `instructions` | Prefixed to the prompt (`request.brief()`); ACP has no system-prompt channel. |
| `input_file` / `input_image` parts | Placed in `inputs/` in the work folder and named in the prompt. Images are files the agent can read, not ACP image blocks. |
| the handover line | Prefixed to the prompt. |
| `model` | `--model <provider>:<HG_MODEL>`. |
| the provider | Environment variables, and the base URL above. |
| `reasoning.effort` | **Not honoured.** dcode's effort/thinking settings come from its own `config.toml`; the request's value is noted once in the turn log. |
| `text.format` | **Not honoured** (no JSON-schema/structured-output option in ACP). Noted in the turn log when present. |
| `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation` | **Not honoured**; dcode has its own model parameters and turn budget. |
| `tools` of type `mcp` | Written to a temporary Claude Desktop-format config in `/tmp` and passed as `--mcp-config`; its hosts must be reachable by the environment. |
| `previous_response_id` | The platform chose the session; the CLI's own session is resumed instead. |
| `stream`, `background`, `store` | The platform's; the package always streams. |

`request.history` is not replayed into the prompt: the CLI's own session already holds the conversation.

## What is printed

| dcode (ACP `session/update`) | Responses item |
|---|---|
| `agent_message_chunk` | `message` with `output_text`, streamed |
| `agent_thought_chunk` | `reasoning` with `summary_text`, streamed |
| `tool_call` + `tool_call_update`, kind `execute` | `shell_call` then `shell_call_output` (the command, captured output and exit code parsed from dcode's formatted result) |
| kind `edit`, a `write_file` call | `apply_patch_call` `create_file` with the file's content as a diff |
| kind `edit`, an `edit_file` call | `apply_patch_call` `update_file` with the old/new text as a diff |
| kind `delete` | `apply_patch_call` `delete_file` |
| any other tool (`read_file`, `grep`, `task`, an MCP tool, …) | `custom_tool_call` then `custom_tool_call_output` |
| `plan`, notices, compaction, config updates | `hg.log` |
| the prompt response, `stopReason`: `end_turn` | `hg.done` |
| `max_tokens` | `hg.incomplete` with `max_output_tokens` |
| `refusal`, `max_turn_requests`, `cancelled` | `hg.failed` with `refusal`, `max_turns`, `cancelled` |
| a JSON-RPC error on `session/prompt` | `hg.failed` `provider_error`, with the provider's message |
| the CLI ends before answering | `hg.failed` `cli_exit`, with its exit code and the last of its stderr |

Notes:

- `edit_file` in dcode's ACP server never sends a completion update; the start already carries the diff, so
  the edit is printed when the call starts. Every other tool is printed when its completion arrives.
- The CLI's stderr is the turn's log, not the caller's output.
- A stopped turn prints no terminal line: the run passes the signal to the CLI and everything the CLI
  started, ends, and leaves what was already printed.

## Token usage

dcode's ACP stream carries no usage. The CLI records its own cumulative counts in the session database:
`$HOME/.deepagents/.state/sessions.db`, in the latest checkpoint's `_session_cost_breakdown`
(`input_tokens`, `output_tokens`, `cache_read_tokens`). The run reads that total with the CLI's own Python
before the turn and after it has ended, and reports the difference:

```json
{"input_tokens": 29502, "output_tokens": 132, "input_tokens_details": {"cached_tokens": 28928}}
```

`input_tokens` is LangChain's inclusive count (cache reads included), and `cache_read_tokens` is reported as
`cached_tokens`. Subagent model calls are in the same total. A turn that fails before any model call (for
example, an unknown model name) has no counts to report and prints the terminal line without `usage`.

## The session

dcode's ACP session id **is** its LangGraph thread id, and its checkpoints live under
`$HOME/.deepagents/.state/sessions.db` — the mind. The run saves the id with `state.set("session", id)` the
moment `session/new` returns it. The next turn calls `session/load` with that id from the same work folder;
the ACP server replays the old conversation (the run discards that replay, so it is not printed again) and
the new prompt continues it. If the load fails — a stopped or damaged session — the run logs it, clears the
state, and starts a new session in the same process. `session/load` requires the same `cwd`; `run` always
starts in the session's work folder.

## Hosts

The package itself declares no hosts. The environment decides what a turn and an install may reach.

- **Install:** `pypi.org`, `files.pythonhosted.org`; plus `github.com` and
  `release-assets.githubusercontent.com` when the image has no Python 3.14. All are guaranteed install hosts.
- **Turn:** the provider's host only. The trial's turns reached `api.deepseek.com` and nothing else.
- **`api.deepseek.com`** was this build's provider; a different environment's provider host replaces it.
- The agent may itself use `fetch_url` or a web-search tool, and may connect to MCP servers named in the
  request. Those hosts are decided by the request and the environment; the package adds none and the CLI
  works without them. Web search is disabled by dcode when no `TAVILY_API_KEY` is present.
- No update, telemetry, price-refresh or LangSmith host is contacted (`DEEPAGENTS_CODE_NO_UPDATE_CHECK`,
  `DEEPAGENTS_CODE_OFFLINE`, `--no-tracing`).

## Operator

- Nothing to set in `settings` or `secrets`: the provider key is the platform's, and the package declares no
  secret of its own.
- An environment must carry this harness and allow the provider's host. A request then names it as
  `<environment>/dcode/<provider>/<model>`.
- The image needs `python3` and the `venv` module, and a writable `/tmp` for the per-turn MCP config.

## What was tried, and what was not

Tried against a DeepSeek provider through its Anthropic-compatible endpoint, with model `deepseek-flash`:

- a text-only turn (`tests/hello`);
- a turn that writes a file, runs it and reports the output (`tests/command`);
- a turn that starts a session and a later turn that continues it (`tests/resumed`);
- a turn that creates, edits and reads a file (`tests/edit`);
- an unknown model, which the provider rejects (`tests/provider_error`);
- a turn stopped after 12 seconds, and the turn after it, which resumed the same session and continued.

Not tried here:

- OpenAI Chat Completions, OpenAI Responses and Gemini providers (only the Anthropic API was available);
- a live MCP server (the request-to-config mapping is written, but no server was reachable);
- images and other non-text inputs;
- subagents, goals/rubrics, remote sandboxes, plugins and project hooks/extensions;
- the CLI's auto-update and managed ripgrep paths (both are turned off during a turn).

## Files

```
harness.json   manifest
install        uv tool install deepagents-code==0.2.10, with agent-client-protocol==0.12.1
run            one turn: ACP client, translator, session and usage
tests/         recorded turns: hello, command, resumed, edit, provider_error
```

### Why `agent-client-protocol` is pinned

`deepagents-acp` 0.0.13, required by `deepagents-code` 0.2.10, imports `acp.audio_block`. The current
`agent-client-protocol` 1.0.0 no longer exports it, and `dcode --acp` then refuses to start
("ACP dependencies not available"). 0.12.1 satisfies deepagents-acp's `>=0.10.1` range and works; the
install pins it and checks both the module and its version. The dcode version itself is exactly 0.2.10.
