# kimi — Kimi Code CLI as its makers ship it

A harness package for **Kimi Code CLI** (Moonshot AI), the `kimi` command from the npm package
[`@moonshot-ai/kimi-code`](https://www.npmjs.com/package/@moonshot-ai/kimi-code). This is the TypeScript/Node
CLI (2.x), not the older Python `kimi-cli`. It installs the CLI at the version its makers publish and runs it
in its own non-interactive **print mode**, translating its `stream-json` output into Responses events.

- Pinned CLI version: **2.6.3** (package revision `1`).
- Mind: `~/.kimi-code` (`KIMI_CODE_HOME`), where the CLI keeps its sessions, config and logs.

## What the image and the provider must give

| | |
|---|---|
| Image | Node.js **22.19 or later** and npm (both in the platform's default image; `install` checks them) |
| Runtime | `python3` for `run` (platform default image) |
| Provider | A base URL, a key and a model that the CLI can reach through the provider's API; the key is handed over as `HG_PROVIDER_KEY` (a placeholder the platform's proxy replaces) |

The package speaks three provider APIs, in this order:

| `HG_PROVIDER_API` | CLI provider type | `HG_PROVIDER_URL` |
|---|---|---|
| `anthropic` | `anthropic` (Anthropic Messages) | the provider's Anthropic base URL, without `/v1` |
| `openai-chat` | `openai` (Chat Completions) | the provider's OpenAI base URL, ending in `/v1` |
| `openai-responses` | `openai_responses` (Responses API) | the same |

## The CLI's command

```
kimi --output-format stream-json -p "<the turn's brief>" --session <id>
kimi --output-format stream-json -p "<the turn's brief>" --continue
```

`-p` is print mode: one prompt, no TUI. Print mode always runs in the CLI's `auto` permission mode, so tools
run without prompting. The CLI is told:

| Variable / file | |
|---|---|
| `KIMI_CODE_HOME` | `$HOME/.kimi-code` |
| `KIMI_CODE_NO_AUTO_UPDATE=1` | no update preflight |
| `KIMI_DISABLE_TELEMETRY=1` | no telemetry |
| `KIMI_CODE_TRUST_WORKSPACE=1` | the work folder is trusted without a prompt |
| `$KIMI_CODE_HOME/config.toml` | written each turn: the provider (`type`, `base_url`) and the model alias `harness`; the key is read from `HG_PROVIDER_KEY` through `api_key_env`, so no key or placeholder is ever written to a file |
| `$KIMI_CODE_HOME/mcp.json` | written each turn from the request's `mcp` tools (see below) |

The provider key is passed to the CLI only as an environment variable; the file names that variable, never its
value. The model alias declares a **131072-token context window** (the request does not carry a context size);
the CLI compacts the conversation against that figure.

## Request fields

| In the request | Where it goes |
|---|---|
| `input` (a string or user messages) | the prompt, through `request.brief()` |
| `instructions` | in front of the prompt (`request.brief()`); the CLI has no system-prompt option, and its `AGENTS.md` files are persistent, so instructions are not written there |
| the handover line and the files of the request | in the prompt (files are placed under `inputs/` in the work folder) |
| `model` | the model id of the model alias `harness` in `config.toml` |
| the provider's base URL and key | `[providers.harness]` in `config.toml`; the key via `api_key_env` |
| `reasoning.effort` (one of `low`/`medium`/`high`/`xhigh`/`max`) | `[models.harness] capabilities = ["thinking"]`, `support_efforts`, `default_effort`, and `[thinking] enabled/effort`. Other effort values are ignored |
| `max_output_tokens` | `max_output_size` on the model alias, which only the `anthropic` provider reads |
| `tools` of type `mcp` | `$KIMI_CODE_HOME/mcp.json`: `server_url` → `url`, `headers` → `headers`, `allowed_tools` → `enabledTools`. The file mirrors this request; a server the request no longer names is removed |

Not honoured (no CLI option): `text.format`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`,
`metadata`. None of them changes what the rest of the turn does. `text.format` in particular cannot be
enforced: the CLI prints text, not a caller-chosen JSON schema.

## What the CLI does, and what is printed

The CLI prints one JSON object per line in `stream-json` mode. `run` maps them as follows.

| The CLI's line | Printed |
|---|---|
| `{"role":"assistant","content":"…"}` | a streamed `message` (`emit.say`) |
| `{"role":"assistant","tool_calls":[…]}`, then `{"role":"tool",…}` | the matching call, printed when its result arrives |
| a `Bash` call and result | `shell_call` + `shell_call_output`; the tool merges stdout and stderr, so both are printed as `stdout`; a trailing `Command failed with exit code: N.` becomes the `exit_code`; a timeout is `124` |
| a successful `Write` (`Wrote N bytes to …` / `Appended …`) | `apply_patch_call` with `create_file` and the content as a `+` diff |
| a successful `Edit` (`Replaced N occurrence(s) in …`) | `apply_patch_call` with `update_file` and the old/new strings as a `-`/`+` diff |
| an `mcp__server__tool` call | `mcp_call` (arguments, output, `completed`) |
| any other tool (`Read`, `Grep`, `Glob`, `TodoList`, `Agent`, `Skill`, `FetchURL`, background task tools, …) | `custom_tool_call` + `custom_tool_call_output` (`emit.used`) |
| `session.resume_hint` | saved as the session id; nothing printed |
| `turn.step.retrying`, unknown meta lines | `hg.log` |
| the end of a finished turn | `hg.done` with usage |

The CLI's `stream-json` writer discards thinking deltas, so **no reasoning items** are printed. A tool result
that the CLI considers an error is still plain text in `stream-json`: file-tool errors are reported as
`custom_tool_call`, and an MCP tool result has no error flag, so it is reported as `completed` with its text.

## Token usage

The CLI does not print usage in `stream-json` mode. It records it in the session's wire log under the mind:

```
$KIMI_CODE_HOME/sessions/<workspace>/<session>/agents/<agent>/wire.jsonl
```

Each model step appends `{"type":"usage.record","usageScope":"turn","usage":{"inputOther":…,"output":…,
"inputCacheRead":…,"inputCacheCreation":…}}`. `run` notes the size of every `wire.jsonl` before the turn and
sums the `usageScope: "turn"` records added during it, across the main agent and any subagents, then reports:

- `input_tokens` = `inputOther` + `inputCacheRead` + `inputCacheCreation`
- `output_tokens` = `output`
- `input_tokens_details.cached_tokens` = `inputCacheRead`

A turn that failed before the provider produced anything (for example an unknown model) has no usage and
prints none.

## Session continuation

- The CLI's sessions live under `$KIMI_CODE_HOME/sessions/` in the mind, so they are restored with the session.
- The `session.resume_hint` line names the session id; `run` saves it with `state.set("session", …)` the moment
  it is read. The next turn resumes with `--session <id>`.
- If a stopped first turn left no id in the state, the next turn uses `--continue`, the CLI's own "most recent
  session for this working directory". On an empty mind the CLI says there is nothing to continue and starts a
  new session.
- If the CLI says the saved session **is not found** (or was created under another directory), `run` logs it,
  clears the saved id, and runs the turn as a new session.
- A stopped turn is sent `SIGTERM`; the CLI flushes its session wire and exits (it needs up to about ten seconds
  to do so, hence `run.stop_grace_s: 15`). `run` prints no terminal line and starts nothing else.

## Hosts an environment must allow

The install asks only for **`registry.npmjs.org`** (the npm registry), which the package-manager list already
covers; an environment whose network is `limited` needs no extra `setup.egress`.

A turn asks for **the provider's host** only. With updates and telemetry switched off, the CLI made no other
request in the trials. In particular it works without `code.kimi.com`, `api.kimi.com`, `api.moonshot.ai`, or
the models.dev catalogue.

Two features can reach other hosts, and the environment decides:

- **MCP servers**: every `server_url` in the request must be reachable by the turn. A localhost server bypasses
  the proxy and needs no allow entry; a remote one does.
- **`FetchURL`**: the tool fetches the URL the agent chooses. It works without any allow entry until the agent
  uses it; the host it names must then be allowed.

## What an operator must set

Nothing in the manifest: no settings and no secrets. The package needs only the provider's base URL, key and
model, which the platform gives every turn. An environment must carry the harness (and provide Node.js 22.19+
for the install) and be chosen for the request as
`<environment>/kimi/<provider>/<model>`.

The request's MCP `headers` are written to `$KIMI_CODE_HOME/mcp.json` in the mind, so that the CLI can attach
them to its MCP requests. Do not put a real credential in them unless it is acceptable for it to be kept in the
session's saved mind.

## What was tried

- Install from npm at 2.6.3 on this image; `kimi --version` checked.
- Real turns against an Anthropic-protocol provider: text only; a file written and a command run; a resumed
  turn; a stopped turn and the turn after it; a provider error (an unknown model); a successful and a failing
  shell command; a `Write` followed by an `Edit`; an MCP server (a minimal local HTTP server) called through
  the request, with its `mcp_call` output checked.
- All three provider paths — `anthropic`, `openai-chat` and `openai-responses` — against the provider available
  here.
- **Not tried**: reasoning output (the CLI's `stream-json` writer drops it); a remote MCP server reached through
  the proxy; a subagent's token usage (the summing includes subagent wire logs, but a subagent was not run in a
  trial).
