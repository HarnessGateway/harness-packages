# dsh

DeepSeek Harness (`dsh`) **0.2.2-rc.4**, as its makers ship it: one headless task per turn, with its
`--json` run event stream translated to OpenAI Responses events. Package revision 1.

## What it needs

| | |
|---|---|
| Image | Node.js 24.9 or later, npm, and `python3` (the default image has all three). `install` says so plainly when one is missing. |
| Provider | The **Anthropic Messages API** (`"apis": ["anthropic"]`). `dsh`'s DeepSeek transport speaks Messages, so `HG_PROVIDER_URL` is its `DEEPSEEK_BASE_URL` and `HG_PROVIDER_KEY` its placeholder `DEEPSEEK_API_KEY`. |
| Install network | `registry.npmjs.org` only, which every environment's install reaches. `setup.egress` needs nothing else. |
| Turn network | The provider's host. Nothing else was asked for by any tried turn. |

`install` pins `@deepseek-ai/dsh@0.2.2-rc.4` with `npm install --prefix "$HG_HARNESS/tools"` (no package in the
tree needs an install script, so `--ignore-scripts` is used for npm 12 and earlier alike), then checks
`dsh --version`. It names no CPU architecture.

`mind` is `.dsh`: `run` forces `DSH_HOME=$HOME/.dsh`, so sessions, the generated `headless` profile, and the
projection cache all stay in the session's mind. The trial mind after a turn is under 0.2 MB.

## The command

```sh
dsh --profile headless --patch "$TMPDIR/dsh-patch-$$.json" --json \
    --permission-mode danger-full-access --approval-policy never [--session-id ID]
```

The task arrives on standard input (`request.brief()`); `dsh` diagnostics go to standard error and become the
turn's log. `--json` writes newline-delimited events to standard output: an opening `session`, `status`
boundaries (`turn_start`, `step_start`, `step_end` with usage, `turn_end` with a reason), `thinking`, `text`,
`tool_call`, `tool_result`, and a closing `final`. `run` also sets `DSH_TELEMETRY_DISABLED=1`, so the shipped
OpenTelemetry row stays silent; the CLI never updates itself (the install is pinned and read-only).

`--permission-mode danger-full-access --approval-policy never` is the shipped preset that needs no human
approval. Headless has no approval channel, so this is how the one-shot runner is allowed to work; the
platform's own sandbox remains the outer boundary. The preset can be changed in `run` if a deployment wants
`workspace-write` instead.

## The request, onto dsh

| In the request | Where it goes |
|---|---|
| `input`, a string or messages | Joined into one task and written to `dsh`'s standard input through `request.brief()`. |
| `instructions` | In front of the task in that brief. The headless profile has no system-prompt flag. |
| `input_file` / `input_image` parts | `request.place_files()` puts them under `inputs/` in the work folder and the brief names their paths. |
| the handover line | In front of the task through `request.brief()`. |
| `history` | Not used. `dsh`'s own persisted session carries the prior turns. |
| `model` (`HG_MODEL`) | A `--patch` overlay sets the `agent-default-model` row's `model` (and `reasoningEffort`). |
| `reasoning.effort` | `minimal`/`low` → `low`, `medium`/`high` → `high`, `xhigh`/`max` → `max`; written as `reasoningEffort`. Absent leaves the CLI's default. |
| `tools` of type `mcp` | One `@deepseek-ai/dsh-mcp-client` row per server, `transport: streamable-http`, a 15 s startup bound, and reconnection off. `server_url` must be `http(s)`. |
| `previous_response_id`, `stream`, `background`, `store` | The platform's own; nothing is done with them. |

`allowed_tools` on an MCP tool is **not** enforced: `dsh-mcp-client` has no per-server tool filter, so every
tool the server offers becomes callable. Each server's own host must be one the turn can reach. A
`server_label` that is not 1–32 characters of `A-Za-z0-9_-`, or a `server_url` that is not HTTP(S), is left out
and noted in the log.

Not honoured, because the headless profile has no option for them: `text.format`, `max_output_tokens`,
`temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`. `text.format` in particular is not
enforced, so a caller asking for `json_schema` gets only whatever the model produces.

## What is printed

| `dsh --json` line | Responses |
|---|---|
| `session` | nothing; its `sessionId` is saved to state at once |
| `thinking` | a streamed `reasoning` item (`summary_text`) |
| `text` | a streamed assistant `message` (`output_text`) |
| `tool_call` + `tool_result` for `bash` | `shell_call` then `shell_call_output`. The result text is split on its `[stderr]` section and `[exit code: N]` marker; no marker means exit code 0 |
| … for `write` / `edit` | `apply_patch_call` (`create_file` / `update_file`) then `apply_patch_call_output`; the diff is built from the call's arguments |
| … for `apply_patch` | each Add/Update/Delete File operation as the same pair. The shipped headless composition leaves this tool off; it is handled if an overlay turns it on |
| … for `mcp__<server>__<tool>` | one `mcp_call`; a failed result carries the error |
| … for any other tool (`read`, `glob`, `grep`, `todo_write`, `job_*`, `skill`, `web_search`, `web_fetch`, `subagent`, …) | `custom_tool_call` then `custom_tool_call_output` with the tool's name, arguments and text result |
| `status.step_end` usage | accumulated for the terminal line; not printed as an item |
| `final` | the one terminal line |

The terminal line follows `final.reason`:

| Reason | Terminal line |
|---|---|
| `completed` | `hg.done` |
| `max-tokens` | `hg.incomplete` with `max_output_tokens` |
| an error whose code is `CONTENT_REFUSED` | `hg.incomplete` with `content_filter` |
| `error` | `hg.failed`, code from the CLI's error code (lower-cased), message from its error |
| `blocked`, `interrupted`, `aborted` | `hg.failed` with that code |
| no `final` (a driver-level `error` event, or the process died) | `hg.failed` with `cli_exit` and the CLI's message or exit code |

### Token usage

Each `status.step_end` carries the step's usage: `inputTokens`, `outputTokens`, `cacheReadTokens`,
`cacheWriteTokens`, `reasoningTokens`. `run` sums the steps of the turn and reports:

- `input_tokens` = input + cache reads + cache writes (Responses counts all input, cached included);
- `output_tokens` = output;
- `input_tokens_details.cached_tokens` = cache reads;
- `output_tokens_details.reasoning_tokens` when the provider reports it.

A provider failure before any model sample produces no `step_end.usage`; the failed turn then carries no
usage, which is the CLI's own silence, not an omission by the package.

## How the session continues

`dsh` stores its session under `$DSH_HOME/sessions`. On the opening `session` line, `run` saves its
`sessionId` with `state.set("session", …)` before reading any further line, so a stopped turn is still
continued. The next turn passes `--session-id`. If that session cannot be adopted (an unknown id, a changed
working directory, or a turn left unusable by a hard stop), `dsh` exits non-zero without a `final`; `run`
clears the state and runs the task once more as a new session. The working directory is always `/work`, which
is what adoption compares.

A turn stopped by the platform prints no terminal line; the kit stops `dsh` and everything it started.
`run.stop_grace_s` is 15 seconds; a stopped turn was observed to end well within it.

## Hosts an environment must allow

- **Install:** `registry.npmjs.org` only — a package registry, always reachable.
- **Turns:** the provider's host and nothing else. When the provider's origin is the official
  `https://api.deepseek.com`, `dsh` also loads its model listing from `https://api.deepseek.com/models` at
  startup; any other `DEEPSEEK_BASE_URL` serves the built-in catalogue and makes no listing request.
- **MCP from the request:** each `server_url`'s host is the caller's, not the package's, and must be allowed
  for that server to work.
- **The shipped web tools** were not exercised. If the agent calls `web_search`, the headless profile's
  default search endpoint is `https://api.deepseek.com/anthropic` (or `DEEPSEEK_SEARCH_BASE_URL`); if it calls
  `web_fetch`, it fetches the public URL it was given. Allow those destinations when those tools are wanted.

## What an operator must set

Nothing in the harness: there are no settings and no secrets. The environment must offer a provider with the
Anthropic Messages API, and its image must have Node.js 24.9 or later (the default image does). The provider's
key is supplied by the platform proxy; no key is in this package.

## What could not be tried here

Tried: a text-only turn; a file write followed by a shell command; a resumed turn; `instructions`; an inline
file input; `reasoning.effort`; a stopped turn and the turn after it; a provider error (an unknown model); an
MCP server that cannot be reached. Not tried: a live MCP server's tool call, `web_search` / `web_fetch`, image
input and `read_image`, subagents, background jobs, `max-tokens` truncation, a content refusal, and a provider
that is not `api.deepseek.com`.
