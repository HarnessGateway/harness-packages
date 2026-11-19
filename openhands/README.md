# openhands

The **OpenHands Software Agent SDK**, as its makers ship it, running headless in a HarnessGateway
sandbox. One request is one turn of the SDK's own default CLI agent: its system prompt, its
condenser, and its three default tools — `terminal`, `file_editor` and `task_tracker`.

- Upstream: <https://github.com/OpenHands/software-agent-sdk>
- Packages: `openhands-sdk==1.62.0` and `openhands-tools==1.62.0` (PyPI)
- Package version: `1.62.0-1`
- Request name: `<environment>/openhands/<provider>/<model>`

This is a **vanilla** package: it adds no instructions, permission rules or purpose of its own. It
uses `openhands.tools.preset.default.get_default_agent(..., cli_mode=True)`, the preset the SDK
ships for its CLI-facing agent, unchanged.

## There is no CLI

The SDK is a Python library; its makers ship no `openhands` executable in these two packages (the
OpenHands CLI is a separate project). The package therefore supplies its own headless entry point:

- `run` starts `driver/openhands_turn.py` with the SDK's virtual environment, through `hgkit.Cli`.
- The driver builds the SDK's default agent, sends the turn's prompt, subscribes to the SDK's typed
  event stream, and prints one JSON line per event on standard output.
- `run` translates those lines into OpenAI Responses events and prints the one terminal line.

Everything the SDK and its dependencies print is redirected to standard error (the turn's log), so
the protocol on standard output is never mixed with a banner, a warning or a traceback.

## What it needs

- **Image:** Python 3.12 or later and `python3 -m venv`. The installer checks this. No root is
  needed. `tmux` is optional: the terminal tool uses it when present and otherwise falls back to its
  subprocess backend (the trials ran on the subprocess backend).
- **Provider:** any provider that offers one of the APIs below. The provider's base URL and the
  placeholder key are passed to the SDK's `LLM`; nothing else is configured.
- **Network:** the provider, plus the host of any MCP server a request names. See “Hosts” below.

## Install

`install` creates `$HG_HARNESS/tools/venv`, installs the two distributions at the pinned version
from PyPI, checks both installed versions, and imports the SDK's default agent and its three tools.
It writes only under `$HG_HARNESS/tools`.

The install asks for `pypi.org` and `files.pythonhosted.org` only — both are on the platform's
package-manager list, so no `setup.egress` entry is needed. The trials confirmed this.

## The provider, onto the SDK

`HG_PROVIDER_API` selects how the model string is handed to LiteLLM and which API mode is used:

| `HG_PROVIDER_API` | `LLM.model` | Mode |
|---|---|---|
| `anthropic` | `anthropic/<HG_MODEL>` | Anthropic Messages |
| `openai-chat` | `openai/<HG_MODEL>` | `api_mode="chat"` |
| `openai-responses` | `openai/<HG_MODEL>` | `api_mode="responses"` |
| `gemini` | `gemini/<HG_MODEL>` | Gemini |

`HG_PROVIDER_URL` becomes `base_url`, and `HG_PROVIDER_KEY` (a placeholder the platform's proxy
replaces on the way out) becomes `api_key`. The key is wrapped in `SecretStr` and is never printed.

**One compatibility shim.** LiteLLM marks every function tool in an Anthropic request with
`"type": "custom"`. Anthropic-compatible endpoints may need the traditional shape without the field;
DeepSeek's, used for these trials, rejects it with `unknown variant 'custom'`. The driver removes
that one field from Anthropic tool definitions before the call, restoring the traditional Anthropic
tool shape (`name`, `description`, `input_schema`).

The SDK also defaults `reasoning_effort` to `"high"`. The driver clears it when the request names no
effort, so nothing is invented; a request's `reasoning.effort` is passed through.

## Request fields

| In the request | Where it goes |
|---|---|
| `input` (string or user messages) | The SDK conversation's user message |
| `instructions` | In front of the prompt (the SDK's system prompt is not replaced) |
| the handover line | In front of the prompt, through `request.brief()` |
| uploaded files and inline files/images | Placed in `inputs/` in the work folder and named in the prompt |
| `reasoning.effort` | `LLM.reasoning_effort` |
| `max_output_tokens`, `temperature`, `top_p` | The corresponding `LLM` fields (LiteLLM drops a parameter the model does not accept) |
| `tools` of type `mcp` | The agent's MCP configuration: `server_url` and `headers` become an HTTP `MCPServer` |
| `model`, `previous_response_id`, `stream`, `background`, `store` | The platform's; the session is restored from the mind |

Not honoured, and deliberately not failed:

- `text.format` — the SDK has no structured-output switch here; the turn logs once that it is not
  enforced.
- `tools` of type `mcp`: `allowed_tools` is not used — every tool the server offers is available.
  Other MCP fields not listed by the SDK's `MCPServer` (for example `require_approval`) are ignored.
- `max_tool_calls`, `truncation`, `user`, `metadata`, `include`, `prompt_cache_key` — no SDK option
  is mapped for them.

## What is printed

| The SDK does | Printed as |
|---|---|
| A `MessageEvent` from the agent | one assistant `message` (`emit.say`) |
| `reasoning_content` / the action's `thought` | `reasoning` items (`emit.think`) |
| `terminal` tool action + observation | `shell_call` + `shell_call_output` (`stdout`, `exit_code`; the SDK's shell merges stderr into the same text, so `stderr` is empty unless the tool failed) |
| `file_editor` `create` | `apply_patch_call` (`create_file`, a `+` diff) |
| `file_editor` `str_replace` / `insert` / `undo_edit` | `apply_patch_call` (`update_file`, a unified diff of the changed lines) |
| `file_editor` `view`, or a failed file edit | a `custom_tool_call`/`custom_tool_call_output` pair |
| an MCP tool call | one `mcp_call` |
| any other tool (`task_tracker`, …) | a `custom_tool_call`/`custom_tool_call_output` pair |
| `finish` | its message as the assistant's `message` |
| a conversation error | `hg.log`, then `hg.failed` with the SDK's error code and detail |
| a failed or stuck run | `hg.failed`; `max_iterations`/`stuck` are named as such |

`run.stop_grace_s` is 15 seconds. A stopped turn prints no terminal line; the kit stops the driver,
the SDK's tool shells, and anything they started.

## Session continuation

- The conversation id is a UUID. It is saved with `state.set("session", …)` as soon as the driver
  reports it, before the prompt is sent, so a stopped turn still continues.
- The SDK persists the conversation under `$HOME/.openhands/conversations/<uuid>/` (events and
  `base_state.json`). The manifest's `mind` is `.openhands`.
- On the next turn the driver opens that conversation, then replaces its LLM with this turn's
  provider/model/key and its MCP configuration with this request's. The SDK's event history, task
  list and tools carry over.
- If the persisted conversation cannot be opened (for example a damaged event log), the driver logs
  it and starts a new conversation in the same turn.

## Token usage

The terminal line carries `usage`. It comes from the SDK's own accounting:
`conversation.state.stats.get_combined_metrics().accumulated_token_usage`, sampled after the user
message is added and again after the run, reporting the difference (the SDK persists cumulative
counts with the conversation). The agent LLM and the condenser LLM are both included.

- `input_tokens` = the SDK's `prompt_tokens` (LiteLLM counts cache reads inside prompt tokens).
- `input_tokens_details.cached_tokens` = the SDK's `cache_read_tokens`.
- `output_tokens` = the SDK's `completion_tokens`.

The SDK has no pricing for an unknown model, so it logs a cost warning for such models; that does
not affect the token counts. A turn that fails before any response reports no usage.

## Hosts

- **Install:** `pypi.org`, `files.pythonhosted.org` — both registries; nothing else.
- **Turns:** the request's provider only (`api.deepseek.com` in the trials). LiteLLM's model cost
  map is read from the installed package (`LITELLM_LOCAL_MODEL_COST_MAP=True`), so it is not
  fetched from GitHub; telemetry, sign-in, update checks and public skill/marketplace downloads are
  not used.
- **MCP:** a request that names an MCP server makes the turn reach that server's host. The
  environment must allow it (`network.allow`); the package cannot and does not add hosts.
- **tmux:** not installed in the trial image; no host is needed for the subprocess fallback.

The manifest declares no host, as the platform requires.

## Operator setup

Nothing is required: the provider, model and key reach the package as turn variables. To use it:

1. Install the harness, then have the environment carry it.
2. Name it in a request as `<environment>/openhands/<provider>/<model>`.

Any `settings` or `secrets` are none for this package. If a later version needs an image with
`tmux`, it still works without it.

## What was not tried here

- The `openai-chat`, `openai-responses` and `gemini` provider APIs: this build environment's
  provider offers only `anthropic`, so only that path was run end to end.
- MCP servers: the mapping is implemented, but no server was reachable from the build environment.
- Image input, very long turns that trigger the condenser, and MCP tools that change mid-turn.
- Anthropic's own hosted API (the tool-shape shim was tested against a compatible endpoint, and
  removing `type: custom` matches the traditional Anthropic shape).

## Test cases

`tests/` holds recordings of real turns, replayed by the platform's checker:

- `hello` — text only, fresh session.
- `command` — `file_editor` creates a file and `terminal` runs it.
- `resumed` — the next turn answers from the earlier conversation's history.
- `failed` — `--set HG_MODEL=no-such-model`; the provider's error is reported as `hg.failed`.

Stopping was tried by hand with `--stop-after 20` during a long terminal command; `run` ended within
its grace, printed no terminal line, and the following turn continued the session.
