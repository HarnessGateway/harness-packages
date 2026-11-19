# cline

The Cline CLI, as Cline Bot Inc. ships it, headless in a HarnessGateway sandbox.

- **CLI:** `cline` from the npm package `cline`, pinned at **3.0.74** (the latest stable release when this
  package was written).
- **Package version:** `3.0.74-2`.
- **Mind:** `.cline` — the CLI's own folder under `$HOME`.
- **APIs:** `anthropic` first, then `openai-chat`.

## What it is

A vanilla harness package: nothing is added to the CLI, no instructions, no permission rules of its own, no
secrets. `run` starts the CLI headless, translates what it does into Responses events, and continues the
CLI's own session on the next turn.

Cline's one-shot mode (`cline --json "…"`) is simpler, but it always starts a new session: its `--id`
resume flag works only in the interactive TUI, and the CLI refuses JSON output in interactive mode. Its
**Agent Client Protocol** mode (`cline --acp`) is the CLI's own headless, bidirectional interface. It opens
a session and reports its id, streams the agent's text, reasoning and tool calls as JSON-RPC notifications,
and loads a session by id. This package therefore drives ACP with a small JSON-RPC client in `run`.

`run` is written in Python (standard library only) and talks to the CLI over its standard input and output.
It does not use `hgkit.Cli`, because `hgkit.Cli` writes standard input once and closes it, and a protocol
needs to keep talking. For the platform's checker, `run` reads the recorded standard output instead
(`HG_REPLAY`) and translates it exactly as a live turn does.

## What the image and the provider must give it

- **Node.js 22 or later**, with `npm` — the npm package's launcher is Node, and it resolves a bundled
  platform-specific binary (the binary carries its own Bun runtime, so Bun need not be installed).
- **`python3`** — `run` is Python, standard library only.
- A provider that speaks the Anthropic Messages API or OpenAI Chat Completions. The platform hands the
  provider's base URL, a placeholder key and the model; the CLI is pointed at them.

No other image package is needed. `install` installs the CLI itself under `$HG_HARNESS/tools`.

## Install

`install` runs `npm install --prefix "$HG_HARNESS/tools" --ignore-scripts cline@3.0.74`, then checks
`node_modules/.bin/cline --version` and fails with a plain message unless it is `3.0.74`.

`--ignore-scripts` is deliberate: it behaves the same under npm 12 (which runs no dependency's install
script unless told to) and older npm (which runs every one). The package's only install script hard-links
the platform binary into the package for faster startup; the launcher finds the binary by walking
`node_modules` without it. npm chooses the build for the machine's platform and architecture; the package
names neither.

**Install hosts reached in the trial:** `registry.npmjs.org` only (a package-manager registry, always
available to an install).

## The command

```sh
$HG_HARNESS/tools/node_modules/.bin/cline --acp --auto-approve true [--thinking <level>]
```

with these variables, alongside the turn's proxy and certificate variables:

| Variable | Value |
|---|---|
| `CLINE_DATA_DIR` | `$HOME/.cline/data` — the CLI's own session store and settings, under the mind |
| `CLINE_PROVIDER` | `anthropic` or `openai-compatible`, chosen from `HG_PROVIDER_API` |
| `CLINE_MODEL` | `HG_MODEL` |
| `CLINE_API_KEY` | `HG_PROVIDER_KEY`: a placeholder the platform's proxy replaces on the way out |
| `CLINE_NO_AUTO_UPDATE` | `1` |
| `E2E_TEST` | `true` — the CLI's own switch that makes its feature-flag poll use a provider that answers nothing, so no request goes to `data.cline.bot` |
| `DISABLE_TELEMETRY`, `OTEL_TELEMETRY_ENABLED` | telemetry off (belt and braces; the CLI's own `telemetryEnabled` setting is also written false) |

The CLI's provider settings file, `$HOME/.cline/data/settings/providers.json`, is written at the start of
each turn with the provider, the model and the provider's base URL, and a fresh `updatedAt` stamp. The CLI
ignores a provider entry without that stamp. The placeholder key is **not** written there: it is passed in
`CLINE_API_KEY`, so the mind never keeps a stale placeholder. `$HOME/.cline/data/settings/global-settings.json`
is merged with `telemetryEnabled: false` and `openTelemetryEnabled: false`.

The CLI's ACP handshake is: `initialize`; `session/new` on a first turn or `session/load` on a later one;
`session/set_model` with `HG_MODEL`; `session/prompt` with the turn's brief. On a stop, `run` sends
`session/cancel`, stops the CLI and everything it started, and exits without a terminal line.

The CLI starts a local **hub daemon** for its session (a process of its own, under `$HOME/.cline/data`).
It is a process of the turn: `run` stops it, and anything else the CLI started, before it exits — at the
end of a normal turn as well as on a stop.

## The request, onto the CLI

| In the request | Where it goes |
|---|---|
| `input` (string, or messages) | The prompt text, through `request.brief()` |
| `instructions` | In front of the prompt, in the brief. ACP has no system-prompt field, and the CLI's `--system` replaces Cline's own system prompt, so it is not used for this |
| `input_file`, `input_image` | `request.place_files()` puts them in `inputs/` in the work folder and the brief names them |
| the handover line | In front of the prompt, through `request.brief()` |
| `model` (`HG_MODEL`) | `session/set_model` on the session, and `CLINE_MODEL` |
| the provider's base URL | `baseUrl` in the CLI's provider settings |
| the provider's key placeholder | `CLINE_API_KEY` |
| `reasoning.effort` | `--thinking`: `minimal`/`low` → `low`, `medium` → `medium`, `high` → `high`, `xhigh` → `xhigh` |
| `tools` of type `mcp` | `mcpServers` on `session/new`/`session/load`: each server as `{type: "http", name: server_label, url: server_url, headers: […]}` |
| `previous_response_id`, `stream`, `background`, `store` | The platform's; the session is continued from the mind |
| `text.format` | **Not honoured.** Cline has no option for it. When the format is not `text`, `run` says so once with `hg.log` |
| `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | **Not honoured**; Cline has no ACP option for them. They do not fail the turn |
| `tools` of any type but `mcp` | The platform refuses such a request before it reaches a package |

`allowed_tools` on an MCP server is **not enforced**: ACP has no per-server tool filter, so the CLI exposes
the server's whole tool list. When a request sets it, `run` says so once with `hg.log`. Remote MCP servers
must be reachable by the turn (the turn's environment decides; no host is added by this package).

## What is printed for each thing the CLI does

| The CLI | Output |
|---|---|
| `agent_message_chunk` | A streamed `message` with one `output_text` part |
| `agent_thought_chunk` | A streamed `reasoning` item with one `summary_text` |
| `run_commands` tool call and its result | `shell_call`, then `shell_call_output` with the command's output. ACP reports no exit code: `0` is printed when the CLI reports the command succeeded, `1` when it reports failure, with the output in `stderr` |
| `editor` creating a file | `apply_patch_call` (`create_file`) with the new content as a `+` diff, then its output |
| `editor` changing a file | `apply_patch_call` (`update_file`) with the old text as `-` and the new as `+`, then its output |
| `editor` failing | A `custom_tool_call` named `editor` and its output: no patch happened |
| `use_mcp_tool` | `mcp_call` with the server, the tool, its arguments and the output (`error` when it failed) |
| `read_files`, `search_codebase`, `fetch_web_content`, `ask_question`, `skills`, `spawn_agent`, `team_*`, other tools | `custom_tool_call`, then `custom_tool_call_output` |
| `submit_and_exit` | Nothing: it is the CLI's own one-shot way of ending a run, not work the agent did |
| `user_message_chunk`, session/mode/config bookkeeping | Nothing |
| anything unexpected | `hg.log`, never a guess |

The end of a turn:

- `end_turn` → `hg.done`, with `usage` when the CLI's history reports the turn's counts
- `max_tokens` → `hg.incomplete` with `max_output_tokens` (and `usage` when reported)
- `refusal` → `hg.incomplete` with `content_filter` (and `usage` when reported)
- a JSON-RPC error from the prompt → `hg.failed` with `provider_error` and the CLI's own message
- the CLI ending before answering → `hg.failed` with `cli_exit`
- a stopped turn → no terminal line (the platform's rule)

**Token usage.** ACP itself carries none in 3.0.74. A real turn was recorded line by line: the stream
contains no `usage_update` notification, and the answer to `session/prompt` is `{"stopReason": …}` with no
`usage` and no `_meta` field. The protocol's schema has both — a `usage_update` update carrying only a
context window's `used` and `size`, and an optional `usage` object on the prompt result — but this CLI
sends neither.

The CLI does keep the counts, and documents a machine-readable way to read them: `cline history --json`
(the `cline history` command, `--json`; the same numbers `cline -v` prints as its run stats). Each
session row has `metadata.usage` with `inputTokens`, `outputTokens`, `cacheReadTokens` and
`cacheWriteTokens`. That row is written while the ACP session is still open, so `run` reads it twice per
turn — after the session is resumed or opened, and after `session/prompt` answers — and reports the
difference. A resumed session's history totals include every earlier turn, so the difference is this
turn's own usage.

| `cline history --json` `metadata.usage` | Responses `usage` |
|---|---|
| `inputTokens` | `input_tokens` (it already includes cache reads) |
| `outputTokens` | `output_tokens` |
| `cacheReadTokens` | `input_tokens_details.cached_tokens` |

`cacheWriteTokens` has no field in the Responses usage object; its tokens are already inside
`inputTokens`. When the history row is missing or carries no counts (for example a provider error before
any completion), the terminal line has no `usage`, rather than a row of zeroes.

The recordings under `tests/` hold the ACP stream plus the two `cline history --json` readings a live turn
took (a JSON array is not an ACP message), so the checker replays the same counts without a CLI or a
model.

## How the session is continued

1. On `session/new`, the CLI reports a session id. `run` saves it with `state.set("session", id)` at once,
   before the turn can be stopped.
2. The next turn sends `session/load` with that id. ACP replays the earlier conversation to the client
   while loading; `run` ignores every update until the load has answered, so the caller sees only this
   turn's work.
3. If `session/load` fails (a stopped turn can leave a session unusable), `run` says so with `hg.log`,
   clears the saved id, and opens a new session for the same turn.
4. The CLI's store is `$HOME/.cline/data/sessions/<id>/`; it comes back with the mind. A stopped turn
   leaves the session usable: the trial stopped one in the middle of a `sleep 90`, and the next turn
   continued it and remembered the task.

`run.stop_grace_s` is 15: the CLI is a Node launcher around a Bun binary, and stopping it means stopping
both plus any command it was running.

## Hosts an environment must allow

Install, beyond the package-manager registries it already has: **none**.

Turns, beyond the provider's own host: **none**. The trial's turns asked for the provider's host and
nothing else. In particular:

- `data.cline.bot` is not asked for: feature-flag polling is off through the CLI's own `E2E_TEST` switch,
  and telemetry is off in the CLI's global settings.
- `api.anthropic.com` is not asked for unless an Anthropic provider is actually configured with Cline's
  default base URL; this package always writes the turn's provider base URL.
- Cline's update check does not run (`CLINE_NO_AUTO_UPDATE=1`; `--update` is never passed).

No host is named in `harness.json`; the environment decides what a turn may reach.

## What an operator must set

Nothing. The package declares no settings and no secrets. The environment must carry the harness and have
a provider that offers one of its declared APIs. A request names the harness as
`<environment>/cline/<provider>/<model>`.

## The mind

`.cline/data/` holds the CLI's session store (`sessions/`, `db/`), its settings (`settings/`), and small
bookkeeping (its local hub's databases). The trial's mind after several turns, a stop, and a stopped turn
continued held a few tenths of a megabyte. `logs/` and `cache/` are named in the manifest's `cache` and are
not saved with the session; the CLI makes them again by itself.

## What could not be tried here

- **`openai-chat` through the platform's own provider selection.** This session's provider offers the
  Anthropic API first, so every recorded turn used `anthropic`. The OpenAI-compatible mapping
  (`CLINE_PROVIDER=openai-compatible`, the `/v1` base URL as `baseUrl`) was exercised by hand against the
  same provider's OpenAI-compatible endpoint, and a turn completed; but no environment whose provider
  selects `openai-chat` was tried. Its `cline history --json` usage was therefore not compared with the
  Anthropic case.
- **`thoughtTokens`.** The history row carries no reasoning-token split; `outputTokens` already includes
  reasoning, so `output_tokens` is the CLI's total.
- **MCP servers.** No live MCP server was reachable from the trial; the ACP `mcpServers` mapping, and the
  note that `allowed_tools` is not enforced, were not exercised end to end.
- **Images.** `input_image` files are placed in `inputs/` and named in the prompt; they were not sent as
  ACP image content blocks.
- **Other images.** Everything was tried on the default image with Node 26; Node 22 (the launcher's
  minimum) was not tried.
- **Plan mode, the TUI, the hub, `--zen`, ACP session fork/resume extensions.** This package uses only
  `initialize`, `session/new`, `session/load`, `session/set_model`, `session/prompt` and `session/cancel`.

## Tests

`tests/` holds four recorded turns made with `trial.py` and checked by
`harnessgateway package check`:

| Case | What it shows |
|---|---|
| `hello` | A fresh session, text only, `hg.done` with the turn's `usage` |
| `command` | `editor` creating `hello.py`, `run_commands` running it, and the final message, with `usage` |
| `resumed` | The next turn on the same session, answering from the earlier turn's work, with no replay of the old conversation, and only that turn's `usage` (the history totals were subtracted) |
| `provider_error` | A model the provider does not know: one `hg.failed` with the provider's message, and no `usage` because no completion happened |

A stopped turn and the turn after it were tried by hand (`--stop-after`) and are not recorded as a case,
because a stopped turn prints no terminal line and the checker expects one.
