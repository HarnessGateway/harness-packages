# MiniMax Code (`mcode`)

The agent CLI MiniMax ships as `@minimax-ai/code`, run headless: one `mcode exec` per turn, with its own
resumable sessions. This is a vanilla package — the CLI as its makers ship it, configured only with the
provider and model the request names.

Pinned CLI version: **0.7.7**.

## What it needs

- **Image:** Node.js 22.19 or later on the 22 line, or 24 through 26, and npm. `run` also needs `python3`
  (the platform's kit). No other system package.
- **Provider:** any of the four APIs the CLI speaks — Anthropic Messages, OpenAI Responses, OpenAI Chat
  Completions, Gemini. The package lists all four and configures the one the turn is given.
- **Settings and secrets:** none. The provider's key is `HG_PROVIDER_KEY`, a placeholder the platform's proxy
  replaces on the way out.

## Install

`install` installs `@minimax-ai/code@0.7.7` with npm under `$HG_HARNESS/tools`, pinned and version-checked.
npm 12 runs no package's install script unless told to, so the install is the same with `--ignore-scripts` on
every npm; the one native dependency the CLI needs (`better-sqlite3`) is then given its prebuilt binary by
name with `prebuild-install`. The CLI's own `verify-native-install.mjs` is run afterwards, and the install
fails with a plain message if the native pieces are missing or the version is not 0.7.7.

The install asked for `registry.npmjs.org`, `github.com` and `release-assets.githubusercontent.com` — all in
the platform's registry lists. No `setup.egress` entry is needed.

## The command

```
mcode exec --output-format stream-json --permission full \
  --model custom_provider:harnessgateway/<model> --input - --cwd <work> \
  [--session <id>] [--append-system-prompt <instructions>] \
  [--config <temporary file>] [--output-schema <json schema>]
```

MiniMax Code reads custom providers from a YAML config and stores the API key in it. The package therefore
writes a complete config for each turn to a temporary file under `/tmp` (never into the package or the
mind) and passes it with `--config`:

- `custom_provider.harnessgateway` — the provider's `baseURL`, the turn's placeholder key, and the API
  format (`anthropic-messages`, `openai-responses`, `openai-completions`, or `google-generative-ai`);
- `defaultModel` and the model's `models` entry — the model the request names;
- `dataContribution.enabled: false` — the CLI's data contribution is off.

`--permission full` is the CLI's own way to act without asking. The CLI's data directory is
`$HOME/.minimax`, so its sessions come back with the mind.

## Request fields

| In the request | Where it goes |
|---|---|
| `input` (a string, or user messages) | `request.prompt`, on the CLI's standard input (`--input -`) |
| `input_file` / `input_image` parts | `request.place_files()` puts them in `inputs/` in the work folder; `request.brief()` names them in the prompt |
| `instructions` | `--append-system-prompt` (the prompt is `request.brief(instructions=False)`, so it is not repeated) |
| the handover line | In front of the prompt, by `request.brief()` |
| `model` | A `models` entry in the generated config, and `--model custom_provider:harnessgateway/<model>` |
| the provider (base URL, key, API) | The generated config, selected by `HG_PROVIDER_API` |
| `reasoning.effort` | **Not applied.** A custom provider in MiniMax Code advertises no effort levels, so the CLI rejects `--effort`; the turn logs that it was not applied. |
| `tools` of type `mcp` | `.mcp.json` in the work folder: each server as `{"type": "http", "url": …, "headers": …}`. `allowed_tools` is not applied; the turn logs it. |
| `text.format` of type `json_schema` | `--output-schema <schema>` for the Anthropic and OpenAI APIs. Not for Gemini: the turn logs it. `json_object` is not supported. |
| `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`, `include` | Not honoured; the CLI's `exec` has no option for them. |
| `previous_response_id` | Nothing: the platform restored the mind, and the package resumes the CLI's own session. |
| `stream`, `background`, `store` | The platform's. |

## What is printed

`mcode exec --output-format stream-json` prints one JSON object per line. The translation is:

| The CLI's line | The turn |
|---|---|
| `item.*` of type `agent_message` (`contentDelta`, or `content` on the completed item) | a streamed `message` |
| `item.*` of type `reasoning` | a streamed `reasoning` item |
| `tool_call` named `bash` | `shell_call` + `shell_call_output`, with stdout, stderr and the exit code |
| `tool_call` named `write` (created) | `apply_patch_call` `create_file` |
| `tool_call` named `write` (overwritten) or `edit` | `apply_patch_call` `update_file`, with the CLI's patch |
| `tool_call` named `mcp__<server>__<tool>` | `mcp_call` |
| any other `tool_call` (`read`, `glob`, `grep`, `todowrite`, `web_fetch`, `task`, …) | `custom_tool_call` + `custom_tool_call_output` |
| `turn.failed`, or `exec.completed` with a failed result | `hg.failed` with the CLI's own message |
| `turn.completed` / `exec.completed` (succeeded) | `hg.done` |
| a line that is not JSON, or an event this package does not know | `hg.log` |

A stopped turn prints no terminal line: the terminal line is held until the CLI has ended, and the kit ends
`run` when the turn is stopped. The kit stops the CLI and every process it started. A stopped turn's partial
items are kept; they may not have their `done` events.

## Token usage

The counts come from the `usage` object of `turn.completed` and `exec.completed`:

```json
{"inputTokens": 12258, "outputTokens": 23, "cacheReadTokens": 2176, "totalTokens": 14457}
```

The terminal line reports `input_tokens` = `inputTokens` + `cacheReadTokens` (+ `cacheWriteTokens` when
present), `output_tokens` = `outputTokens`, and `input_tokens_details.cached_tokens` = `cacheReadTokens`.
A failed run usually has `usageSource: "unavailable"` and no counts; the terminal line then carries none.

## Sessions

The CLI reports its session id (`mvs_…`) in the first line of every run; the package saves it with
`state.set("session", …)` at that moment, so a stopped turn is still continued. The next turn passes
`--session <id>`. When the CLI exits non-zero without printing anything (its record of the session is gone),
`run` logs that, clears the id, and runs the turn once more as a new session.

Sessions and their tool outputs live under `$HOME/.minimax` (`v2/sqlite`, `v2/sessions`,
`background-tasks`). The manifest's `cache` names `.minimax/cache` and `.minimax/.builtin-skills` — the
model catalogue and the CLI's unpacked built-in skills, both remade by the CLI itself — so they are not saved
with the session. The trial's mind was about 6 MB of session data once those are excluded.

## Hosts an environment must allow

| Host | Why | Needed? |
|---|---|---|
| the provider's host | The model calls | Yes |
| `agent.minimax.cn` | MiniMax Code's model-catalogue descriptor, requested at every `exec` startup | No: the refresh is best-effort. A turn succeeded with the descriptor origin unreachable. |
| `filecdn.minimax.chat` | The model-catalogue content fetched from that descriptor | No: it is fetched only after a descriptor succeeds, and the refresh ignores a failure there too. |

No other host was seen during install or turns. The install's hosts are all in the platform's registry lists;
the two catalogue hosts are not, so an environment with a `closed` or restricted `limited` network needs them
in `network.allow` if the catalogue is wanted.

## What an operator sets

Nothing in the harness: it declares no settings and no secrets, and the provider's key and base URL come from
the turn. The operator's work is on the environment: the provider's host must be reachable from a turn, and
the environment must carry this harness before a request can name it. If the environment's `setup.egress` is
restricted, the three install hosts above must be allowed; the two catalogue hosts are optional.

## What was not tried here

- **OpenAI Responses, OpenAI Chat Completions and Gemini provider formats.** This session's provider speaks
  only the Anthropic API. The configuration for the other three is the CLI's own `provider add` shape, but
  they were not run against a provider.
- **MCP servers.** No MCP server was available; the `.mcp.json` mapping follows the CLI's documented project
  format. `allowed_tools` is not applied.
- **A successful structured output.** `text.format` with a JSON Schema is passed to `--output-schema`; the
  trial's model answered with prose, the CLI rejected the answer, and the turn failed with the CLI's
  `structured_output_invalid` message — so the flag reaches the CLI, but no valid answer was produced.
- **Inline images.** Text files sent inline were placed and read correctly; images were not tried.
- **A handover from another harness.** The handover line is put in front of the prompt by
  `request.brief()`, as for any turn.
- **Platforms other than Linux.**

A request names this harness as `<environment>/minimax/<provider>/<model>`.
