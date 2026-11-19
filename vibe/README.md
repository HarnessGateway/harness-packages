# vibe

Mistral Vibe 3.1.3 (the `mistral-vibe` package from PyPI) as its makers ship it, run headless: the `vibe`
coding agent in its programmatic mode, with no wrapper prompt, agents or tools of the package's own.

## What it needs

- **The image**: Linux, Python 3.12 to 3.14 with `venv`, and about 510 MB of free space under
  `$HG_HARNESS/tools`. No root. It wants the image's `python3` to be a GIL-enabled CPython; Vibe's makers do
  not ship free-threaded builds of its native parts.
- **The provider**: an Anthropic Messages, OpenAI Chat Completions, or OpenAI Responses endpoint. This
  session's provider, an Anthropic Messages endpoint, is the one every case below was tried against.
  The provider's key is `HG_PROVIDER_KEY`, a placeholder the platform's proxy replaces; it is never written
  to a file.
- **Nothing from the operator**: this package declares no settings and no secrets.

## Install

`install` picks the image's newest `python3.14`, `python3.13`, `python3.12`, or a `python3` in that range
(the makers build for 3.12 to 3.14), installs uv 0.13.9 from PyPI into `$HG_HARNESS/tools/uv`, then runs the
makers' documented method:

```sh
uv tool install --python <that python> --compile-bytecode mistral-vibe==3.1.3
```

under `$HG_HARNESS/tools/{env,bin}`, and checks that `vibe --version` reports `vibe 3.1.3`. It names no CPU
architecture: uv picks the wheel for the machine. The install reaches only `pypi.org` and
`files.pythonhosted.org`, which every install reaches whatever its environment's network.

## The command

Every turn runs, in `$HG_WORK`:

```sh
vibe -p --output streaming --auto-approve --trust \
     [--resume SESSION_ID] [--system-prompt-file FILE] [--output-dir DIR]
```

with the turn's prompt on standard input (`-p` with no argument reads it there). `--output streaming` is
Vibe's newline-delimited JSON mode: one completed transcript entry per line. `--auto-approve` is what makes a
headless run use its tools at all; without it, a tool call that wants approval is denied. `--trust` trusts
the work folder for the run, so the project's `AGENTS.md` and its `.vibe/config.toml` are honoured, as they
would be in a terminal after the user accepted the trust prompt.

The turn's provider, model and MCP servers are given through Vibe's `VIBE_*` environment layer
(`VIBE_PROVIDERS`, `VIBE_MODELS`, `VIBE_ACTIVE_MODEL`, `VIBE_MCP_SERVERS`). That layer outranks both the
user's `config.toml` and a trusted project's `config.toml`, so a project in `/work` cannot redirect the turn
to another provider or model (an `allowed_models` policy in the project is reset too).
`VIBE_TEST_DISABLE_KEYRING=1` keeps headless startup from probing a keyring the sandbox
does not have; `VIBE_ENABLE_TELEMETRY`, `VIBE_ENABLE_UPDATE_CHECKS`, `VIBE_ENABLE_AUTO_UPDATE`,
`VIBE_ENABLE_NOTIFICATIONS`, `VIBE_ENABLE_PR_MONITORING` and `VIBE_EXPERIMENTS__ENABLE` are turned off.

## The request, onto Vibe

| In the request | Where it goes |
|---|---|
| `input` (a string, or a list of messages) | `request.brief(instructions=False)` on Vibe's standard input; the handover line and the paths of the request's files are in front of it |
| `instructions` | `--system-prompt-file`. Vibe replaces its own instructions and the agent's with the file's text; its general guidance still comes first, and project context and `AGENTS.md` still follow |
| `input_file`, `input_image` | `request.place_files()` puts them in `inputs/` in the work folder (uploaded files, inline base64, and data URLs); the prompt names their paths. Vibe can read images on models that accept them |
| the handover | In the prompt |
| `model` | The model entry's `name` in `VIBE_MODELS`; the fixed alias `harness` is `VIBE_ACTIVE_MODEL` |
| the provider | `VIBE_PROVIDERS`: `HG_PROVIDER_URL` as `api_base`, `HG_PROVIDER_KEY` as `api_key_env_var`, and `api_style` from `HG_PROVIDER_API` (`anthropic` → `anthropic`, `openai-chat` → `openai`, `openai-responses` → `openai-responses`) |
| `reasoning.effort` | The model entry's `thinking`. `minimal` becomes `low`; any other word is passed through as Vibe documents |
| `max_output_tokens` | The model entry's `max_output_tokens` (the per-completion cap, which the Anthropic adapter sends as `max_tokens`) |
| `temperature`, `top_p` | The model entry's `temperature` and `top_p` when they are in range |
| `tools` of type `mcp` | `VIBE_MCP_SERVERS`: `server_label` becomes the name, `server_url` becomes the URL (`streamable-http`; the older `http` transport when the URL ends in `/sse`), `headers` become static auth headers |
| `previous_response_id`, `stream`, `background`, `store` | The platform's; the session is continued from the mind (below) |
| `text.format`, `truncation`, `max_tool_calls`, `parallel_tool_calls`, `user`, `metadata` | Not honoured: Vibe has no option for them, and its generic adapters send no structured-output format. The turn goes on; there is no failure for an unused field |
| `tools` of any other type | Never reach a package |

An MCP server's `allowed_tools` and `require_approval` cannot be expressed in Vibe's server config; all of
its tools are offered, and `--auto-approve` approves them. The MCP server's own host must be one the turn's
environment allows; the package adds no host.

## What is printed

Vibe's streaming entries become Responses events:

| Vibe's entry | Printed as |
|---|---|
| the user's own message (Vibe echoes it) | nothing |
| `message` with `role: assistant` | one `message` item, its text streamed (Vibe emits the message whole, so there is one large delta) |
| `reasoning` | one `reasoning` item with one `summary_text`; a reasoning entry whose text is `[redacted]` (the provider withheld it) is not printed |
| `effect` of kind `shell` | `shell_call` and `shell_call_output` with stdout, stderr and an exit code |
| `effect` of kind `file_write` | `apply_patch_call` with `create_file`, or `update_file` when the file existed (Vibe reports the previous content) |
| `effect` of kind `file_edit` | `apply_patch_call` with `update_file`, a `-`/`+` diff from the old and new strings |
| `effect` of kind `tool` naming an MCP server (`mcp_<server>.<tool>`) | `mcp_call` |
| `effect` of any other kind (`file_read`, `file_search`, `todo`, `scratchpad`, `web_search`, `web_fetch`, `skill`, `subagent`, `worktree`, `process`, `tool`) | `custom_tool_call` and `custom_tool_call_output`, with the tool's name, input and output |
| a failed or cancelled effect | still printed, with the error in its output or stderr |
| `notice`, `callback`, `checkpoint`, an unknown entry | `hg.log` |
| a line that is not JSON | `hg.log` |

The turn ends from Vibe's own `export.json` (written with `--output-dir` and read after the CLI exits):
`finished` is `hg.done`, `length` is `hg.incomplete` with `max_output_tokens`, and every other outcome is
`hg.failed` with the CLI's own message (`infrastructure_failure` becomes `provider_error`; a model refusal is
`refusal`). Usage comes from the export: `input_tokens` with `input_tokens_details.cached_tokens`, and
`output_tokens`.

Two consequences of Vibe's output format are worth knowing. There is no token-by-token streaming: an
assistant message or reasoning entry arrives complete. And a shell effect records whether the call
succeeded, not the command's numeric exit code, so `shell_call_output` carries 0 for success and 1 for
failure.

Under the platform's package check the CLI is not started, so no export exists; a recorded turn with an
answer ends `hg.done` without usage, and a recording with no answer ends `hg.failed` with the generic
`cli_error` message. The turn's stderr — the provider's or CLI's own error — is in the turn log.

## Sessions

Vibe keeps its sessions under `$HOME/.vibe/logs/session` (`$HOME` is the mind), so they come back with the
session. Every streaming entry carries `sessionId`; it is saved with `state.set("session", …)` the moment it
is first seen, not at the end, so a stopped turn is still continued. The next turn passes `--resume
<session id>`.

If Vibe answers a resume with `Session not found` and nothing has been printed to the caller yet, `run`
clears the saved id, says so in the turn log, and runs the turn again as a new session. A stopped turn ends
the way Vibe documents: SIGTERM stops the active turn and writes its export; `run` prints no terminal line,
and the next turn resumes the session. `run.stop_grace_s` is 20 seconds for that cleanup.

## Hosts

- **Install**: `pypi.org` and `files.pythonhosted.org` only. Both are package-manager registries, so no
  environment needs to add them.
- **Turns**: only the provider's host. With this session's provider that was `api.deepseek.com`, reached
  two to six times a turn. Telemetry, crash reporting, experiments, update checks, PR monitoring and the
  model catalog are off, so Vibe's own hosts (`api.mistral.ai`, `chat.mistral.ai`, the console, Sentry and
  the experiments and update endpoints) were never asked for. An environment whose network is `limited`
  needs nothing beyond its provider.
- **A request's MCP servers**: their hosts must be allowed by the turn's environment. The package adds none.
- **A project's own configuration**: because the work folder is trusted, a `.vibe/config.toml` or
  `.vibe/agents/` in `/work` can add hooks, MCP servers or tools; their hosts must be allowed too. It cannot
  change the turn's provider or model (the `VIBE_*` layer outranks it).

## What was and was not tried

Tried, as recorded under `tests/`:

- `hello`: a text-only turn (`hg.done`).
- `command`: writes `hello.py` with `file_write`, runs it with `shell`, answers (`apply_patch_call`, two
  `shell_call`s, messages).
- `resumed`: the next turn, continued by session id.
- `failure`: a model name the provider does not have; Vibe exits 2 with a 400, and the replay of its
  one-entry recording ends `hg.failed`.
- `instructions`: the request's `instructions` reached the model through `--system-prompt-file`.
- `mcp`: a turn whose request names a local MCP server (streamable HTTP), its tool called and printed as
  `mcp_call`.
- Also by hand: a stopped turn (SIGTERM) that ended within its grace, printed no terminal line and was
  resumed by the next turn; a saved session id that does not exist, which was retried as a new session; and
  a project `AGENTS.md`, which was read only because of `--trust`.

Not tried:

- OpenAI Chat Completions and OpenAI Responses endpoints. The adapters are Vibe's and the configuration is
  the same shape, but this session's provider speaks only Anthropic Messages.
- An MCP server over the older SSE transport, and MCP OAuth (only static headers are passed through).
- Inline image and file inputs, subagents, hooks, skills, worktrees, and a provider that streams reasoning
  of its own.
- Windows and macOS; a free-threaded Python; a session corrupt in a way Vibe reports other than
  `Session not found`; very long sessions (compaction is Vibe's own).
- Vibe's exact numeric shell exit codes: they are not in its transcript and are approximated as 0 or 1.

## Installing as a harness

In the console: **Sessions**, this session, **New harness from workspace**, the folder `vibe`; then
**Install**. Through the API: `POST /v1/drafts` with `{"name": "vibe", "session": "<session id>", "path":
"vibe"}`, then `POST /v1/drafts/vibe/install`. Then tick `vibe` in the environment's **Harnesses** (or
`PATCH /v1/environments/<environment>` with the whole `harnesses` list), and name it in a request as
`<environment>/vibe/<provider>/<model>`.
