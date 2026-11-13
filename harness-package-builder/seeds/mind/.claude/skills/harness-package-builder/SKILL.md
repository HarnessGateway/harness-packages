---
name: harness-package-builder
description: Write a HarnessGateway harness package - for a new agent CLI, or a customised version of one that ships. Use for any request to add, wrap, package or customise an agent harness.
---

# Writing a harness package

HarnessGateway runs any agent CLI in a sandbox, behind the OpenAI Responses API. Everything that is
particular to one CLI lives in its **harness package**. The platform knows nothing about any CLI.

A complete, working package is the one you are running from. Read it before you write anything:

- `/harness/harness.json` - the manifest
- `/harness/install` - how the CLI is installed
- `/harness/run` - one turn: starts the CLI, translates what it prints
- `/harness/kit/hgkit.py` - the kit `run` uses; read its docstrings

## What a package is

A folder with:

| File | What it is |
|---|---|
| `harness.json` | The manifest |
| `install` | Executable. Runs once per environment image. Puts the CLI under `/harness/tools`. |
| `run` | Executable. Runs once per turn, in `/work`. |
| `seeds/mind/` | Optional. Files copied into `$HOME` on first use, never overwriting: this is where a customised agent's instructions, skills and settings go. |
| `tests/<case>/` | Optional. `request.json`, a `recording` of the CLI's real output, `expected.jsonl`. |
| `README.md` | What it is, what it needs |

## The manifest

```json
{
  "contract": 1,
  "name": "my-agent",
  "version": "<CLI version>-<package revision>",
  "description": "One sentence.",
  "mind": ".mycli",
  "apis": ["anthropic"],
  "install": { "egress": [], "timeout_s": 900 },
  "run": { "egress": [], "stop_grace_s": 10 },
  "settings": { "NAME": { "description": "...", "default": "..." } },
  "secrets": { "NAME": { "description": "...", "hosts": ["api.example.com"] } }
}
```

- `name`: lower case letters, digits and `-`. It is what requests put in `model`.
- `mind`: the CLI's dot directory under `$HOME`. Other harnesses are pointed at it when they take over.
- `apis`: which provider APIs the CLI can speak, in order of preference: `anthropic` (Anthropic Messages),
  `openai-responses`, `openai-chat` (Chat Completions). `[]` if it needs no model provider.
- `install.egress` / `run.egress`: hosts needed beyond the common package registries (npm, PyPI, GitHub,
  crates.io and the like are always allowed during install) and beyond the provider.
- `settings`: non-secret values the organization may set; they arrive as environment variables.
- `secrets`: values the organization may set; each is bound to the hosts listed. In the sandbox the variable
  holds a placeholder, and the platform's proxy puts the real value in on the way to those hosts only.
- Unknown fields are refused. Setting and secret names are upper case and may not begin `HG_`.

## `install`

Runs as user 10000 with `/harness` writable (for this run only), `HOME=/tmp/home`, and network access to
package registries plus `install.egress`. It must:

- install the CLI **at a pinned version**, by the CLI's own documented method, entirely under
  `/harness/tools`;
- check the version it got, and exit non-zero with a plain message if it is wrong or the image lacks
  something;
- write nowhere else.

Some CLIs cannot be installed that way: they keep their dependencies with the home they run under, or
update themselves in place, so a read-only install shared by many sessions does not work and every
session's mind would carry a copy. When the CLI's makers publish an image, use it instead: `install`
installs nothing, checks that the CLI is on the `PATH` at the pinned version, and when it is not, says
which image to build an environment from and how the model is then named (`<environment>:<harness>/…`).
Say the same in the README. The platform never runs an image's own entrypoint, so `run` starts the CLI
directly.

## `run`

Called as `/harness/run` in `/work`, once per turn. `$HOME` is `/mind`. Both folders stay with the session;
nothing else does. `/harness` is read-only now.

Inputs:

- `/turn/request.json`: the Responses request as sent. `/turn/handover.txt`: one line when another harness
  worked on this session last. `/turn/history.json`: the turns this harness has not seen.
  `/turn/files/<id>/<name>`: uploaded files the request refers to.
- Variables: `HG_MODEL`, `HG_PROVIDER_API`, `HG_PROVIDER_URL`, `HG_PROVIDER_KEY` (a placeholder: pass it to
  the CLI as if it were the key), `HG_STATE` (a folder in the mind for the package's own small state),
  `HG_HANDOVER`, and proxy and certificate variables the CLI must be left to honour.

It prints to standard output one JSON object per line, and nothing else:

- events of the OpenAI Responses stream that describe output, without `sequence_number`;
- `{"type": "hg.log", "text": "..."}` for the turn's log;
- exactly one terminal line, last: `{"type": "hg.done"}`, `{"type": "hg.incomplete", "reason": ...}` or
  `{"type": "hg.failed", "code": ..., "message": ...}`, each optionally with `usage`.

Then it exits 0. Standard error is free text and goes to the turn's log.

With the kit this is short:

```python
request, emit, state = hgkit.Request(), hgkit.Emitter(), hgkit.State()
hgkit.seed_mind()                                   # copies seeds/mind into $HOME, once
cli = hgkit.Cli([...the CLI's headless command...], env=..., stdin=request.brief())
for line in cli.lines():                            # the CLI's own output, a line at a time
    ...                                             # emit.say / think / ran / wrote / edited / deleted /
                                                    # called / used, as the line calls for
emit.done(usage)                                    # or emit.failed(code, message)
```

Rules that matter:

1. **Continue the CLI's own session.** Keep the CLI's session id with `state.set("session", id)` and resume
   it next turn. If the CLI says the session is gone, start a new one and say so with `emit.log`.
2. **Give the agent the whole brief.** `request.brief()` is what the agent is asked, as one text: the
   handover line when another harness worked on the session last, the request's instructions, where the
   request's files were put (`inputs/` in the work folder), then the prompt. Pass `instructions=False` when
   the CLI takes instructions some other way (a system-prompt flag), and give it `request.instructions`
   there.
3. **Translate only your own CLI's output.** Never read another harness's files or formats.
4. **Never write a secret anywhere.** The key the CLI is given is a placeholder; keep it that way.
5. **No interaction.** The CLI must run headless and act without asking for permission: the sandbox is the
   safety boundary.

## Finding out how a CLI behaves

Before writing `run`, find out, from the CLI's documentation and by running it:

- how it is installed, and how to pin its version;
- its headless command, and its flag for JSON or streaming output;
- how it is told a provider's base URL, key and model;
- where it keeps its session (its dot directory), and how a session is continued;
- how it is told to act without asking.

## A customised version of a CLI that ships

Copy the shipped package, give it a new `name`, and put what makes it yours under `seeds/mind/`: the
instructions file the CLI reads, skills, settings. Leave `install` and `run` as they are unless the CLI
itself must behave differently.

## Tests

For each case, a folder `tests/<case>/` with `request.json` (the request body) and `recording` (the CLI's real
standard output for that request, captured once). To capture one, ask for an environment with the variable
`HGKIT_RECORD=/work/recording` and run a turn: the kit copies the CLI's raw lines there.

Outside the sandbox, `harnessgateway package check <folder>` validates the package and replays each
recording through `run`; `--record` writes each case's `expected.jsonl`.

## When the package is written

Tell the person the folder's name, and that it is added with either:

- the console: open this session under Sessions, press **New harness from workspace** and give the folder. It
  opens as a draft, where every file can be read and edited; **Install** makes it a harness; or
- `POST /v1/harnesses` with `{"session": "<this session's id>", "path": "<folder>"}`.

The session's id is in the variable `HG_SESSION`.
