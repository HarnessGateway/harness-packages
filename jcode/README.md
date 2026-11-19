# jcode

J-Code (`jcode`, <https://github.com/1jehuang/jcode>) as its makers ship it: one headless coding-agent
turn per request, streamed back as OpenAI Responses events.

- **Pinned CLI:** jcode 1.0.0 (`v1.0.0`, the latest stable release at build time).
- **Installed by:** the makers' own `scripts/install.sh` at tag `v1.0.0`, whose SHA-256 is pinned in
  `install`; that installer picks the build for the machine, downloads the release archive from GitHub,
  and verifies the archive's published SHA-256. It is run with `JCODE_VERSION=v1.0.0` and with its
  version store and launcher inside `$HG_HARNESS/tools`, so the install writes nowhere else. Updates and
  telemetry are off during the install and during turns.
- **Mind:** `.jcode` — jcode's sessions, config, MCP config and logs.

## What it needs from the image and the provider

The default image already has what it needs: `bash`, `curl`, `tar`, `sha256sum` for the install, and
`python3` for `run`. jcode's release binary is a glibc build; the release archive carries the launcher
and binary it needs. No root is needed.

The request names the provider and model; the package configures jcode for the provider API the turn was
given (`HG_PROVIDER_API`):

| API | How jcode is told |
|---|---|
| `anthropic` | native Anthropic runtime: `ANTHROPIC_API_KEY` = the placeholder, `ANTHROPIC_BASE_URL` / `JCODE_ANTHROPIC_API_BASE` = `HG_PROVIDER_URL` + `/v1`, model in `JCODE_ANTHROPIC_MODEL`. No `--model`, so an arbitrary provider model id is not checked against jcode's built-in Anthropic list. |
| `openai-chat` | a named `[providers.harness]` profile of type `openai-compatible` in `$JCODE_HOME/config.toml`; `--provider-profile harness --model <model>`. Chat completions are sent to `HG_PROVIDER_URL` (`/chat/completions` is appended). |
| `openai-responses` | native OpenAI runtime: `--provider openai-api`, `JCODE_OPENAI_API_BASE` / `OPENAI_BASE_URL` = `HG_PROVIDER_URL`, `OPENAI_API_KEY` = the placeholder, model in `JCODE_OPENAI_MODEL`. `/responses` is appended. Because that runtime silently substitutes its default for a model it does not know, `run` also declares the turn's model in jcode's model-catalogue cache; if jcode still runs a different model the turn fails with `model_mismatch`. |
| `gemini` | native Gemini runtime: `--provider gemini`, `GEMINI_API_ENDPOINT` = `HG_PROVIDER_URL`, `GEMINI_API_VERSION=v1beta`, `GEMINI_API_KEY` = the placeholder, model in `JCODE_GEMINI_MODEL`. |

The provider's key is never in the package or in a file: jcode receives `$HG_PROVIDER_KEY`, whose real
value the platform's proxy substitutes on the way to the provider's host.

`HG_PROVIDER_URL` is used as given for the OpenAI APIs (which end in `/v1`) and for Gemini (which ends
before `/v1beta`); for Anthropic, `/v1` is appended because jcode appends `/messages`.

## The command

`run` writes the turn's provider profile into `$JCODE_HOME/config.toml` and the request's MCP servers into
`$JCODE_HOME/mcp.json`, then runs:

```
jcode --quiet --no-update --no-selfdev --socket /tmp/jcode.sock [--resume <id>] <provider flags> run --ndjson "<brief>"
```

- `--quiet --no-update --no-selfdev` — wrapper mode as jcode's own `docs/WRAPPERS.md` recommends.
- `JCODE_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`, `JCODE_DISABLE_PRICING_REFRESH=1` — no telemetry, no
  models.dev catalogue fetch.
- `JCODE_RUN_AUTO_POKE=0` — one turn, not jcode's extra self-review turns.
- `JCODE_DISABLE_CLAUDE_MCP=1` — the request's `mcp` tools are the whole set; another harness's
  `.claude.json` in the mind is not read.
- `JCODE_HOME=$HOME/.jcode` — everything the CLI writes stays in the mind.

The CLI's standard error is copied to `run`'s standard error (the turn's log) after it exits; its last
line is used in a failed turn's message.

## Request fields

| In the request | Where it goes |
|---|---|
| `input` text, `instructions`, handover, files | `hgkit.Request.brief()` as the one prompt argument: handover line, instructions, the paths of files placed in `inputs/`, then the prompt. jcode has no system-prompt flag, so instructions are at the front of the prompt. |
| `input_file` / `input_image` parts | `request.place_files()` puts them in `inputs/` in the work folder and the brief names them; jcode opens them with its file and image tools. |
| `model` | The provider's model settings above. Every model the CLI asks for is this one. |
| the provider's base URL and key | The variables in the table above. |
| `reasoning.effort` | `[provider] anthropic_reasoning_effort` (Anthropic) or `openai_reasoning_effort` (OpenAI APIs/compatible) in `config.toml`. The Gemini runtime has no effort setting, so it is ignored there. |
| `tools` of type `mcp` | `$JCODE_HOME/mcp.json` as HTTP servers: `{"mcpServers": {<label>: {"type": "http", "url": <server_url>, "headers": …}}}`. A server's `allowed_tools` has no jcode equivalent and is not enforced by the package. |
| `text.format`, `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`, `parallel_tool_calls` | Not honoured: jcode has no option for them in headless mode. They are left alone (not failed on) and do not change what the caller gets. |
| `previous_response_id`, `stream`, `background`, `store` | The platform's; the package does not see or act on them. |

## What is printed for what jcode does

`run` translates jcode's `--ndjson` lines, one event per thing:

| jcode line | Printed as |
|---|---|
| `text_delta` | a streamed `message` (`response.output_text.delta`) |
| `tool_start` / `tool_input` / `tool_done` for `bash` | `shell_call`, then `shell_call_output`. jcode merges stdout and stderr in its tool output and ends it with `--- Command finished with exit code: N ---` or `Exit code: N`; the trailer is stripped and the code put in the outcome, the text in `stdout`. |
| `write` | `apply_patch_call` with `create_file` (the file's contents as a `+` diff) |
| `edit` | `apply_patch_call` with `update_file` (each edit's old/new strings as a `-`/`+` diff) |
| `apply_patch` | one `create_file` / `update_file` / `delete_file` per file when the patch is a Codex-style `*** Add/Update/Delete File:` patch; otherwise a `custom_tool_call` |
| `mcp__<server>__<tool>` | `mcp_call`, with its arguments and output (or error) |
| any other tool (`read`, `webfetch`, `websearch`, `todo`, …) | `custom_tool_call`, then `custom_tool_call_output` |
| `tokens` | counted for the terminal line's `usage` (see below) |
| `start`, `session` | the CLI's session id, saved with `state.set` the moment it arrives |
| `done` | `hg.done` (or `hg.incomplete` if the last `message_end` said `max_tokens`/`length` or `content_filter`/`refusal`) |
| `error` | `hg.failed` with `code: provider_error` and jcode's message |
| a CLI that exits without `done` or `error` | `hg.failed` with `code: cli_exit`, the exit code and the last line of its standard error |
| `connection_type`, `connection_phase`, `service_tier`, `status_detail`, `upstream_provider`, `compaction`, `memory_injected`, auto-poke notices | the turn's log or nothing; they are not things the agent did |

`text_replace` and `text_suffix_replace` (stream corrections, which this CLI did not emit in any trial)
are noted in the turn's log; the Responses stream has no way to retract text already sent, so a correction
is recorded rather than rewinding the message.

## Token usage

jcode reports a `tokens` line per provider request (`input`, `output`, `cache_read_input`,
`cache_creation_input`), usually twice with the same numbers, and a final `done` whose `usage` covers only
the last request. `run` keeps one count per request — a new request starts at a `connection_phase` of
`sending request` — and sums them for the turn. `input_tokens` is
`input + cache_read_input + cache_creation_input` (the Responses shape counts cached input), and
`input_tokens_details.cached_tokens` is the sum of `cache_read_input`. A turn that calls tools therefore
accounts for every request it made, not just the last one. A turn that fails before any request carries
zeroes.

## Sessions

jcode stores sessions under `$JCODE_HOME/sessions` (in the mind). The `session_id` in its `start` line is
saved immediately; the next turn continues with `jcode --resume <id> ... run`. When a resume fails before
the CLI starts (the session is gone or unusable), `run` notes it in the turn's log, clears the id and runs
the turn again as a new session. A stopped turn is stopped by the kit together with everything the CLI
started; its session was already saved, so the next turn picks it up (the trial's stop-and-continue passed).

## Hosts an environment must allow

**Install:** `github.com`, `raw.githubusercontent.com`, `release-assets.githubusercontent.com` — all in
the platform's install registries, so no `setup.egress` entry is needed for this package.

**Turns:**

| Host | Why | Needed? |
|---|---|---|
| the provider's host (`HG_PROVIDER_URL`) | the model requests | yes — the environment's provider binding supplies it |
| `api.anthropic.com` | jcode's Anthropic runtime prewarms a usage/cost lookup when it starts | no — observed refused, and the turn completed normally. Allow it only if you want jcode's usage display. |
| `models.dev` | jcode's live model-pricing catalogue | no — `JCODE_DISABLE_PRICING_REFRESH=1` keeps it from being asked |
| the hosts of the request's `mcp` servers | those tools | only when the request sends MCP servers |

The manifest names no host; the environment decides.

## Operator

Nothing to set in the package: no settings, no secrets, no image beyond the default. An environment must
carry the harness; a request names it as `<environment>/jcode/<provider>/<model>`.

## What was tried, and what was not

Tried against a real provider (Anthropic Messages API): text turns, a turn that wrote a file and ran a
command, a resumed turn, a turn stopped with SIGTERM and the turn that continued it, a provider error
(a model the provider rejects), and `instructions` reaching the prompt. The platform's checker passes all
recorded cases.

Not tried here: the `openai-chat`, `openai-responses` and `gemini` mappings (this build session's provider
speaks Anthropic, and the sandbox would not reach a local stand-in server); an MCP server (none was
available); uploaded files and images; and a stop that had already streamed text (the recorded stop
happened before the first delta). They are implemented from the CLI's own documented variables and
`--help`, and should be tried in an environment whose provider speaks that API.
