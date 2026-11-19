# opensquilla

OpenSquilla, the token-efficient microkernel agent from
[TokenRhythm/opensquilla](https://github.com/TokenRhythm/opensquilla), as its makers ship it, run headless for
one automation turn through its own `opensquilla agent` command.

This is a vanilla package: it adds no instructions, no permission policy and no tools of its own. What it does
is put the platform's provider, model and prompt into the CLI and translate the CLI's result into Responses
events.

## What it needs

- **Image:** Linux with `python3` 3.9 or later (to bootstrap `uv`). Everything else the CLI needs, `uv`
  downloads. The install writes about 1.1 GB under `$HG_HARNESS/tools` (its own CPython 3.12, the wheel, and the
  `recommended` extras the makers install by default), so the image needs that much room.
- **Provider:** a model reachable through one of the APIs in `harness.json`. The request names the provider and
  model; the package has no settings and no secrets of its own. The provider's key arrives as
  `HG_PROVIDER_KEY` and is handed to the CLI as `OPENSQUILLA_LLM_API_KEY`; it is the platform's placeholder, and
  the platform's proxy puts the real key in on the way out.
- **Network:** at install, the package registries and GitHub (see *Hosts*). At a turn, only the provider's host
  for a text turn.

## The CLI

`install` follows the makers' documented method (`install.sh`): `uv tool install --python 3.12` of the release
wheel, with the `recommended` profile. It pins:

- OpenSquilla **0.5.8**, from
  `https://github.com/TokenRhythm/opensquilla/releases/download/v0.5.8/opensquilla-0.5.8-py3-none-any.whl`
- `uv` **0.13.9**, from PyPI, into a throwaway venv under `$HG_HARNESS/tools`.

The result is at `$HG_HARNESS/tools/bin/opensquilla`, and `install` checks that `opensquilla version` says
0.5.8. The package revision is `0.5.8-1`.

`run` starts:

```
opensquilla agent -m <brief> --workspace $HG_WORK --permissions bypass --json --no-memory-capture
                  --session-id agent:main:main --session-db-path $HOME/.opensquilla/session.sqlite3
                  --transcript-path <temp file> --model <HG_MODEL> [--thinking <effort>]
```

with `OPENSQUILLA_LLM_PROVIDER`, `OPENSQUILLA_LLM_BASE_URL`, `OPENSQUILLA_LLM_API_KEY` and
`OPENSQUILLA_LLM_MODEL` set from the turn. `OPENSQUILLA_TRUST_ENV=1` makes the CLI honour `HTTPS_PROXY`; without
it the CLI ignores the sandbox's proxy and cannot reach the provider.

Telemetry, the update check, the session-namer, SquillaRouter and OpenRouter's live price lookups are turned
off: the request names one model, and none of those should route away from it or reach the network. Memory
embeddings are off and retrieval is lexical (`fts_only`), so no embedding model is fetched; memory lives under
the mind (`.opensquilla/state`), not in the caller's `/work`. Automatic memory capture is off for these
one-shot turns (`--no-memory-capture`), so the mind does not grow by itself; the agent's own memory tools still
work.

## How the request maps

| In the request | In the turn |
|---|---|
| `input` (string or message list) | The prompt, through `request.brief()` |
| `instructions` | In front of the prompt: OpenSquilla's one-shot command has no system-prompt option |
| the handover line | In front of the prompt, as `request.brief()` puts it |
| `input_file` / `input_image` | Placed in `$HG_WORK/inputs/` and named in the prompt |
| provider | Provider id chosen by `HG_PROVIDER_API`: `anthropic` → `anthropic`; `openai-chat` → `openai`; `openai-responses` → `openai_responses`; `gemini` → `gemini` (base URL + `/v1beta/openai`, the OpenAI-compatible surface OpenSquilla speaks) |
| `model` | `--model`, `OPENSQUILLA_LLM_MODEL` |
| `reasoning.effort` | `--thinking`: `none`→`off`; `minimal`, `low`, `medium`, `high`, `xhigh`, `adaptive` passed through |
| `max_output_tokens` | `OPENSQUILLA_LLM_MAX_TOKENS` |
| `temperature`, `top_p` | `OPENSQUILLA_LLM_TEMPERATURE`, `OPENSQUILLA_LLM_TOP_P` |
| `tools` of type `mcp` | A generated `config.toml` (`[mcp]`, one `[[mcp.servers]]` per server, `transport = "sse"`) |
| `previous_response_id`, `stream`, `background`, `store` | The platform's; the CLI session is resumed from the mind |

**Not honoured:**

- `text.format`: OpenSquilla has no option for a response schema. The turn is asked without enforcing it, and
  `run` says so once with `hg.log`.
- `truncation`, `max_tool_calls`, `user`, `metadata`: no CLI option; ignored.
- With the `anthropic` API, OpenSquilla sends the key as `x-api-key`, as Anthropic does. A provider whose
  Anthropic-compatible endpoint insists on `Authorization: Bearer` will reject the turn; the CLI has one
  provider id per header style, and this package uses the standard Anthropic one.
- MCP `headers`: OpenSquilla's MCP client takes no HTTP headers for a server, so a request's headers are not
  sent (logged). Its MCP client supports **SSE** only, not streamable HTTP or stdio from the request;
  `allowed_tools` is not enforced per server (the whole server's tools are advertised).

## What a turn prints

OpenSquilla's one-shot command has **no streaming output**. It prints one JSON object at the end; with
`--transcript-path` it also writes the session transcript as JSONL. That transcript is the only place the CLI
makes known what each tool was given and answered. `run` reads both and prints the turn's items **when the CLI
ends**. While it works, `run` prints no output items; it forwards the CLI's stderr (including its opt-in
progress events) to the turn's log and writes an `hg.log` line every 20 seconds or so, so a long turn does not
leave the stream empty.

| The CLI did | The items |
|---|---|
| assistant text | one `message` per contiguous piece, with `output_text` deltas |
| `exec_command` | `shell_call` + `shell_call_output`. OpenSquilla merges stdout and stderr and prefixes the exit code; `run` strips the prefix, puts the merged text in `stdout`, and takes the exit code from the result |
| `write_file`, `write_scratch` | `apply_patch_call` (`create_file`) + output |
| `edit_file`, `edit_source` | `apply_patch_call` (`update_file`) + output, with `-old`/`+new` diff lines |
| `apply_patch` | one `create_file`/`update_file`/`delete_file` per file in the patch |
| `mcp__<server>__<tool>` | `mcp_call` |
| any other tool (`read_file`, `web_search`, `web_fetch`, `execute_code`, `memory_*`, `subagents`, …) | `custom_tool_call` + `custom_tool_call_output` with the arguments and result |

Rows of the transcript that are the current user message are not echoed; `system` rows (the CLI's own error
notes) go to `hg.log`. Tool arguments and results are the transcript's, capped at 1 MB per result.

**Token usage** comes from the final JSON object's `usage`: `input_tokens`, `output_tokens` and
`cached_tokens` (OpenSquilla's `input_tokens` already includes cache reads and writes, so they are not added
again). `reasoning_tokens`, when non-zero, goes in `output_tokens_details`. A provider rejection that never
reached the model reports zeros.

**Errors:** a JSON result with `status: "error"` becomes `hg.failed` with the CLI's own code and message (an
HTTP status such as `400` is reported as `provider_error`). A CLI that exits without a JSON result becomes
`hg.failed("cli_exit", …)` with its exit code and last stderr line. There is no clean "length cap" signal from
the CLI, so `hg.incomplete` is not emitted; a turn the provider cut short surfaces as the CLI's own error.

## Sessions

OpenSquilla keeps a session in a SQLite database. The package uses one fixed session key, `agent:main:main`,
and `--session-db-path $HOME/.opensquilla/session.sqlite3`. The mind is `$HOME`, so the database is saved,
restored, rewound and forked with the session. `run` writes the key with `state.set("session", …)` before the
CLI starts and again from the result. A stopped turn persists its user message; the next turn opens the same
database and continues. There is no "session is gone" retry: opening a missing key creates a new session, and
a corrupted database is not detectable before the CLI starts.

## Hosts

What the trials saw, beyond the provider:

- **Install:** `github.com`, `release-assets.githubusercontent.com` (the release wheel and uv's CPython build),
  `pypi.org`, `files.pythonhosted.org` (uv and its dependencies). All are in the platform's registries, so no
  `setup.egress` entry is needed. `releases.astral.sh` is deliberately avoided with
  `UV_PYTHON_INSTALL_MIRROR` and `UV_NO_UPDATE_CHECK`.
- **Turn:** the provider's host only (`api.deepseek.com` in these trials). Nothing else is contacted: no
  OpenRouter price list, no telemetry, no update check, no embedding model.

Not required, but possible if the agent uses them:

- `web_fetch` reaches any URL the agent chooses: a trial reached `wttr.in`. `web_search` uses DuckDuckGo by
  default; a trial's search reported a network error, and the turn finished anyway. The CLI works without
  either -- those tools fail and the agent reports it -- so allow hosts only if you want the agent to browse.
- MCP servers named in a request: the turn must be allowed each server's host for the client to connect.
  Untested here (no MCP server was available).

The package's manifest names no host; an environment decides.

## What an operator must set

Nothing. The harness takes the provider, model and key from the request, and declares no settings or secrets.
The environment must carry the harness and have network `limited` (provider + registries) at least; the image
needs `python3` and room for the install. If the agent is to browse or use MCP servers, allow those hosts in
the environment's `network.allow`.

The mind after a turn holds about 1.5 MB: `session.sqlite3`, the CLI's small state databases, and its memory.
`.opensquilla/cache` (the skills catalogue) and `.opensquilla/logs` are declared as `cache`, so they are not
saved. `/work` holds only what the agent wrote.

## Tests

`tests/` holds six recorded turns: `hello`, `command` (a file written and a command run), `resumed` (the turn
after `command`), `stopped-then-continued` (the turn after one stopped by `--stop-after`), `file-input` (an
inline `input_file` the agent reads from `inputs/`), and `provider-failure` (`HG_MODEL=no-such-model`). Each
`recording` is the package's record of the turn:
`{"stdout": [...], "stderr": [...], "transcript": [...], "exit_code": N}` -- the CLI's stdout, the tail of its
stderr, and the new transcript rows. `run` replays it when `HG_REPLAY` is set.

```
/harness/tools/platform/bin/harnessgateway package check /work/opensquilla
```

## What was not tried here

- The `openai-chat`, `openai-responses` and `gemini` mappings: this session's provider speaks Anthropic only.
  The code paths are the CLI's own provider ids, but they ran only against the Anthropic-compatible endpoint.
- MCP servers: the config mapping is written, but no server was reachable to exercise it.
- An uploaded file by id (`/turn/files`) and `input_image`; an inline `input_file` was tried and works.
- Provider errors other than a 400 rejection, and a CLI crash before any result.
- An environment whose image lacks libgomp: SquillaRouter (disabled by this package) would need it; the turn
  does not.
