# zeroclaw

ZeroClaw 0.9.0 — the single-binary personal AI agent runtime from
[zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw) — run headless through its own ACP server.

This is the CLI as its makers ship it, not a customized agent: no instructions, no extra tools, no opinion
about the work. The only configuration written is what a headless turn needs to reach the request's provider
and act without an operator.

## What it needs

- **Image:** Linux, with `curl`, `tar` and `sha256sum` for `install`, and Python 3 for `run` (all in the default
  image). The installed ZeroClaw binary is statically linked against the image's libc (glibc or musl).
  Node.js and Rust are not needed.
- **Provider:** one of the three APIs in the manifest, reached through the platform's proxy with
  `HG_PROVIDER_URL` and the placeholder key. All three were tried against this session's provider.
- **Install:** the makers' pre-built release archive for `v0.9.0`, from
  `github.com/zeroclaw-labs/zeroclaw/releases`, checked against the release's `SHA256SUMS`, installed at
  `$HG_HARNESS/tools/bin/zeroclaw`. The version is checked with `zeroclaw --version`. Only x86_64 Linux
  (glibc) was tried; the installer also names the makers' aarch64 and arm Linux archives.

## The CLI's command

```
zeroclaw --config-dir $HOME/.zeroclaw acp --agent zeroclaw
```

`acp` is ZeroClaw's machine-readable headless face: JSON-RPC 2.0, newline-delimited, on stdin/stdout. The
package sends `initialize`, `session/resume` (when the mind holds a session), `session/new`, and
`session/prompt`, then translates `session/update` notifications as they arrive. `zeroclaw agent -m` is the
other single-shot path, but it prints prose for a person, not a stream.

The configuration is written to `$HOME/.zeroclaw/config.toml` at the start of every turn:

- a `[providers.models.<type>.hg]` entry for the request's provider URL and model (`anthropic`, or `openai`
  with `wire_api = "responses"` / `"chat_completions"`), with the key passed as the environment override
  `ZEROCLAW_providers__models__<type>__hg__api_key` so no key or placeholder is written to disk;
- one `[agents.zeroclaw]`, a `[risk_profiles.unattended]` and a `[runtime_profiles.unattended]` entry;
- `[[mcp.servers]]` entries and a bundle when the request carries MCP tools.

### Autonomy, and what it costs

A headless turn has no operator to answer ZeroClaw's approval prompts, so the package runs the agent at
ZeroClaw's documented `full` autonomy level and turns off the CLI's own command and path gates:
`workspace_only = false`, `sandbox_enabled = false`, `block_high_risk_commands = false`,
`allowed_commands = ["*"]`, `forbidden_paths = []`. ZeroClaw's OS sandbox is not used because the platform's
sandbox — the environment's network rules, the read-only `/harness`, and the session's `/mind` and `/work` —
is the boundary around the turn. An operator who wants stricter rules should use a tailored package, not this
one.

## Request fields

| In the request | What happens |
|---|---|
| `input` (string, or message list) | `request.brief()`: the user text, with files placed and named |
| `input_file`, `input_image` (file id or inline) | written to `inputs/` in the work folder and named in the prompt. ACP advertises `image: false`, so images are not sent as image blocks; they are only files the agent may read |
| `instructions` | put in front of the prompt (ACP's `session/new` has no system-prompt parameter) |
| handover line | put in front of the prompt by `request.brief()` |
| `request.history` | not used beyond what the handover line says |
| `model` (`HG_MODEL`) | the provider entry's `model` |
| provider URL / key | provider entry's `uri`; key as the environment override |
| `reasoning.effort` | `[runtime] reasoning_effort`, when it is one ZeroClaw accepts (`minimal`, `low`, `medium`, `high`, `xhigh`) |
| `max_output_tokens` | the provider entry's `max_tokens` |
| `temperature` | the provider entry's `temperature` |
| `tools` of type `mcp` | `[[mcp.servers]]` entries (`transport = "http"`, `url`, `headers`), granted to the agent through a bundle. Not tried end to end here |
| `previous_response_id`, `stream`, `background`, `store` | the platform's; the mind and work are restored, and the CLI's own session is resumed |
| `text.format`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | not honoured; ZeroClaw's ACP prompt has no equivalent |

Tools of any type other than `mcp` never reach the package: the platform refuses the request.

## What is printed for what the CLI does

| ZeroClaw | Printed |
|---|---|
| `agent_message_chunk` | `emit.say` — one streamed `message` |
| `agent_thought_chunk` | `emit.think` — one streamed `reasoning` item |
| `shell` tool call, then `tool_call_update` | `emit.ran`: `shell_call`, then `shell_call_output`. ACP carries no exit code, so a successful command is exit 0 and a failed one (`status: failed`, or ZeroClaw's `Error: ` prefix) is exit 1 |
| `file_write` (completed) | `emit.wrote`: `apply_patch_call` `create_file`, diff from `newText` |
| `file_edit` (completed) | `emit.edited`: `apply_patch_call` `update_file`, diff from `oldText` / `newText` |
| `file_delete` / `file_remove` (completed) | `emit.deleted` |
| an MCP tool `<server>__<tool>` | `emit.called`: one `mcp_call` |
| any other tool (`file_read`, `glob_search`, `web_fetch`, `deliver_file`, …) | `emit.used`: `custom_tool_call`, then `custom_tool_call_output` |
| a failed file tool | `emit.used` with the error text, so no file is claimed to have been written |
| a CLI line that is not JSON | `emit.log` |

A turn ends with exactly one terminal line: `hg.done` for `stopReason: end_turn`; `hg.incomplete` with
`max_output_tokens` for `max_tokens`, or `content_filter` for a refusal; `hg.failed` with `provider_error` when
ZeroClaw reports a provider failure, or `cli_exit` when the CLI ends before answering. A stopped turn prints no
terminal line: `run` sends SIGTERM to the CLI's process group and exits.

## Token usage

ZeroClaw does not put token counts in its ACP stream. It appends one record per model call to
`$HOME/.zeroclaw/data/state/costs.jsonl` (`conversation_id` is the ACP session), with `input_tokens`,
`output_tokens` and `cached_input_tokens`. The package records the file's size before the prompt, sums the
records appended during the turn, and puts them on the terminal line as the Responses `usage` object
(`cached_input_tokens` becomes `input_tokens_details.cached_tokens`). A provider failure before any model call
has no usage to report.

Under `harnessgateway package check`, a recording carries only the CLI's ACP stdout, so the replayed turn has no
cost record and its recorded `expected.jsonl` terminal line has no `usage`. Live turns do.

Other places looked at: the ACP `session/prompt` result (no usage in protocol v1), the ACP session SQLite
`token_count` (a context-size snapshot, not a turn's input/output counts), and ZeroClaw's runtime trace logs
(no per-turn counts).

## Sessions

The ACP server persists sessions in `$HOME/.zeroclaw/data/sessions/acp-sessions.db`, under the mind. The
session id from `session/new` is saved with `state.set("session", …)` immediately, before the prompt. The next
turn calls `session/resume` with it. If the store says the session is gone, the package logs it, clears the
state, and starts a new session. A stopped turn leaves the partial conversation in the store, and the next turn
continues it (tried with `--stop-after`, then a question about where it stopped).

The work folder is the ACP session's `cwd`, so ZeroClaw's file and shell tools are rooted at `/work`. The
agent's own workspace (`$HOME/.zeroclaw/agents/zeroclaw/workspace`) holds its identity files and stays in the
mind.

### What the mind holds

After a turn: `config.toml` (mode 600, rewritten each turn), `data/sessions/` (the ACP session store),
`data/memory/brain.db`, `data/state/` (small logs, including the cost records), and `agents/zeroclaw/workspace/`
(the CLI's default identity files). About 0.3 MB after a short session; no download cache or unpacked
libraries are created, so no `cache` entry is declared.

## Hosts an environment must allow

Observed:

- `github.com` and `release-assets.githubusercontent.com` — the install's release download. Both are in the
  platform's registries, so an install reaches them whatever the environment's network.
- the provider's host — from `HG_PROVIDER_URL`, through the platform's proxy.

Beyond the registries and the provider, no host was asked for. A turn adds none of its own: ZeroClaw's update
check and gateway are not started by `acp`. A request that carries MCP tools names servers, and those servers'
hosts are the request's to allow; none was tried here.

## What an operator must set

Nothing on the package: it has no settings or secrets. The environment must carry the harness and offer the
provider named in the request; the platform supplies `HG_PROVIDER_URL`, the placeholder key and the model. If
requests carry MCP tools, the environment must allow those servers' hosts.

## What was tried, and what was not

Tried against this session's provider: a text-only turn; a turn that created and ran `hello.py`; a resumed
turn; a turn the provider failed (a model that does not exist); a turn stopped with `--stop-after` and the turn
after it; recovery when the session store was removed; the Anthropic, OpenAI chat-completions and OpenAI
Responses provider forms; `instructions` reaching the model.

Not tried: MCP tools end to end (the configuration is written and validates, but no server was called);
image input (ACP advertises `image: false`); providers other than this session's; Linux targets other than
x86_64 glibc; a stop during a tool call (a stop during streamed text ended cleanly in under a second).
