# docker-agent

Docker Agent, the `docker-agent` CLI from Docker (github.com/docker/docker-agent), as its makers ship it,
headless in a HarnessGateway sandbox. The CLI is pinned at **v1.161.0** and installed as the standalone Linux
binary from its GitHub release.

One turn is one headless `docker-agent run --exec` with a coding agent: the file and shell toolsets, the
instruction and behaviour of the CLI's built-in `default` agent, JSON events on standard output, and the
session kept in the mind.

## What it needs

- The default image: `sh`, `curl` for `install`, and Python 3 for `run` (the kit). The CLI itself is a
  statically linked Go binary and needs nothing else.
- A provider the platform reaches through its proxy, speaking one of the manifest's APIs: Anthropic Messages,
  OpenAI Responses, OpenAI Chat Completions, or the Gemini API. The model named by the request must be one that
  endpoint serves.

No setting and no secret is declared: the provider key arrives as `HG_PROVIDER_KEY` (a placeholder the proxy
replaces), and nothing else is required of the operator.

## Install

`install` downloads

```
https://github.com/docker/docker-agent/releases/download/v1.161.0/docker-agent-linux-<arch>
```

where `<arch>` is what the machine reports (`amd64` or `arm64`; no build is fixed in the script), puts it at
`$HG_HARNESS/tools/docker-agent`, and checks the version it got with `docker-agent version`. Both hosts it
asks for — `github.com` and the redirect target `release-assets.githubusercontent.com` — are in the platform's
version-control registry, so `install` needs nothing added to an environment's `setup.egress`. The makers
publish no separate checksum asset for the binary; the version the binary reports is what is checked.

## The command

Each turn `run` writes a small agent file to `$HG_STATE/agent.yaml` (removed when the turn ends) and starts:

```
docker-agent run --exec --json --safety autonomous \
  --session <id> \
  --data-dir   /mind/.cagent \
  --config-dir /mind/.cagent/config \
  --cache-dir  /mind/.cagent/cache \
  <agent.yaml> -
```

The prompt is written to standard input (`-`). `--safety autonomous` is the CLI's unattended mode, so no tool
approval can block the turn. `TELEMETRY_ENABLED=false`, `DOCKER_AGENT_HIDE_TELEMETRY_BANNER=1`,
`DOCKER_AGENT_NO_SETUP=1`, `DOCKER_AGENT_AUTO_UPDATE=0`, `DOCKER_AGENT_AUTO_INSTALL=false` and
`DOCKER_AGENT_DISABLE_DESKTOP_PROXY=1` turn off telemetry, the first-run notice, the setup wizard, self-update,
tool auto-install and Docker Desktop's proxy adapter.

The generated agent file is the CLI's built-in `default` coding agent — its instruction, `skills: true`,
`add_environment_info: true`, `add_prompt_files: [AGENTS.md]`, the `file` and `shell` toolsets — with a
provider and model block for this turn:

```yaml
providers:
  hg:
    provider: anthropic          # or openai, or google
    base_url: "<HG_PROVIDER_URL>"
    token_key: ANTHROPIC_API_KEY # the variable holding HG_PROVIDER_KEY
    api_type: openai_responses   # only for the two OpenAI APIs
models:
  hgmodel:
    provider: hg
    model: "<HG_MODEL>"
```

The key itself is never written to the file: the CLI reads its placeholder from the environment, and the
platform's proxy puts the real key in on the way to the provider.

## The request

| In the request | Where it goes |
|---|---|
| `input` | The prompt on standard input: `request.brief()` — the handover line, the request's `instructions`, the paths of the request's files, then the text |
| `instructions` | In front of the prompt (the agent file's instruction is the CLI's own, as shipped) |
| uploaded files and inline `input_file`/`input_image` parts | `inputs/` in the work folder, named in the prompt; the agent opens them with `read_file` |
| `model` (`HG_MODEL`) | The model id in the generated agent file |
| the provider | `base_url` and `token_key` in the generated file, and `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` / `GOOGLE_GEMINI_BASE_URL` in the environment |
| `reasoning.effort` | `thinking_budget` on the model, when it is one of the CLI's effort levels |
| `max_output_tokens`, `temperature`, `top_p` | `max_tokens`, `temperature`, `top_p` on the model |
| `tools` of type `mcp` | A remote MCP toolset per server, named `server_label`, with its `server_url`, `headers` and `allowed_tools` |
| the handover line | In front of the prompt |
| `previous_response_id` | Nothing: the platform restored the mind, and the CLI's own session is resumed |
| `stream`, `background`, `store` | The platform's |

Not honoured, and said so in the turn's log where it changes what the caller gets: `text.format` (the CLI
supports structured output, but only through an agent-file schema, not this request), `max_tool_calls`,
`truncation`, `user`, `metadata`, and `prompt_cache_key`/retention options. `history` is not replayed; the
handover line is what points the agent at another harness's work.

MCP servers in the request must be reachable over HTTP; the CLI runs them as remote toolsets, not local
processes. Their hosts must be ones the turn's environment allows, and a header carrying a declared secret is
replaced by the platform's proxy only toward the host the secret is bound to.

## What is printed

| The CLI | The turn |
|---|---|
| `agent_choice` pieces | one streamed `message` (`response.output_text.delta`) |
| `agent_choice_reasoning` pieces | one streamed `reasoning` item |
| a `shell` tool call and its result | `shell_call` and `shell_call_output`; the CLI folds the exit status into the output text, and it is read back from there |
| `write_file` | `apply_patch_call` `create_file`, with a `+` diff of the content |
| `edit_file` | `apply_patch_call` `update_file`, with `-`/`+` lines for each edit |
| a tool of a request MCP server (`<label>_<tool>`) | `mcp_call` with the server label, tool, arguments and output (or the error) |
| any other tool (`read_file`, `list_directory`, `todo`, …) | `custom_tool_call` and `custom_tool_call_output` |
| `warning`, `model_fallback`, an `error`, a line that is not JSON | the turn's log (`hg.log`) |
| `stream_stopped`, reason `normal` | `hg.done` |
| `stream_stopped`, `finish_reason` `length` / `refusal` | `hg.incomplete` with `max_output_tokens` / `content_filter` |
| `stream_stopped`, reason `max_iterations` / `budget_exceeded` / cancelled | `hg.failed` |
| an exit with no `stream_stopped` | `hg.failed` (`cli_exit`), with the CLI's own last error line from standard error |

The CLI's own bookkeeping events (`hook_*`, `team_info`, `mcp_init_*`, `toolset_info`, `user_message`,
`stream_started`, `agent_info`, `message_added`, `partial_tool_call`, streamed `tool_call_output`,
`session_title`, …) are not printed.

### Token usage

`token_usage` events carry, per model response, a `last_message` with that response's `input_tokens`,
`cached_input_tokens`, `cached_write_tokens` and `output_tokens`. A turn's usage is the sum over its
responses, with all input buckets added together and `cached_input_tokens` reported as
`input_tokens_details.cached_tokens`. The top-level `usage` numbers in those events are session totals and are
not used. A turn that fails before the provider answers (an invalid model, say) has no `token_usage` event and
reports none.

## The session

The CLI keeps its session in SQLite at `/mind/.cagent/session.db` (`--data-dir` under the mind). `run` owns the
session id: `hg-<uuid>`, kept in `$HG_STATE/session` and written there before the CLI starts, so a stopped turn
is resumed by the next one with `--session <id>`. Docker Agent creates a session whose id does not exist yet,
so a lost database begins a fresh session under the same id; if the CLI does report a session it cannot load,
`run` clears the id, starts a new one, and runs the turn again.

The mind holds `.cagent/session.db` and, in `.cagent/cache`, the models.dev catalogue the CLI downloads
(about 7 MB). The cache is named in the manifest's `cache`, so it is not saved with the session; the CLI
fetches or embeds it again when it is missing.

## Hosts an environment must allow

Beyond the provider's own host:

| Host | Asked for by | Needed? |
|---|---|---|
| `models.dev` | every turn: the CLI's model catalogue (capabilities, context limits, pricing) | No. The CLI falls back to its embedded/cached catalogue; the turn runs, but context-window information and cost estimates may be missing. |
| the host of each remote MCP server in the request | only a request that names one | Yes, for that request: the CLI connects to it. Allow the host and bind any secret used in its headers. |

Telemetry, update checks and setup are off, so no Docker host is contacted during a turn. The install's hosts
are in the registries and need no `setup.egress` entry.

## What was not tried here

- The OpenAI Responses, OpenAI Chat Completions and Gemini paths: this build session's provider speaks only
  Anthropic Messages, and every case was recorded against it.
- A remote MCP server from the request: the configuration is written as documented, but no server was
  available to call.
- Image inputs (`input_image`): a text file was placed and read; images should reach the agent the same way
  through `read_file`, but were not exercised.
- A closed network in which `models.dev` is refused (the fallback is the CLI's documented behaviour, not
  something observed here).
- Multi-agent agent files, `--sandbox`, Docker Model Runner, and the other serve modes: the package runs the
  single-agent `--exec` path only.
