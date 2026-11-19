# nanobot

A harness package for [nanobot](https://github.com/HKUDS/nanobot) — the HKUDS personal AI agent, PyPI package
`nanobot-ai` — as its makers ship it: one headless turn per request, with the agent's own tools, workspace,
memory and session store.

- **Pinned version:** `nanobot-ai==0.4.1` (manifest `0.4.1-1`).
- **Installed by:** `install` creates a virtual environment at `$HG_HARNESS/tools/venv` and `pip install`s the
  pinned wheel into it, the makers' documented pip route (`uv tool install nanobot-ai` installs the same
  package). `install` checks `nanobot --version` and fails with a plain message if the image has no Python 3.11
  or later, or if the version installed is not 0.4.1.
- **Mind folder:** `$HOME/.nanobot` (the CLI's own instance root: `config.json`, `sessions/`, `cache/`).
- **Work folder:** the turn's `/work`, used as nanobot's workspace.

## Why a driver process and not `nanobot agent -m`

nanobot's command line has no headless machine-readable mode. `nanobot agent -m "…"` prints a rendered answer
plus human progress hints (`↳ write …`, `↳ $ …`); its tool arguments and results, reasoning and token counts
never appear on stdout. Its makers do document a Python SDK over the same agent runtime
([`docs/python-sdk.md`](https://github.com/HKUDS/nanobot/blob/main/docs/python-sdk.md)) with typed streaming
events: `run.started`, `text.delta`, `reasoning.delta`, `tool.started`, `tool.completed`/`tool.failed`, and a
`RunResult` carrying the turn's token usage.

So `run` starts `nanobot_headless.py` with the installed nanobot's own Python. That driver reads one JSON spec
on stdin, calls `Nanobot.from_config(...).run(...)` once with an `AgentHook` attached, and prints one JSON object
per line. `run` translates those lines into Responses events. Everything is the makers' code and the makers'
configuration format; the package adds no patch, no fork and no default instructions. The driver is a
subprocess so that `hgkit.Cli` can record its output for `tests/`, replay that recording under
`harnessgateway package check` (no model or network), and stop it and every process it started when a turn is
stopped.

## What the image and the environment need

- **Install:** `python3` 3.11 or later, `venv`/`ensurepip`, and the package registries (`pypi.org`,
  `files.pythonhosted.org`). No compiler and no root: only wheels are installed.
- **Turn:** the provider's base URL, key and model, passed by the platform. No other variable is required.
- **Provider APIs:** `anthropic`, `openai-chat` (Chat Completions) and `openai-responses` are implemented. The
  turn uses whichever one the provider offers, in the manifest's order (`openai-chat`, `openai-responses`,
  `anthropic`).
  - `anthropic` → nanobot's built-in `anthropic` provider with `apiBase` set to `HG_PROVIDER_URL`.
  - `openai-chat` → nanobot's `custom` provider with `supportedApis: ["chat_completions"]`.
  - `openai-responses` → the same with `supportedApis: ["responses"]`.
  `HG_PROVIDER_KEY` is written into the config as `${HG_PROVIDER_KEY}`, so the placeholder never enters a file;
  nanobot resolves it from the environment at load, and the platform's proxy replaces it on the way out.

## The command

```
$HG_HARNESS/tools/venv/bin/python -I $HG_HARNESS/nanobot_headless.py     # stdin: one JSON turn spec
```

The driver configures `$HOME/.nanobot/config.json` from the turn (provider, model, effort, MCP servers), writes
nothing outside the mind and the work folder, and calls nanobot's SDK once. `run` prints no other command.

## The request, onto nanobot

| In the request | Where it goes |
|---|---|
| `input` (a string, or a list's user messages) | the turn's message (`hgkit.Request.brief()`); a list is joined by the kit |
| `instructions` | in front of the message — nanobot has no system-prompt option; its system prompt is built from `SOUL.md`, `USER.md`, `AGENTS.md` and memory in the workspace |
| the handover line | in front of the message (`brief()`) |
| `input_file` / `input_image` parts | `hgkit` writes them to `inputs/` in the work folder and `brief()` names them |
| `model` | `HG_MODEL`, in the `harness` model preset |
| the provider | `providers.<anthropic|custom>.apiBase` / `apiKey` |
| `reasoning.effort` | `agents.defaults.reasoningEffort` (`minimal` is passed as `low`; other nanobot values as given) |
| `max_output_tokens` | the preset's `maxTokens` (default 8192) |
| `temperature` | the preset's `temperature` (nanobot's default is 0.1) |
| `tools` of type `mcp` | `tools.mcpServers`, one entry per `server_label`/`server_url`, with `headers` and `allowed_tools` as `enabledTools` |
| `previous_response_id` | nothing: the platform restored the mind, and `run` resumes nanobot's own session |
| `stream`, `background`, `store` | the platform's |

**Cannot be honoured:** `text.format`, `top_p` and `max_tool_calls` — nanobot has no equivalent and the request
is not failed over them; a non-empty `text.format` or `top_p` is noted once in the turn's log. `truncation`,
`user` and `metadata` are ignored. `max_output_tokens` can be shorter than asked when the provider stops a
reply, but nanobot's runner retries a length-truncated reply and reports the finished turn as `completed`; the
package has no `max_output_tokens` stop to report.

Tools of any type but `mcp` never reach a package; the platform refuses such a request.

## What is printed for what nanobot does

| nanobot | Printed |
|---|---|
| an answer (SDK `text.delta`) | one `message` item, streamed |
| reasoning (`emit_reasoning`) | one `reasoning` item with a `summary_text`, streamed |
| `exec` tool | `shell_call` + `shell_call_output`; the command is the tool's `command`, stdout is the tool's captured output, the exit code is the one nanobot printed in its result. nanobot merges stderr into the same buffer, so `stderr` is empty |
| `write_file` | `apply_patch_call(create_file)` + output, with a unified diff from the file before and after |
| `edit_file` | `apply_patch_call(update_file)` + output |
| `apply_patch` | one `apply_patch_call` pair per file it changed: `create_file`, `update_file` or `delete_file` |
| a tool of a request MCP server (`mcp_<label>_<tool>`) | `mcp_call` with arguments, output, and the error when it failed |
| any other tool (`read_file`, `list_dir`, `grep`, `find_files`, `web_fetch`, `web_search`, sub-agents, cron, …) | `custom_tool_call` + `custom_tool_call_output` |
| a failed tool | still printed, with what it said (a file tool that failed is a `custom_tool_call`, since no file changed) |
| nanobot's error | `hg.failed` with nanobot's own message |
| the end | `hg.done`; `hg.failed` when nanobot stopped with `error`, `cancelled` or `empty_final_response`, or reached its 200 tool-iteration limit |

Any non-JSON line the driver or the runtime writes to stdout goes to `hg.log` rather than being guessed at.

### Token usage

The numbers are nanobot's `RunResult.usage`, which the SDK takes from the agent loop's per-turn capture
(`LLMUsage`): `input_tokens` (already including cache reads and writes), `output_tokens`, and
`cache_read_tokens` as `input_tokens_details.cached_tokens`. They cover every model call in the turn, including
tool-call rounds. A failed turn reports zeroes when no model call completed; the platform then shows no tokens
for it, which is correct.

## Sessions

`run` chooses the session key `cli:direct` (nanobot's own one-shot session), or the key saved in
`hgkit.State["session"]`, and calls `state.set("session", …)` as soon as the driver reports the key at the start
of the turn. nanobot persists each turn in `$HOME/.nanobot/sessions/<workspace-id>/sessions.sqlite3`, so the
next turn — after a normal end or a stopped one — continues the same conversation. If resuming raises a
session/database error before anything else happened, `run` logs it, clears the saved key and starts a fresh
session in the same turn; if nanobot reports that the store itself is unreadable, `run` first renames
`sessions.sqlite3` (and its `-wal`/`-shm`) to `*.broken`, so the turn can go on. A corrupt store is therefore
lost, not repaired.

`request.history` (turns another harness took on this session) is not replayed into nanobot: its own session
store is the conversation it continues, and the handover line in `brief()` tells it where the other harness's
files are.

The work folder is nanobot's workspace: on the first turn it creates its agent profile there (`SOUL.md`,
`USER.md`, `AGENTS.md`, `HEARTBEAT.md`, `memory/`, `skills/`, `prompts/`) and a `.git` store it uses for
change tracking. That is the CLI's own behaviour, and those files stay with the session's work folder.

## Hosts an environment must allow

The install already reaches the package registries (`pypi.org`, `files.pythonhosted.org`), which every install
may reach.

Turns ask for these beyond the provider:

| Host | Why | Needed? |
|---|---|---|
| `openaipublic.blob.core.windows.net` | `tiktoken` downloads its `cl100k_base` vocabulary once per session into `$HOME/.nanobot/cache/tiktoken`, for context-size estimates | No: if it is refused, nanobot logs a warning and falls back to UTF-8 byte estimates. The provider's own token counts (the ones reported at the end) are unaffected |
| the `server_url` host of each request MCP server | the agent connects to that MCP server | Only for requests that name MCP servers; the environment must allow that host for the tool calls to work |

Nothing else was asked for in the trials: a text turn and a file-and-command turn reached only the provider
(and, on a fresh session, the tiktoken host above).

## What an operator must set

Nothing. There are no settings and no secrets: the provider's key is the platform's placeholder, and the
provider, base URL and model come from the request. An environment only has to carry the harness.

## What could not be tried here

- The `openai-chat` and `openai-responses` paths were run by hand against DeepSeek's OpenAI-compatible endpoint
  and answered normally, but they are not in the recorded cases: this session's provider is reached with the
  `anthropic` API, so only that path went through a platform trial.
- MCP servers were not exercised: no trial turn named one, so the `mcp_call` mapping and the `mcpServers`
  configuration are unproven end to end.
- Web tools: no trial turn called `web_search` or `web_fetch`, so their hosts are not listed above. If an agent
  is expected to use them, allow the host of the configured search/fetch provider.
- Scheduled jobs, channels and the gateway are not part of a headless turn; `run` starts one agent turn and
  exits.

## How it becomes a harness

In the console: **Sessions**, this session, **New harness from workspace**, the folder `nanobot`; then
**Install**. Or `POST /v1/drafts` with `{"name": "nanobot", "session": "<session id>", "path": "nanobot"}`
followed by `POST /v1/drafts/nanobot/install`. The environment must then carry it (its Harnesses list), and a
request names it as `<environment>/nanobot/<provider>/<model>`.
