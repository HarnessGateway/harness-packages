# cheetahclaws

CheetahClaws (`cheetahclaws` on PyPI), the CLI as its makers ship it, run headless: one turn per Responses
request, with the CLI's own tools, session store and JSONL event stream.

Package version `3.5.90-1`; it installs CheetahClaws **3.5.90**.

## What it needs

- **Image:** Python 3.10 or later with `venv` and `pip`. The platform's default image has it; nothing else is
  installed with root or system-wide. CheetahClaws' core dependencies come from PyPI with the CLI.
- **Provider:** one that offers the **Anthropic Messages API** or an **OpenAI Chat Completions** endpoint.
  `harness.json` lists `["anthropic", "openai-chat"]`, in that order, so a provider offering both is spoken to
  with the Anthropic API; a provider offering only the OpenAI-compatible one is spoken to that way. The Gemini
  API and OpenAI's Responses API are not declared: the CLI has no native client for them.

## Install

`install` creates `$HG_HARNESS/tools/venv` and runs `pip install cheetahclaws==3.5.90` into it, by the makers'
documented method. It then runs `cheetahclaws --version` and fails if the version is not 3.5.90. It names no
CPU architecture. The install asked for `pypi.org` and `files.pythonhosted.org` only — both package-manager
hosts the platform always allows.

## The command

```
$HG_HARNESS/tools/venv/bin/cheetahclaws -p --output-format stream-json \
    --permission-mode accept-all --model <provider>/<model> [--resume <session id>]
```

The turn's brief (the handover line, the request's instructions, the placed files, then the prompt) is written
to the CLI's standard input. `--permission-mode accept-all` is what makes one headless run carry a whole task
through: nobody is at the terminal to answer an approval prompt, and without it every tool that would normally
ask is denied.

The package does **not** pass `--trust-workspace`, so a repository's `.mcp.json` servers, project plugins and
project hooks are not loaded; the CLI reports them as skipped and the package writes that to the turn log with
`hg.log`. Project instruction files (`AGENTS.md`, `CLAUDE.md`, `.cheetahclaws/INSTRUCTIONS.md`) are loaded as
the CLI normally loads them.

`<provider>/<model>` is `anthropic/<HG_MODEL>` when the turn speaks the Anthropic API (with
`ANTHROPIC_ENDPOINT=HG_PROVIDER_URL`, `ANTHROPIC_API_KEY=HG_PROVIDER_KEY`), and `custom/<HG_MODEL>` when it
speaks the OpenAI-compatible one (with `CUSTOM_BASE_URL=HG_PROVIDER_URL`, `CUSTOM_API_KEY=HG_PROVIDER_KEY`).
The key is the platform's placeholder; the proxy puts the real key in on the way out.

## The request, onto the CLI

| In the request | What the package does |
|---|---|
| `input` (a string, or a list of messages) | The user text is the prompt; `request.brief()` joins it. |
| `instructions` | Put in front of the prompt as "Instructions for this request:". CheetahClaws has no system-prompt option. |
| `input_file`, `input_image` parts | `request.place_files()` puts them under `inputs/` in the work folder and the brief names them. Images are files the agent must open; the CLI's image reader needs the `vision` extra, which this package does not install. |
| `model` | Passed as `<provider>/<HG_MODEL>`; the prefix selects the CLI's provider while the provider receives exactly `HG_MODEL`. |
| the provider's URL and key | The CLI's environment variables above. |
| `tools` of type `mcp` | Written to `~/.cheetahclaws/mcp.json` as HTTP servers (label → URL, with headers), the file CheetahClaws reads. |
| the handover line | In front of the prompt, through `request.brief()`. |
| `previous_response_id` | Nothing: the platform already restored the mind and work folder. The CLI's own session id from `hgkit.State` is resumed. |
| `stream`, `background`, `store` | The platform's; the package always streams as events arrive. |
| `reasoning.effort` | Not honoured: CheetahClaws' headless mode has no effort flag. |
| `text.format`, `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | Not honoured: no headless flag for them. The CLI keeps its own defaults (`max_tokens` 40,000 output tokens). |
| `tools` of type `mcp`: `allowed_tools` | Not supported per server; all of a connected server's tools are offered. The package says so once with `hg.log`. |

## What each thing the CLI does becomes

The CLI prints one JSON object per line (`--output-format stream-json`). The package translates:

| CheetahClaws event | Printed as |
|---|---|
| `assistant_delta` (text) | streamed `message` text (`response.output_text.delta`) |
| `assistant_message` text that did not arrive in deltas | a `message` item |
| `Bash` call + result | `shell_call`, then `shell_call_output` |
| `Write` call + result | `apply_patch_call` with `create_file` |
| `Edit` / `MultiEdit` call + result | `apply_patch_call` with `update_file` (`-`/`+` diff) |
| `ApplyPatch` call + result | one `create_file`/`update_file`/`delete_file` per file in the patch |
| `mcp__<server>__<tool>` call + result | one `mcp_call` |
| any other tool (`Read`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `Agent`, …) | `custom_tool_call`, then `custom_tool_call_output` |
| `error` | `hg.log`, and the message of `hg.failed` |
| `result` | the terminal line |

Not printed: `session_start`, `user_message`, `usage`, `permission_decision`, `notice`, `compaction`, `hook`,
`session_end` (a notice or denial is put in the turn log with `hg.log`). Events tagged with a sub-agent's
`depth` are skipped: the parent's `Agent` tool call and its result already say what the sub-agent did.

Notes on the translation:

- CheetahClaws' Bash tool returns **combined stdout+stderr and no exit code**. `shell_call_output` therefore
  carries the whole output as `stdout`, and `exit_code` is 0 unless the CLI reported the call as an error
  (`is_error`), in which case it is 1. A command that exits non-zero without the CLI flagging it still shows
  its output, with exit code 0.
- The CLI's event log truncates a tool result to 4,000 characters before it reaches this package, so the
  output items carry that truncation (the model itself sees more).
- A tool call that failed is still printed, with its error text: file-tool failures fall back to
  `custom_tool_call`, and a failed MCP call carries `error`.

## The end of a turn

`hg.done` when the CLI's `result` event says `exit_reason: completed`. Otherwise `hg.failed` with a code from
the CLI's reason: `provider_error` (`api_error`), `cli_error`, `max_turns`, `permission_denied`, `quota`,
`hook_blocked`, `interrupted`, `cancelled`; the message is the CLI's own `error` message and hint, so it says
what a person can act on. A CLI that exits without a `result` is `hg.failed` / `cli_exit` with its exit code.

### Token usage

The CLI's `result` event carries the run's `usage`: `input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_write_tokens`. The terminal line uses them:

- on the Anthropic API, `input_tokens` is reported without cache reads/writes, so the package adds both in and
  puts the cache reads in `input_tokens_details.cached_tokens` (the Responses usage counts all input);
- on the OpenAI-compatible API, `prompt_tokens` already includes cached tokens, so only
  `input_tokens_details.cached_tokens` is filled from `cache_read_tokens`.

A provider failure before any model call reports zeros, as the CLI does.

## Sessions and stopping

- The CLI reports its session id in `session_start`; the package saves it with `state.set("session", id)` at
  that moment. Its store lives under `$HOME/.cheetahclaws` (`sessions.db`, plus
  `sessions/<id>/events.jsonl`), which is the session's mind and comes back with it.
- Next turn it runs `--resume <id>`. If the CLI says that session is gone (exit 1, no event), the package logs
  it, clears the state and runs the turn as a new session.
- **A stopped turn is continued.** The CLI itself writes its session only when it reaches its `result`, so a
  killed run would otherwise lose the turn. When the platform stops this package, it catches the stop, and
  writes the run's event stream — the prior transcript plus the user message, the streamed text so far, and
  "interrupted" results for any tool calls still open — into the CLI's session store before ending. It prints
  no terminal line, as a stopped turn must. The next turn's `--resume` then sees the conversation and how far
  it got. This was tried with `--stop-after`: a count stopped mid-answer, and the next turn answered "where
  did you stop?" with the actual number.

CheetahClaws also writes a quota file (`quota/YYYY-MM-DD.json`) beside its sessions; together the mind stays
small (well under 1 MB in the trials), so no `cache` entry is declared.

## MCP servers

A request's `tools` of type `mcp` become `~/.cheetahclaws/mcp.json` entries of type `http` (the CLI's
streamable-HTTP transport) for that turn; an empty request rewrites the file with no servers, so one turn's
servers do not leak into the next. Their hosts must be allowed by the environment (`network.allow`); they are
not reached through the install. This was tried against a local streamable-HTTP MCP server: the tool was
offered as `mcp__echo__echo`, its call arrived as `mcp_call`, and its text came back. A server that answers
only `application/json` (rather than `text/event-stream`) is not readable by this CLI version's MCP client.
CheetahClaws connects its MCP servers in a background thread at startup, so a server that takes longer to
answer than the CLI's own startup may not be in the tool surface offered to the first model call.

## Hosts an environment must allow

The install asked for `pypi.org` and `files.pythonhosted.org`; both are package-manager hosts every install
can reach.

The recorded turns asked for the provider host only — `api.deepseek.com` in the trials, which is the provider
and is always reachable. **No other host was asked for**, so this package needs no `network.allow` entry and no
`setup.egress` entry beyond the provider.

That is what the trials saw, not a guarantee about the agent: if the agent chooses `WebFetch`, `WebSearch`,
`Research`, a remote MCP server, or a command that uses the network, those hosts are the environment's to
allow (or refuse). The manifest names none, as the contract requires.

## What an operator must set

Nothing mandatory: no settings and no secrets are declared. The environment must

- have an image with Python 3.10+ and its `venv` module (the default image does);
- carry the harness, and the request names it as `<environment>/cheetahclaws/<provider>/<model>`;
- allow the provider host (the platform does) and any extra host the work is meant to use.

## What could not be tried here

- The **OpenAI-chat** path: this session's provider offers the Anthropic API, which the package used. The
  mapping is `custom/<model>` + `CUSTOM_BASE_URL`/`CUSTOM_API_KEY`; it was not exercised against a real
  OpenAI-compatible provider.
- A **remote authenticated MCP server**; only a local streamable-HTTP echo server.
- **Images/vision**: the CLI's `vision` extra (Pillow) is not installed, so an `input_image` is placed and
  named as a file but not read as an image.
- CheetahClaws' `WebSearch`/`WebFetch`/`Research` tools against a live environment: they would name hosts
  the environment must allow, and none were asked for in the recorded turns.
