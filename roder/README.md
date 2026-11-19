# roder

A harness package for **Roder** (`roder`), the Rust-native agent harness from
[github.com/RoderAI/roder](https://github.com/RoderAI/roder), as its makers ship it: the
`roder` binary at version **0.4.10**, run through its headless entrypoint `roder exec --json`.

## What it needs

- A Linux image with glibc, `curl`, `tar`, `awk` and either `sha256sum` or `shasum`. The
  platform's default image has all of these.
- An environment provider offering **OpenAI Chat Completions** or **OpenAI Responses**: the
  package declares those two APIs, Chat Completions first. Chat Completions is the preferred
  path: in Roder 0.4.10 its Responses replay puts a duplicated pre-tool assistant message
  between a `function_call` and its `function_call_output`, and some Responses endpoints
  (DeepSeek's was observed) reject that with `No tool output found for tool call …`. The same
  tool turn over Chat Completions works. Responses stays declared second, for providers that
  offer only it. Roder's built-in Anthropic and Gemini transports are fixed to the makers' own
  endpoints and cannot be pointed at another provider, so those APIs are not declared.
- The provider's key arrives as `HG_PROVIDER_KEY`, a placeholder. Roder reads it from the
  environment; the platform's proxy puts the real key in on the way out. No secret is declared,
  and no operator setting is required.

`install` downloads the pinned release archive for this machine from GitHub Releases
(`github.com`, then `release-assets.githubusercontent.com`), verifies its SHA-256 against the
release's `.sha256`, and installs `roder` under `$HG_HARNESS/tools/roder`. Both hosts are in the
platform's package-manager registry list, so an install needs no extra egress.

## The command

Each turn starts one Roder process:

```
roder exec [resume <thread-id>] --json --profile non_interactive --mode bypass -
```

- `--json` makes it emit one JSON event per line (`thread.started`, `turn.started`,
  `item.started`/`item.updated`/`item.completed`, `turn.completed`/`turn.failed`).
- `--profile non_interactive` is its non-TTY profile; `--mode bypass` approves its tools
  without asking (the CLI warns about this on stderr, which is the turn's log).
- `-` reads the prompt from standard input.
- Before starting it, `run` writes `$HOME/.roder/config.toml` with a custom provider named
  `platform`: the turn's base URL, `api_key_env = "HG_PROVIDER_KEY"`, the turn's model in
  `models` (so Roder does not call `/models`), and `protocol = "chat_completions"` when the
  turn's API is `openai-chat` (the default custom protocol is Responses). It also turns off
  local analytics, the code index, knowledge and notifications, and points
  `RODER_CONFIG_DIR`/`RODER_DATA_DIR` at `$HOME/.roder`, so the thread store lives in the mind.

## What maps where

| In the request | How Roder is given it |
|---|---|
| `input` (a string, or messages) | The prompt on standard input. |
| `instructions` | In front of the prompt. `roder exec` has no system-prompt flag. |
| the handover line | In front of the prompt. |
| the request's files | `request.place_files()` puts them in `inputs/` in the work folder and the prompt names them; the agent opens them with its file tools. Images were **not** passed with `--image`. |
| `model` | The custom provider's model in `config.toml`. Roder stores the model on the thread when it starts, so a later turn naming a different model continues with the thread's original model. |
| the provider | `[providers.platform]` with `base_url`, `api_key_env = "HG_PROVIDER_KEY"`, and `protocol = "chat_completions"` for `openai-chat` (Responses otherwise). |
| `reasoning.effort` | `reasoning` in `config.toml` and `RODER_REASONING`. |
| `tools` of type `mcp` | **Not honoured.** `roder exec` has no MCP configuration option (MCP servers are supplied to the app-server/ACP, not to `exec`). The turn logs one line saying so. |
| `text.format`, `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | **Not honoured:** `roder exec` has no option for them. |
| `previous_response_id`, `stream`, `background`, `store` | The platform's. The session is continued from Roder's own thread store (below). |

## What is printed

Roder's `--json` items become Responses events:

| Roder | Printed as |
|---|---|
| `agentMessage` completed | one `message` item with its `output_text`. Text is printed when Roder completes a message, not token by token. |
| `reasoning` completed | one `reasoning` item with a `summary_text`. |
| `exec_command` / `shell` tool | `shell_call` and `shell_call_output`; stdout is Roder's combined output, and the exit code is read from its `Exit code: N` line. |
| `write_file` tool | `apply_patch_call` with `create_file` and a `+` diff of the content. |
| `edit` / `multi_edit` tool | `apply_patch_call` with `update_file` and `-`/`+` lines. |
| `apply_patch` tool | `create_file` / `update_file` / `delete_file` for each file named in the patch. |
| any other tool (`read_file`, `grep`, `glob`, `list_files`, …) | `custom_tool_call` and `custom_tool_call_output`, with its arguments and output text. |
| a failed file tool | `custom_tool_call` with the tool's error text as its output. |
| a tool named `mcp__<server>__<tool>` | `mcp_call` (Roder can make these, though this package cannot be given the request's MCP servers). |
| a non-JSON line on stdout | `hg.log`. Roder's diagnostics on stderr are the turn's log already. |
| `turn.completed` | `hg.done` |
| `turn.failed` | `hg.failed`, code `turn_failed`, with the provider's own message. |
| the process ends with no terminal event | `hg.failed`, code `cli_exit`, with the exit code. |

Repeated `item.completed` notifications for the same tool call are printed once, and so is the
same assistant text when Roder records it under two phases (`commentary` and `final_answer`).
`item.updated` notifications (Roder's cumulative token-by-token text) are not printed; the
completed item is.

**Token usage** comes from Roder's `turn.completed` (or `turn.failed`) `usage`:
`input_tokens` (which already includes cached input on the OpenAI APIs) becomes `input_tokens`,
`cached_input_tokens` becomes `input_tokens_details.cached_tokens`, and `output_tokens` becomes
`output_tokens`. A turn the provider rejects before any model call reports zeros.

## The session

Roder's thread store is `$HOME/.roder/threads`. `run` saves the `thread_id` from
`thread.started` with `state.set("session", …)` the moment it is printed, and continues with

```
roder exec resume <thread-id> --json --profile non_interactive --mode bypass -
```

If resuming fails before a turn starts (the thread is gone or unusable), `run` logs it, clears
the saved id, and runs the turn as a new thread. A stopped turn ends within the grace period and
prints no terminal line; its thread id was already saved, and the next turn continues it (tried:
a turn stopped after 3 seconds was continued by the next one).

The mind holds `.roder/threads` (the session), `.roder/memory` and `.roder/workspaces.json`.
`.roder/discovery` (Roder's rebuilt discovery catalogue) and `.roder/code-index` are regenerated
by the CLI and are named in the manifest's `cache`, so they are not saved with the session.

## Hosts an environment must allow

- **Install:** `github.com` and `release-assets.githubusercontent.com`. Both are in the
  platform's package-manager registry list, so no `setup.egress` entry is needed.
- **Turn:** only the provider's own host (`HG_PROVIDER_URL`). The model is fixed in
  `config.toml`, so Roder does not fetch a model list, and nothing else was asked for. No other
  host was seen in any turn, so no `network.allow` entry is needed.

## What was tried, and what was not

Tried with real turns against the building session's provider (DeepSeek, reached through its
OpenAI-compatible `/v1` endpoint): a text-only turn, a turn that wrote a file and ran it, a
resumed turn, a stopped turn followed by a continuation, a provider error (an unknown model),
and the same file-and-command turn over both Chat Completions and Responses. A thread created
over Responses whose tool turn failed was then continued over Chat Completions, which worked.
Each case is recorded under `tests/`.

The Responses tool turn reproduced a Roder 0.4.10 defect: the request it sends after a tool call
contains `function_call`, then a second copy of the pre-tool assistant message, then
`function_call_output`, and DeepSeek's Responses endpoint rejects that ordering. The package
prints a completed assistant message once even though Roder records it under two phases
(`commentary` and `final_answer`), so the duplicate does not reach the caller either.

Not tried here:

- The Responses tool path against a provider other than DeepSeek; it is declared second, so the
  platform chooses Chat Completions whenever the provider offers it.
- A provider offering the Anthropic or Gemini API. Roder's built-in transports for those are
  fixed to `api.anthropic.com` and Google's endpoint, so they cannot use a turn's
  `HG_PROVIDER_URL`; the package therefore declares only the two OpenAI APIs.
- The request's MCP tools (see above).
- Uploaded images through `--image`; files are placed and named in the prompt instead.
- `text.format` and the other request fields listed as not honoured.
- A session whose next request names a different model: Roder's thread keeps the model it was
  started with.
