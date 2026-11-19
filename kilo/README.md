# kilo

Kilo Code's CLI, `kilo`, as its makers ship it — run headless, one turn per request. Version **7.8.27** of
[`@kilocode/cli`](https://www.npmjs.com/package/@kilocode/cli), installed with npm. No instructions, rules,
seeds or tools are added: the package only points the CLI at the turn's provider and says what it does.

## What it needs

| | |
|---|---|
| Image | Node.js and npm (the default image has Node.js 22 or later), and `python3` for `run`. Node runs only the npm launcher; the native binary does the work. |
| Install | `registry.npmjs.org`, through npm's normal registry access. No other host. |
| Provider | An **Anthropic Messages** endpoint or an **OpenAI-compatible Chat Completions** endpoint. The manifest lists `anthropic` first, then `openai-chat`; the turn is given the first of the two the provider offers. A provider that offers only Responses or Gemini fails with `hg.failed` / `unsupported_provider`. |
| Network in a turn | The provider's host, and nothing else. |

The CLI is installed under `$HG_HARNESS/tools` by npm; its own `postinstall` puts the native binary for the
image's platform in place. `install` checks `kilo --version` and fails unless it is exactly 7.8.27.

## The command

`run` writes a global config at `$HOME/.config/kilo/kilo.json` (and `.jsonc`) for this turn, then starts:

```
kilo run --format json --auto --pure --thinking -m hg/<model> [-s <session>] [--variant <effort>] \
     [-f <file>]... -- <the brief>
```

- `--format json` is the CLI's machine-readable output: one JSON object per line.
- `--auto` is its autonomous mode. Without it, a non-interactive run rejects permission requests and exits 1.
- `--pure` leaves out external plugins; there are none in the image, and it keeps the run off Kilo's plugin
  and indexing services.
- `--thinking` makes reasoning parts appear in the JSON output.
- `hg` is a custom provider entry the package writes: `@ai-sdk/anthropic` for `anthropic`,
  `@ai-sdk/openai-compatible` for `openai-chat`, with `baseURL` from `HG_PROVIDER_URL` and
  `apiKey: {env:HG_PROVIDER_KEY}`. The config holds the variable's **name**, never the key. Only `hg` is
  enabled, so Kilo does not load its own providers.
- `KILO_TELEMETRY_LEVEL=off`, `KILO_DISABLE_MODELS_FETCH=1`, `KILO_DISABLE_AUTOUPDATE=1`,
  `KILO_DISABLE_SESSION_INGEST=1`, `KILO_DISABLE_PRESENCE=1` are set for every turn, and `autoupdate: false`
  and `share: "disabled"` are in the config. With those, the only host a turn was seen to ask for is the
  provider's.

## The request, onto Kilo

| In the request | Where it goes |
|---|---|
| `input` | The prompt (`kilo run … -- <text>`). |
| `instructions` | In front of the prompt. Kilo has no per-request system-prompt flag; its ambient instructions are files and URLs in config. |
| The handover line | In front of the prompt. |
| `input_file` / `input_image` parts | Placed in `inputs/` in the work folder, named in the prompt, and passed to the CLI with `-f`. |
| `model` | `-m hg/<model>`; the same model is declared as `small_model`, so title and compaction calls use it. |
| the provider | The `hg` provider entry; `HG_PROVIDER_KEY` is handed over as `{env:HG_PROVIDER_KEY}`. |
| `max_output_tokens` | The model's declared output limit; the settings' `MODEL_OUTPUT_TOKENS` is used when the request sets none. |
| `reasoning.effort` | `--variant <effort>`. The harness declares no model variants, so this has no confirmed effect and the turn logs that once. |
| `tools` of type `mcp` | Each `server_label`/`server_url` becomes a remote MCP server in Kilo's config, with the request's `headers`. A call is printed as `mcp_call`. |
| `text.format` | Not honoured by the CLI. Logged once when set; the answer is returned as the model writes it. |
| `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`, `previous_response_id`, `stream`, `background`, `store` | No per-request option; ignored. The session is resumed from the mind, not `previous_response_id`. |

Every request field the package cannot honour is left alone; only `text.format`, `reasoning.effort` and an
MCP server's `allowed_tools` are noted with `hg.log`.

## What it prints

| Kilo's line | The turn prints |
|---|---|
| `text` | one `message` item, streamed as `response.output_text.delta` |
| `reasoning` | one `reasoning` item, streamed as `response.reasoning_summary_text.delta` |
| `tool_use` for `bash` | `shell_call` then `shell_call_output`, with the command, stdout, stderr and exit code |
| `tool_use` for `write` / `edit` | `apply_patch_call` (`create_file` / `update_file`) and its output, with Kilo's diff |
| `tool_use` for an MCP tool (`<server>_<tool>`) | one `mcp_call` for that server and tool |
| `tool_use` for any other tool (`read`, `grep`, `glob`, `todowrite`, `task`, `webfetch`, …) | `custom_tool_call` and `custom_tool_call_output` |
| `step_finish` | its token counts are added to the turn's usage; the last step's reason decides the terminal line |
| `error` | one `hg.failed`, with the CLI's error name as `code` and its message |

A `step_finish` reason of `length` is `hg.incomplete` / `max_output_tokens`; a content filter is
`hg.incomplete` / `content_filter`. A CLI exit with no final event is `hg.failed` / `cli_exit`. Token counts
are summed across the turn's steps, with cache reads and writes added into `input_tokens`. Empty reasoning
parts print nothing.

## The session

Kilo keeps its sessions in `$HOME/.local/share/kilo/kilo.db`, which is the mind. Every JSON line carries the
`sessionID`; `run` saves it with `hgkit.State` the moment the first one arrives, so a stopped turn is still
continued. The next turn resumes it with `-s <id>`. If the CLI says the session is gone (`Session not
found`, exit 1, no events), `run` logs that, clears the id and runs the turn as a new session, which is how a
stopped turn that left its record unusable recovers.

The mind after a turn is about 0.3 MB. The manifest's `cache` leaves out what Kilo makes again by itself:
`.cache/kilo` (its model catalogue and downloaded tools), `.local/share/kilo/log`, `.local/share/kilo/repos`
and `.local/state`. A resume still worked after those were deleted.

A *fresh* session here took several seconds to print its first event. A turn stopped before that has no id
to save, and the next turn starts a new session. Once a line has arrived, the id is saved immediately: a turn
stopped after its first event was resumed by the next turn, which still knew the stopped turn's prompt.

## Hosts an environment must allow

| Host | When | Needed? |
|---|---|---|
| The provider's host | every turn | Yes: it is where the model is. `HG_PROVIDER_URL`'s host. |
| The host of each MCP server in the request | turns that name one | Yes, for that server: `server_url`'s host. Not a host of this package; it comes from the request. |

No other host was seen. Install asks only for `registry.npmjs.org`, which every install reaches. There is no
`network.allow` entry this package's own turns need beyond the provider's host; `setup.egress` needs none
beyond the registries.

## What an operator sets

- Nothing is required. There are no secrets: the provider's key is the platform's placeholder.
- `MODEL_CONTEXT_TOKENS` (default `200000`) and `MODEL_OUTPUT_TOKENS` (default `32000`) are the model limits
  declared to Kilo. Set them to the provider model's real limits if they are smaller; Kilo sizes its requests
  and compaction from them, and a provider may refuse a request that runs past its window.
- The environment must carry this harness and allow the provider's host. It chooses the provider.

## What could not be tried here

- **openai-responses** and **gemini**: the package speaks `anthropic` and `openai-chat` only. `openai-chat`
  was tried against this build's provider on its OpenAI-compatible endpoint and worked; another provider's
  compatibility may differ.
- A provider whose authentication is not a bearer key in `x-api-key`/`Authorization` (OAuth, AWS signing) is
  not handled.
- A remote MCP server requiring OAuth was not tried. A plain remote HTTP MCP server with no authentication
  was tried, and its tool call printed as `mcp_call`; a request's `allowed_tools` is ignored by the CLI.
- Model variants and reasoning effort: `--variant` was accepted but no variant was declared, and the
  provider did not change its reasoning. Reasoning itself was tried with a reasoning model and printed.
- Only Linux x64 was tried. `install` names no architecture; npm chooses the binary package for the image.
- Kilo's own accounts, cloud sessions, sharing and sign-in are not used; the run is pointed at the turn's
  provider directly.

## Tested turns

`tests/` holds recorded turns: `hello` (text only), `command` (a file written and a command run), `resumed`
(a second turn continuing the first), `no-such-model` (the provider failing the turn), `reasoning`,
`incomplete` (output limit reached), `files` (an inline file input), `instructions`, and `mcp` (a remote MCP
server). `python3 /harness/guide/trial.py` made them; `harnessgateway package check` replays them.
