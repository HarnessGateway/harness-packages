# Grok Build (`grok`)

A vanilla harness package for **Grok Build**, xAI's terminal coding agent, as its makers ship it. It pins
Grok Build **1.0.89** and runs one headless turn per request with `--output-format streaming-json`, translating
that stream into OpenAI Responses events. There is no purpose, ruleset or permission policy of its own: the
request's provider, model, instructions and MCP servers are what the turn gets.

- Upstream: <https://github.com/xai-org/grok-build> (Rust source; this package installs the released binary)
- Documentation: <https://docs.x.ai/build/overview>
- Package version: `1.0.89-1`

## What it needs

**Image.** `curl`, `bash`, `awk`, `uname` and the usual coreutils, plus `python3` for `run`. The install
downloads the makers' prebuilt Linux binary; neither `install` nor the manifest names a CPU architecture — the
installer picks the build for the machine.

**Install network.** Grok Build's installer is fetched from, and the binary downloaded from, **`x.ai`**. If
`x.ai` cannot be reached the installer falls back to **`storage.googleapis.com`**. Neither is on the platform's
registry list, so an environment that carries this harness must allow them for the install stage:

```json
"setup": { "egress": ["x.ai", "storage.googleapis.com"] }
```

Only `x.ai` was asked for in the trial (12 requests); the fallback is the installer's own documented behaviour.

**Provider.** The CLI is configured for whichever of the manifest's APIs the turn is given:

| `HG_PROVIDER_API` | Grok `api_backend` | Base URL used |
|---|---|---|
| `openai-chat` | `chat_completions` (the CLI's default) | `HG_PROVIDER_URL` (ends in `/v1`) |
| `openai-responses` | `responses` | `HG_PROVIDER_URL` (ends in `/v1`) |
| `anthropic` | `messages` | `HG_PROVIDER_URL` + `/v1` (the platform's Anthropic form has no `/v1`) |

The key is `HG_PROVIDER_KEY`, passed as the model's `env_key`; for the Messages API it is also put in the
`x-api-key` header from that same variable. It is the platform's placeholder and the proxy substitutes the real
key on the way out. Grok also sends its usual `Authorization: Bearer` header on the Messages backend; Anthropic
ignores it.

**Operator settings.** None. The package declares no settings and no secrets. An environment must carry the
harness, and its provider must offer at least one API in the manifest. Nothing else has to be set.

## The CLI's command

`run` writes `$HOME/.grok/config.toml` from the turn's request (see below), then starts:

```
$HG_HARNESS/tools/bin/grok \
    --prompt-file <the turn's brief> \
    -m harness-model \
    --output-format streaming-json \
    --yolo --no-auto-update \
    (-s <new UUID> | -r <stored session id>) \
    [--rules <instructions>] [--reasoning-effort <effort>] [--json-schema <schema>]
```

with `HOME=/mind` and the working directory `/work`. `--yolo` is the CLI's always-approve mode
(`bypassPermissions`), which is what a headless turn needs. `GROK_DISABLE_AUTOUPDATER=1` and
`[cli] auto_update = false` suppress the update check; `[features] telemetry = false` turns product telemetry
off. The session's files, including `config.toml`, live in `~/.grok` under the mind.

`config.toml` is rewritten on every turn from the request. It defines one model entry, `harness-model`:

```toml
[model.harness-model]
model = "<HG_MODEL>"
base_url = "<the provider's URL for this API>"
name = "<HG_MODEL>"
api_backend = "messages" | "responses" | "chat_completions"
env_key = "HG_PROVIDER_KEY"
context_window = 200000
# messages: env_http_headers = { "x-api-key" = "HG_PROVIDER_KEY" }
#           extra_headers = { "anthropic-version" = "2023-06-01" }
```

plus `max_completion_tokens`, `temperature` and `top_p` when the request carries them, and one
`[mcp_servers.<label>]` block per MCP server the request names. Any change the CLI makes to this file itself
(for example its `[marketplace]` marker) is replaced on the next turn. The model's context window is declared
as 200000 because Grok's custom-model config requires a value; the provider's real limit is not known to the
package.

## Request fields

| In the request | Where it goes |
|---|---|
| `input` (string or messages) | `request.brief(instructions=False)`, written to a temporary file and passed as `--prompt-file`. Grok's headless mode does not read the prompt from stdin. |
| `instructions` | `--rules`, which Grok appends to a **new** session's system prompt. Grok ignores `--rules` on a resumed session, so on a continuation the package also puts them in front of the prompt. |
| `input_file`, `input_image` (by id or inline) | `request.brief()` places them in `/work/inputs/` and names them in the prompt. They are not attached as native content blocks; the agent opens them with its file tools. Images are only named, not shown to a vision model. |
| the handover | In front of the prompt, through `request.brief()`. |
| `model` (`HG_MODEL`) | The `model` of `[model.harness-model]`; every model call in the session uses that entry. |
| provider URL / key | `base_url`, `env_key` and the Messages `x-api-key` header, as above. |
| `reasoning.effort` | `--reasoning-effort`, when it is one of `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. Other values are left out. |
| `tools` of type `mcp` | One `[mcp_servers.<label>]` block: `url` from `server_url`, `headers` from `headers`. `allowed_tools` and other fields are not mapped. |
| `text.format` with `type: json_schema` | `--json-schema`, with the request's `schema`. |
| `max_output_tokens` | `max_completion_tokens` of the model entry. |
| `temperature`, `top_p` | The model entry's fields. |
| `max_tool_calls`, `max_turns`, `truncation`, `user`, `metadata`, other `text.format` types | Not mapped. Grok has `--max-turns`, but it is a different counter from `max_tool_calls`, so the package does not guess. |
| `previous_response_id`, `stream`, `background`, `store` | The platform's. Continuation comes from the CLI's own session in the mind. |

## What is printed

| Grok Build's stream | Responses events |
|---|---|
| `text` | one `message` with `output_text` deltas (streamed as they arrive) |
| `thought` | one `reasoning` item with `summary_text` deltas |
| a `tool_call` whose tool is `run_terminal_command` / `bash` (kind `execute`) | `shell_call`, then `shell_call_output` with stdout and the exit code |
| a `write` (kind `write`) | `apply_patch_call` `create_file`, then `apply_patch_call_output` |
| `search_replace` / `edit` / `apply_patch` (kind `edit`) | `apply_patch_call` `update_file`, then its output |
| a delete tool | `apply_patch_call` `delete_file` |
| an MCP call — Grok routes these through its `use_tool` meta-tool, naming the target `server__tool` | one `mcp_call` with the server label, tool name and arguments |
| any other tool (`read_file`, `list_dir`, `grep`, `todo_write`, `spawn_subagent`, `web_search`, …) | `custom_tool_call`, then `custom_tool_call_output` |
| `plan`, `max_turns_reached`, unknown lines | `hg.log` (not shown to the caller) |
| `available_commands`, `usage` | ignored (the turn's tokens come from `end`) |
| `error` | one `hg.failed` with the provider's message, unwrapped from the CLI's `Internal error:` JSON |

The `end` line's `stopReason` decides the terminal line:

- `end_turn`, `max_turn_requests` → `hg.done` (the latter also writes a log line);
- `max_tokens` → `hg.incomplete("max_output_tokens")`;
- `refusal` → `hg.incomplete("content_filter")`;
- `cancelled` → `hg.failed("cancelled", …)`;
- anything else → `hg.done`, with the reason in the log.

A CLI that exits without an `end` or `error` line is `hg.failed("cli_exit", …)` with its exit code. A stopped
turn prints no terminal line, as the contract requires.

## Token usage

The terminal line's `usage` comes from the **`end` line's `usage` object**, which is the turn's aggregate
(reported by the CLI in both `streaming-json` and `json` output). Grok reports the buckets disjoint, so the
package reports:

```
input_tokens  = usage.input_tokens + cache_read_input_tokens + cache_creation_input_tokens
output_tokens = usage.output_tokens
input_tokens_details.cached_tokens = cache_read_input_tokens
```

That is the whole input, cached reads and cache writes included, as `events.md` asks. Per-response `usage`
lines were looked at and not used: they are per model response, not the turn. `grok usage` and the `json`
output format were also looked at; the `end` aggregate is the same ledger and is already on the stream.

When the provider rejects the prompt before any model call (a bad model name, for example), the CLI emits
`error` with no spend fields and the terminal line carries no `usage`; there are no tokens to report. The
`failed` test case shows that shape.

## Sessions

Grok Build keeps its sessions under `~/.grok/sessions` (the mind; the manifest's `mind` is `.grok`). On the
first turn the package chooses the session UUID itself, saves it in `$HG_STATE/session` **before** starting the
CLI, and starts the CLI with `-s <UUID>`. Every later turn resumes with `-r <UUID>`, so a turn that was stopped
is continued even though a stopped run prints no `end` line. `end.sessionId` is also saved whenever it is seen.

If a resume fails — Grok says `No session found with ID …` or `Session does not exist: …` — and the attempt
printed no text or tool output, `run` clears the stored id, logs it, and runs the turn again as a new session.

The CLI's session store also includes a SQLite search index and its own logs. `.grok/logs` is not saved with the
session (the manifest's `cache`); everything else the CLI writes is the session itself or its unpacked
documentation (about 1.1 MB).

## Hosts

| Stage | Hosts | Why |
|---|---|---|
| install | `x.ai` | the makers' `install.sh` and the pinned binary |
| install, only if `x.ai` is unreachable | `storage.googleapis.com` | the installer's documented fallback |
| turn | the provider's host and no other | the model call; in the trial this was `api.deepseek.com` |

Every other host is the environment's decision. If a request names MCP servers, **their hosts** must be allowed
for the turn or those tools fail. Grok's web search and web fetch tools reach hosts of their own; they were not
exercised here, so the environment must allow whatever such a tool is expected to reach if callers are to use
it. The package itself names no host and adds nothing to the environment's network.

## What could not be tried here

- **Only the `anthropic` (Messages) backend** was exercised, because this build session's provider speaks it.
  The `openai-chat` and `openai-responses` configurations were written from the CLI's documented model config
  and the sampler's URL construction but not run against a provider.
- **MCP servers.** The config block is generated and validated by TOML parsing (`grok inspect`), but no MCP
  server was reachable or configured, so an actual `mcp_call`, including Grok's `server__tool` routing through
  `use_tool`, was not observed end to end.
- **File and image inputs.** `request.brief()` placement is the kit's and was not exercised with a request that
  carries files; images are named, not attached.
- **Structured output** (`--json-schema`), `--reasoning-effort` beyond `medium`, and **subagents** were not
  exercised.
- **Web search / web fetch** hosts were not observed.
- **Stop grace.** One stopped turn (`sleep 120`, stopped after 8 s) ended well within the 20 s
  `run.stop_grace_s` and the next turn continued the session; longer shutdowns were not tried.

## Files

| File | |
|---|---|
| `harness.json` | manifest; `mind` is `.grok`, `apis` are `openai-chat`, `openai-responses`, `anthropic` |
| `install` | fetches the makers' installer, pins 1.0.89, verifies `grok --version` |
| `run` | one turn: writes the model config, starts the CLI, translates `streaming-json` |
| `tests/hello` | a text-only turn |
| `tests/command` | a file write and a shell command |
| `tests/resumed` | the turn after `command`, continued in the same CLI session |
| `tests/failed` | a provider error (`HG_MODEL=no-such-model`), with no tokens to report |
