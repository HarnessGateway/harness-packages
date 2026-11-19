# goose

[goose](https://github.com/aaif-goose/goose) is Block's open-source AI agent CLI. This package runs the
CLI headless in the sandbox, as its makers ship it: its own session store, its default extensions (the
developer tools, the extension manager, apps, summon, analyze and the rest), and its own `stream-json`
output.

- CLI version: **1.60.1** (release tag `v1.60.1`)
- Package version: **1.60.1-1**

## What it needs

- A Linux image with `curl` and `tar`. The install downloads the release archive the project publishes and
  unpacks it; it needs no root, no compiler and no Node.js.
- x86_64 or aarch64. The install chooses the build from `uname`; the glibc archive is used, and the musl one
  when the image's `ldd` says it is musl. Goose also publishes a Vulkan build for local inference; this
  package uses the ordinary build.
- A provider reachable at the API the request names. The provider's key is a placeholder in the sandbox; the
  platform's proxy puts the real key in on the way out.

The install reaches `github.com` and `release-assets.githubusercontent.com`, both of which are in the
platform's package-manager registries, so an environment needs no extra `setup.egress` for it.

## The command

```
goose run -i - -q --output-format stream-json \
  --provider <goose provider> --model <model> \
  [--resume] --name <session name> \
  [--system <instructions>] \
  [--with-streamable-http-extension <url> ...]
```

The turn's prompt is written to standard input (`-i -`). The provider is set through goose's own variables:

| Request's API | goose provider | base URL | key |
|---|---|---|---|
| `anthropic` | `anthropic` | `ANTHROPIC_HOST` | `ANTHROPIC_API_KEY` |
| `openai-chat` | `openai` | `OPENAI_BASE_URL` | `OPENAI_API_KEY` |
| `gemini` | `google` | `GOOGLE_HOST` | `GOOGLE_API_KEY` |

The CLI runs with `GOOSE_MODE=auto` (tools run without asking), `GOOSE_DISABLE_KEYRING=1`,
`GOOSE_TELEMETRY_OFF=1`, and `GOOSE_PATH_ROOT=$HOME/.goose`, which puts goose's config, data and state
together in the mind (`.goose`). Nothing is written under `/harness` during a turn.

## Request fields

| In the request | Where it goes |
|---|---|
| `input` | the prompt, on standard input |
| `instructions` | `goose run --system`, goose's additional system prompt |
| uploaded files, `input_file` and inline image parts | copied to `inputs/` in the work folder and named in the prompt; the agent opens them with its tools (`read_image` for images) |
| `model` | `--model`; goose's provider is set to the API the turn was given |
| `reasoning.effort` | `GOOSE_THINKING_EFFORT`: `minimal` is sent as `low`, `low`/`medium`/`high` as they are, `xhigh`/`max` as `max` |
| `tools` of type `mcp` with a `server_url` | one `--with-streamable-http-extension <server_url>` each |
| the handover line | in front of the prompt |
| `previous_response_id`, `stream`, `background`, `store` | the platform's; the CLI's session is resumed from the mind instead |

Not honoured, and left alone without failing the turn: `text.format` (the CLI has no equivalent),
`max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`. An MCP
server's `headers` and `allowed_tools` are not passed either: goose's CLI flag carries the URL only, so a
server that needs headers will not authenticate. This is said once in the turn's log when a request has
headers. MCP servers must speak streamable HTTP; goose's flag has no SSE form.

## What is printed

`goose run --output-format stream-json` prints one JSON object per line; `run` translates them:

| goose's line | Printed as |
|---|---|
| assistant text pieces | one streamed `message` (`output_text` deltas) |
| `thinking` pieces | one streamed `reasoning` item |
| `toolRequest`/`toolResponse` for developer `shell` | `shell_call`, then `shell_call_output` with stdout, stderr and exit code |
| … for developer `write` / `edit` | `apply_patch_call` (`create_file` / `update_file`) and its output |
| … for a tool of a request's MCP server | one `mcp_call` (server label, tool, arguments, output or error) |
| … for any other tool (`tree`, `read_image`, `analyze`, the apps and extension-manager tools, `delegate`, `load`, …) | `custom_tool_call`, then `custom_tool_call_output` |
| goose's log/progress notifications, non-JSON lines, unknown lines | `hg.log` (the turn's log; the caller never sees it) |
| final `complete` | `hg.done`, with usage: `input_tokens` (cached included), `output_tokens`, `cached_tokens` |
| final `error`, or an error content block | `hg.failed` with a short code (`provider_error`, `authentication`, `context_length_exceeded`, `credits_exhausted`, `resource_exhausted`) and goose's message |
| no result at all | `hg.failed("cli_exit", …)` with the exit code |

Goose emits the assistant's output pieces as they arrive, so text and reasoning stream. Calls and results
are paired by goose's call id and printed together when the result arrives.

## Sessions

goose keeps its sessions in `$GOOSE_PATH_ROOT/data/sessions/sessions.db`; with `GOOSE_PATH_ROOT=$HOME/.goose`
that is `.goose/data/sessions` in the mind, and it is saved, restored, rewound and forked with the session.

goose's `stream-json` output does not report a session id, so the package addresses the session by a name it
gives it: `hgsess-<HG_SESSION>`. The name is written to the package's state (`session`) before the first
turn's CLI starts, and every later turn runs `--resume --name <name>`. The name is stable for the session
and changes (`-g2`, `-g3`, …) only when a new session is started in the same mind.

If the state names a session that goose's store no longer has, `run` says so in the turn's log and starts a
new one; the same is done if goose refuses a resume before producing any output. A stopped turn prints no
terminal line: the CLI and the processes it started are signalled and end within `run.stop_grace_s` (15 s),
and the session record it had already written is what the next turn resumes. This was tried: a turn stopped
during a 60-second shell command was continued correctly by the next turn.

The package also clears and restarts the session if goose reports a session-gone error in its JSON output.

## Hosts an environment must allow (turns)

Beyond the provider itself (which the platform binds):

| Host | Why | Needed? |
|---|---|---|
| `models.dev` | goose fetches a model catalogue at startup (cached under `.goose/data/model_catalog`) | no: the fetch is in the background and a refusal only logs a warning |
| each request's MCP server host | the tools the request asks for | only when the request names MCP servers |

That is all that was observed. The install asks for `github.com` and `release-assets.githubusercontent.com`,
which the platform's registry list already covers.

## The mind

`.goose/data/sessions` holds the session; `.goose/config` holds what goose writes of its configuration;
`.goose/data/apps` holds the apps extension's default app; `.goose/state` holds goose's small state. The
manifest's `cache` leaves out `.goose/state/logs` (per-turn logs, which include full prompts) and
`.goose/data/model_catalog` (the download cache), so they are not saved with the session.

## What an operator sets

Nothing in the manifest: this package declares no settings and no secrets. Give the harness an environment
that carries it, and name a provider and model in the request
(`<environment>/goose/<provider>/<model>`). If turns should reach `models.dev` or MCP servers, allow those
hosts in the environment's `network.allow`; the CLI works without `models.dev`.

## What was not tried

- The `openai-chat` and `gemini` paths: the only provider available while writing this package spoke the
  Anthropic API. They use goose's own `openai` and `google` providers and the variables above.
- MCP servers: the translation of `mcp_call` events and the CLI flag are in place, but no live MCP server
  was attached in a trial.
- Models or providers whose tool-calling behaves differently from the one used in the trials.
