# omp — Oh My Pi

`omp` is Oh My Pi's coding-agent CLI (`@oh-my-pi/pi-coding-agent`), installed and run as its makers ship it,
headless in the sandbox. This package adds no instructions, rules or tools of its own.

- CLI version: **18.22.2** (npm `@oh-my-pi/pi-coding-agent`), package revision 1.
- Source: <https://github.com/can1357/oh-my-pi>. Runtime: Bun (installed from npm at 1.4.4; the CLI's own
  documented install is Bun's global install).

## What it needs

- An image with **Node.js and npm** (the default image has both). Bun is installed by this package from
  `registry.npmjs.org` and does not need to be on the image.
- A provider that speaks one of the APIs in the manifest: **Anthropic Messages** (first), OpenAI Chat
  Completions, OpenAI Responses, or the Gemini API. The environment must allow the provider's own host; the
  package names no host.
- Nothing to set: it declares no settings and no secrets. The provider's key arrives as
  `HG_PROVIDER_KEY` and reaches the provider through the platform's proxy.

## The command

```
omp -p --mode json --no-title --offline --approval-mode yolo --model hg/<HG_MODEL> [--thinking <level>]
    [--resume <session id>] [--append-system-prompt <instructions>]
```

The prompt is written to standard input (non-TTY input is read to EOF). `-p --mode json` is the CLI's
machine-readable print mode: one JSON object per line. `--approval-mode yolo` is what makes a headless turn
act without asking; `--no-title`/`PI_NO_TITLE=1` stop the extra model call that names the session. The agent
directory `~/.omp/agent` holds, rewritten before each turn:

- `models.yml` — a custom provider `hg` with the turn's base URL, key variable and model id, so the provider
  and model the request names are the ones used;
- `config.yml` — `models.offline: true` and telemetry export off;
- `mcp.json` — the request's MCP servers, when it has any.

The CLI stores its sessions under `~/.omp/agent/sessions/<encoded-cwd>/`; that is inside the mind, so it is
saved and restored with the session. The mind also holds `~/.omp/agent/models.db` (about 8 MB), the CLI's
model-catalogue cache; it is rewritten by `omp` itself, not a session, and the other files in the mind are
small (a log, the credential database). The manifest names no `cache` folder: the large file is a single
database, and removing it only makes the next turn fetch the catalogue again.

## The request, mapped

| In the request | Where it goes |
|---|---|
| `input` | The prompt on standard input (`hgkit.Request.brief`, instructions excluded) |
| `instructions` | `--append-system-prompt` |
| `input_file` / `input_image` parts, by file id or inline | `hgkit.Request.brief` places them in `inputs/` in the work folder and names them in the prompt |
| `model` | `--model hg/<HG_MODEL>`; the same id is declared in `models.yml` |
| the provider (URL, key, API) | `models.yml`: `baseUrl` and `apiKey: HG_PROVIDER_KEY`; the API is chosen by `HG_PROVIDER_API` (`anthropic` → `anthropic-messages`, `openai-chat` → `openai-completions`, `openai-responses` → `openai-responses`, `gemini` → `google-generative-ai`) |
| `reasoning.effort` | `--thinking` (`none`→`off`, `minimal`/`low`/`medium`/`high`/`xhigh`/`max` passed through; anything else omitted) |
| `tools` of type `mcp` | `~/.omp/agent/mcp.json` as HTTP servers, with their headers |
| the handover line | In front of the prompt (`brief`) |
| `previous_response_id` | Nothing: the platform restores the mind; the package resumes its own session (below) |
| `text.format`, `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | Not honoured: `omp`'s print mode has no option for them. They are left alone, not failed. |

The platform refuses tools of any type but `mcp` before a package sees them, so that row does not arise here.
`request.history` is not read; the handover line points the agent at the other harness's folder.

## What is printed

The CLI's `--mode json` events are translated to Responses events:

| `omp` prints | The turn prints |
|---|---|
| `message_update` `text_delta` | `response.output_text.delta` (a message item) |
| `message_update` `thinking_delta` | `response.reasoning_summary_text.delta` (a reasoning item) |
| `tool_execution_end` with tool `bash` | `shell_call` + `shell_call_output` (stdout, stderr, exit code from the trace) |
| tool `write` | `apply_patch_call` `create_file` with a `+`-line diff of the content |
| tool `edit` / `apply_patch` | `apply_patch_call` `update_file` with the old/new lines as `-`/`+` |
| tool `mcp__<server>_<tool>` | `mcp_call` |
| any other tool (`read`, `grep`, `glob`, `find`, `task`, …) | `custom_tool_call` + `custom_tool_call_output` |
| `session` header | Saved with `state.set("session", id)` as soon as it arrives |
| an assistant message with `stopReason: "error"` | `hg.failed` `provider_error`, with the provider's own message |
| `agent_end` | `hg.done` |

A `write` to `out://` (the CLI's way of saying something to the reader) is printed as assistant text.

### Token usage

Every model request's `message_end` carries `usage` (`input`, `output`, `cacheRead`, `cacheWrite`). The
package sums the assistant messages of the run, and the terminal line reports
`input_tokens = input + cacheRead + cacheWrite`, `output_tokens = output`, and
`input_tokens_details.cached_tokens = cacheRead`. The failure case in `tests/` shows a provider error with
zero counts; the other cases carry the sums.

## How the session continues

The first JSON line of every run is `{"type":"session","id":…}`. `run` saves that id in the package's state
the moment it reads it, before any model work, so a stopped turn is still continued. The next turn resumes it
with `--resume <id>`. If `omp` exits non-zero without reporting a session at all, its record is gone: `run`
logs that, clears the state and runs the turn once more as a new session. The trial's stop test (`--stop-after
8`, after startup) ended with no terminal line and the following turn resumed it.

`run.stop_grace_s` is 20 seconds: `omp` handles SIGTERM, records the session's exit and disposes of its
workers, which takes a few seconds.

## Hosts an environment must allow

The provider's host is required; the platform gives each turn its provider through the proxy. Everything
else below was seen in the install or the turns:

| Host | When | Needed? |
|---|---|---|
| `registry.npmjs.org` | Install (48 requests) and the first turn of a fresh session | **Install: yes** — it is in the platform's registry list. On a turn it is the model-catalogue refresh; refused, the CLI keeps its bundled catalogue. |
| `catalog.stencil.so` | First turn of a session whose mind has no model cache | Optional. `omp` refreshes the shared model catalogue in the background; a refusal leaves the bundled catalogue in place. Later turns in the same session made no request. |
| `api.commandcode.ai`, `api.kilo.ai`, `api.venice.ai`, `coding-intl.dashscope.aliyuncs.com`, `hyper.charm.land`, `zenmux.ai` | The same first-turn catalogue refresh | Optional, same fallback. They are other providers' discovery endpoints, not this turn's provider. |
| `127.0.0.1:11434` (Ollama), `127.0.0.1:1234` (LM Studio), `127.0.0.1:8080` (llama.cpp/Bifrost) | Every turn, at startup | Optional. These are local-engine probes; the platform's proxy refuses them, `omp` warns in its log and continues. |

The install needs nothing beyond the package managers. If an environment's network is `limited`, its default
already covers `registry.npmjs.org`; the other hosts can stay refused, at the cost of the background model
catalogue refresh and three harmless warnings in the turn's log.

## What could not be tried here

- MCP servers: the mapping to `~/.omp/agent/mcp.json` is written from the CLI's documentation; no MCP host
  was available in this sandbox to connect to.
- Non-Anthropic provider APIs (`openai-chat`, `openai-responses`, `gemini`): this session's provider speaks
  the Anthropic API only. Those mappings are the CLI's documented custom-provider APIs, untested here.
- Image/file attachments sent as `input_file`/`input_image`: placed by `hgkit.Request.brief` and named in the
  prompt, but not exercised in a recorded case.
- Approval prompts: print mode runs with `--approval-mode yolo`; no interactive approval path was tried.

## What an operator must set

Nothing in this package: no settings, no secrets. An environment that carries the harness must be able to
reach the provider it names and carry the harness in its `harnesses` list. The CLI's own model catalogue
refresh and local-engine probes are optional, as above.
