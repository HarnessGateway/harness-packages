# fast-agent harness package

**fast-agent** (the PyPI package `fast-agent-mcp`), version **0.10.57**, as its makers ship it: a coding agent
with its shell, file and MCP tools, run headless one turn at a time. The package adds no instructions, no
permission rules and no MCP servers of its own; it installs the CLI and translates its Agent Client Protocol
(ACP) output into Responses events.

- Manifest name: `fast-agent`; version `0.10.57-1`
- Provider APIs: `anthropic`, `openai-chat`, `openai-responses`, `gemini` (in that order)
- Mind folder: `.fast-agent` (`$HOME/.fast-agent`)

## What it needs

- An image with `python3` **3.12 to 3.15** and its `venv`/`ensurepip` module. `install` creates a private
  virtual environment at `$HG_HARNESS/tools/venv` and installs the pinned wheel with pip; nothing is installed
  into the image itself.
- At install time, PyPI: `pypi.org` and `files.pythonhosted.org`. Both are in the platform's registry group, so
  the default install network suffices; no `setup.egress` entry is needed for them.
- At turn time, the request's provider host (the platform's provider, not a host this package adds). Remote MCP
  servers named by a request need their own hosts allowed by the environment (see below).

## The command

Each turn `run` starts one `fast-agent` process:

```
$HG_HARNESS/tools/venv/bin/fast-agent --no-update-check acp \
  -c   $HG_STATE/fast-agent.yaml \
  --home $HG_MIND/.fast-agent \
  --model <provider>.<model>[?reasoning=<effort>] \
  -x --no-permissions \
  [-i $HG_STATE/instructions.md]
```

- `acp` is fast-agent's machine-readable stdio server: JSON-RPC 2.0, one object per line on stdout. That is the
  surface this package translates; fast-agent's one-shot `go` mode prints human-oriented text and has no
  JSON-lines output.
- `-x` gives the agent its local shell and file tools, as the makers' coding setup documents.
- `--no-permissions` makes it act without asking (there is no one to answer).
- `--no-update-check` turns off the startup check for fast-agent/plugin updates and recommended plugins.
- `--home` puts fast-agent's own store (sessions, state) under the mind, so it is saved with the session.
- `run` writes the provider config (`fast-agent.yaml`) and, when the request has instructions, the instruction
  file, into `$HG_STATE` at the start of every turn. Both are regenerated each turn; nothing is written under
  `/harness`.

`run` is itself a minimal ACP client. It advertises the `terminal` capability, so fast-agent runs the agent's
shell tool through `run`: `run` creates the process, captures combined stdout/stderr, reports its exit status,
and then closes it. Commands therefore execute in the turn's sandbox, in `run`'s working directory (`/work`)
unless fast-agent supplies another, inheriting the turn's environment (including the proxy variables).

## Request fields

| In the request | Where it goes |
|---|---|
| `input` (string or user messages) | The prompt text sent in `session/prompt` |
| `instructions` | fast-agent's `-i` instruction file, written from the request each turn |
| `input_file`, inline files and images | `request.brief()` puts them in `inputs/` in the work folder and names them in the prompt; the agent opens them with its file tools |
| `model` | `HG_MODEL`, in the ACP model spec `<provider>.<model>` (also the config's `default_model`) |
| provider URL / key | The provider section's `base_url`; the key is the `HG_PROVIDER_KEY` placeholder, which the platform's proxy replaces on the way out |
| `reasoning.effort` | Appended to the model spec as `?reasoning=<effort>`; fast-agent warns and ignores it for models that do not support it |
| `tools` of type `mcp` | ACP `mcpServers` on `session/new` / `session/resume`, as HTTP servers with their headers |
| `previous_response_id` | Nothing: the platform restores the mind, and the package resumes its saved ACP session |

**What the CLI cannot honour:** `temperature`, `top_p`, `max_output_tokens`, `text.format` (and other structured
output), `max_tool_calls`, `truncation`, `user`, `metadata`, `tool_choice`, and a per-turn
`parallel_tool_calls` setting are not passed to fast-agent and have no effect. `stream`, `background` and
`store` are the platform's. Instructions are a property of the CLI session: a later request that carries no
`instructions` leaves the earlier instruction in force, while one that carries instructions replaces them for
that turn onward. An MCP entry's `allowed_tools` is not expressible in ACP; fast-agent exposes the server's
tools as the server publishes them.

## What `run` prints

| fast-agent does | Output |
|---|---|
| streams assistant text (`agent_message_chunk`) | one `message` item, deltas as they arrive |
| streams reasoning (`agent_thought_chunk`) | one `reasoning` item |
| runs its shell tool (`execute`) | `shell_call` and `shell_call_output`, with the command, combined output, and the exit code fast-agent appends as `[Exit code: N]` |
| `write_text_file` | `apply_patch_call` `create_file`, with the content as a `+` diff |
| `edit_file` | `apply_patch_call` `update_file`, with `old_string`/`new_string` as `-`/`+` |
| `delete_file` | `apply_patch_call` `delete_file` |
| calls a tool of a request MCP server | `mcp_call` (server and tool names, arguments, output or error) |
| uses any other tool | `custom_tool_call` + `custom_tool_call_output` |
| ends the prompt | `hg.done` (or `hg.incomplete` for `max_tokens`) |
| fails | `hg.failed` with `provider_error`, `session_error` or `cli_exit` and a message from the CLI |

fast-agent does not disclose local shell arguments in its ACP notifications for every shell path; with the
client's `terminal` capability advertised, the shell goes through `terminal/*` and its command and output are
known, which is the mode this package uses. If a command is started in the background, only its launch is
observed; a later `process` tool call is reported as an ordinary tool call.

### Token usage

fast-agent attaches a status line to its ACP updates and to the answer to `session/prompt`, for example
`1,795 in, 16 out, 2 tools (0.2%)`. The harness reads the last such line of the turn; that number is the
turn's total across all its model calls. It is reported as `input_tokens` and `output_tokens` on the terminal
line. The ACP status line does not expose a cached-token split, so `input_tokens_details` is omitted. A turn
that fails before any model call (an unknown model, say) has no counts and carries none.

## Sessions

fast-agent's home is `$HG_MIND/.fast-agent`; its session store is `$HOME/.fast-agent/sessions/<id>/`. On
`session/new` the harness saves the returned id with `state.set("session", id)` immediately, before the prompt
runs, so a stopped turn is still continued. The next turn calls `session/resume` with that id; if fast-agent
says `Session not found`, `run` logs it, clears the state and runs the turn as a new session. On resume,
fast-agent replays the earlier conversation as `session/update` notifications before answering; the harness
ignores everything before the resume response, so only the new turn's output is reported.

A stopped turn prints no terminal line and starts nothing else: `run` passes the termination signal to the
CLI's process group and to every terminal command it started, then exits. `run.stop_grace_s` is 20 seconds.

## Hosts an environment must allow

- **Install:** `pypi.org` and `files.pythonhosted.org` (platform registries; already reachable for an install).
- **Turns:** the request's provider host only. In the trials that was `api.deepseek.com`, this session's
  provider — not a host the package adds. No other host was asked for.
- **Request MCP servers:** each remote MCP server a caller names (`server_url`) must have its host allowed by
  the environment's `network.allow`; otherwise the agent's calls to it fail. The package cannot add it.
- fast-agent's update check is disabled, so it does not reach fast-agent.ai, GitHub or the plugin marketplace at
  startup.

## What an operator must set

Nothing: this package declares no settings and no secrets. The provider key and URL come from the platform per
turn. An operator choosing an environment must give it a provider whose API is one of the four above and, for
MCP use, allow the MCP hosts.

## What was not tried here

- The `openai-chat`, `openai-responses` and `gemini` routes (only an Anthropic-compatible provider was
  available in this session; the config mapping is written but unexercised).
- Remote MCP servers and their headers (no reachable server in this session), including OAuth and
  `allowed_tools`.
- `edit_file` and `delete_file` (the model used `write_text_file` in the recorded turns), and image inputs
  beyond placing them as files.
- Background/managed shell processes (`run_in_background`), whose later `process` calls are reported only as
  ordinary tool calls.
- Parallel tool calls and their completion order.
- A turn long enough to hit the environment's time limit.
