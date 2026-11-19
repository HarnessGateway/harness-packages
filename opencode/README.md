# opencode

The [opencode](https://opencode.ai) CLI by its makers, at **1.19.6**, run headless in a sandbox: one
`opencode run --format json` per turn, translated into OpenAI Responses events.

Vanilla: it adds no instructions, tools or permissions of its own. The agent is OpenCode as it ships, with
only the switches below that a headless, proxied turn needs.

## What it needs

- **To install:** Node.js and npm on the image (it installs the pinned npm package and runs the package's own
  post-install step, which picks the binary for the machine). No root; everything goes under
  `$HG_HARNESS/tools`. The installed `opencode` is a self-contained executable; Node.js is not needed at turn
  time. `install` pins `opencode-ai@1.19.6` and checks `opencode --version`.
- **To run:** Python 3 (the default image has it) for `run`. No other service.
- **From the provider:** an Anthropic Messages or OpenAI Chat Completions endpoint. The manifest declares
  `anthropic` first, then `openai-chat`, so a provider offering both is spoken to in the Anthropic API.

`install` also puts `@opencode-ai/plugin` under `$HG_HARNESS/tools/opencode-xdg/opencode` and points the turn's
`XDG_CONFIG_HOME` there, so the CLI does not install its start-up plugin from npm during a turn. That
directory is complete before the first turn — `opencode.jsonc`, `.gitignore`, `package.json`,
`package-lock.json` and `node_modules` — because OpenCode writes beside its global config on start-up and
`/harness` is read-only during a turn. No turn writes anything under `/harness`.

## The command

```
opencode run --format json --thinking --auto -m harnessgateway/<model> [--session <id>] "<brief>"
```

`--auto` approves permissions that are not explicitly denied (OpenCode's default already allows everything);
it matters when a project config sets a permission to `ask`. `--thinking` adds reasoning parts to the JSON
stream. The prompt is `request.brief()`: the handover line, the request's instructions, the paths of the files
this request brought, then the prompt.

## The provider

`run` writes an OpenCode configuration for the turn (`OPENCODE_CONFIG_CONTENT`) with one custom provider:

| Provider API | AI SDK package | `baseURL` |
|---|---|---|
| `anthropic` | `@ai-sdk/anthropic` | `HG_PROVIDER_URL` + `/v1` (the platform's Anthropic URL has no `/v1`) |
| `openai-chat` | `@ai-sdk/openai-compatible` | `HG_PROVIDER_URL` (already ends in `/v1`) |

The key is `HG_PROVIDER_KEY`, a placeholder the platform's proxy replaces on the way to the provider. The
model key and `-m` are `HG_MODEL`, so OpenCode's small/title model is the same model (no second model needs to
exist). The model is declared with tool calling and attachments, without a reasoning flag: OpenCode asks for
no thinking parameters, which keeps arbitrary gateway models working.

Three maker services are turned off because a turn cannot rely on them: update checks (`autoupdate: false`,
`OPENCODE_DISABLE_AUTOUPDATE`), sharing (`share: "disabled"`), and the models.dev catalogue
(`OPENCODE_DISABLE_MODELS_FETCH`). The bundled default plugin is not loaded
(`OPENCODE_DISABLE_DEFAULT_PLUGINS`); the plugin package is already installed, so nothing is fetched.

## What maps to what

| In the request | In the turn |
|---|---|
| `input` (text) | The prompt |
| `instructions` | In front of the prompt; `opencode run` has no system-prompt option |
| `input_file` / `input_image` | Placed in `work/inputs/` by `request.brief()`, named in the prompt; the agent opens them with its `read` tool |
| the handover line | In front of the prompt (from `request.brief()`) |
| `model` | `-m harnessgateway/<model>` |
| the provider's URL, key, API | The custom provider's `options.baseURL`, `options.apiKey`, and its AI SDK package |
| `tools` of type `mcp` | `mcp` in the turn's config, as remote servers (`server_url` + `headers`) |
| `reasoning.effort` | **Not honoured.** OpenCode's variant is not set; providers get their default |
| `history` | **Not used.** The handover line points at the other harness's folder |
| `text.format`, `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | **Not honoured.** `opencode run` exposes no such option |
| MCP `allowed_tools` | **Not honoured.** OpenCode exposes every tool an MCP server offers |

A project's own `opencode.json` in the work folder is still read by the CLI (it has the highest config
precedence). `-m` overrides its model. A project that redefines the provider id `harnessgateway` could change
its endpoint; that only makes the turn fail, since the proxy will not put the key toward another host.

## What it prints

| OpenCode (`run --format json`) | Responses output |
|---|---|
| `text` part | one streamed `message` |
| `reasoning` part (with `--thinking`) | one streamed `reasoning` item |
| `tool_use` `bash` | `shell_call` + `shell_call_output` with stdout, stderr and the exit code |
| `tool_use` `write` | `apply_patch_call` `create_file` with the new content as a diff |
| `tool_use` `edit` | `apply_patch_call` `update_file` with `-old` / `+new` lines |
| `tool_use` `apply_patch` | one `create_file` / `update_file` / `delete_file` per file in `patchText`; a patch it cannot read becomes a `custom_tool_call` |
| MCP tool (`<server>_<tool>`) | `mcp_call` with the server's label and the tool |
| `read`, `glob`, `grep`, `list`, `task`, `skill`, `webfetch`, `todowrite`, … | `custom_tool_call` + `custom_tool_call_output` |
| `step_finish.tokens` | summed into the terminal line's `usage` (input includes cache reads and writes) |
| `error` | `hg.failed` with `code: "provider_error"` and the provider's message |
| a last step reason of `length` / `content-filter` | `hg.incomplete` with `max_output_tokens` / `content_filter` |
| otherwise, the CLI's normal end | `hg.done` |

Anything else OpenCode prints that this package does not know goes to the turn's log (`hg.log`). A CLI exit
with no output, or before it finished a step, is `hg.failed` with `code: "cli_exit"`.

## Sessions

OpenCode stores sessions in SQLite at `$HOME/.local/share/opencode/opencode.db`, which is the manifest's
`mind`. Its session id is on every JSON line; `run` saves it with `state.set("session", …)` as soon as it
sees the first one, so a stopped turn is still continued. The next turn resumes with `--session <id>`.

If the session id is no longer usable, OpenCode exits non-zero without printing anything; `run` logs that,
clears the state and runs the turn again as a new session.

`.cache/opencode`, `.local/state/opencode`, `.local/share/opencode/log` and `.npm` are declared as `cache`:
OpenCode (or npm, when the agent runs it) makes them again when missing. In the trials the saved mind held
only `opencode.db`, about 0.3 MB.

## Network

A turn reaches the provider's host and nothing else. No other host was asked for in the trials
(`api.deepseek.com` in this environment: the provider).

`install` reaches `registry.npmjs.org` only, which is one of the package registries an install can always
reach. It needs no `setup.egress` entry.

An environment needs no `network.allow` entry for this package beyond its provider. If an operator wants MCP
servers or a project plugin to be usable, the hosts of those servers/registries must be allowed by the
environment; this package does not name them.

## What an operator sets

Nothing. There are no settings and no secrets in the manifest. The environment must carry the harness and
offer a provider whose API is `anthropic` or `openai-chat`; a request names the model. A turn started as
`<environment>/opencode/<provider>/<model>` uses `HG_MODEL` for every OpenCode model call.

## What could not be tried here

- `openai-chat` was exercised against a local OpenAI-compatible stand-in (the request went to
  `/v1/chat/completions` with `Authorization: Bearer <placeholder>`), not against a real provider: this
  environment's provider offers only the Anthropic API.
- The Anthropic path was tried against this environment's provider (an Anthropic-compatible endpoint), not
  against `api.anthropic.com` itself.
- MCP servers were not exercised; the configuration follows the v1.19.6 `mcp` shape (`type: "remote"`, `url`,
  `headers`) but no MCP call was recorded.
- The `edit` and `apply_patch` translations were not produced by the model in a trial; `write`, `bash` and
  `read` were. The recording of a failed turn used a model name the provider rejects.
- A stopped turn ended within the 10-second grace and the next turn continued it; the visible answer from
  that resumed turn confirmed the earlier prompt was in the session.
