# harness-packages

The harness packages that ship with [HarnessGateway](https://github.com/HarnessGateway/harnessgateway):
one folder per agent CLI. Everything that is particular to a CLI is here, and nothing about any CLI is in
the platform.

| Package | CLI | Provider APIs it speaks |
|---|---|---|
| `claude-code` | Claude Code 2.1.323 | Anthropic Messages |
| `codex` | Codex CLI 0.167.2 | OpenAI Responses |
| `pi` | pi 1.5.2 | Anthropic Messages, OpenAI Responses, OpenAI Chat Completions |
| `hermes` | Hermes Agent 0.23.1 | OpenAI Chat Completions |
| `harness-package-builder` | Claude Code, set up to write new packages: with the guide to the package contract, the platform's own checker, and a trial that runs a package inside its sandbox | Anthropic Messages |

"Unmodified" in a package's description means the CLI as its makers ship it: no added instructions, skills
or restrictions. To make an agent of your own, copy a package, give it a new name, put its instructions and
skills under `seeds/mind/`, and add it. Or have it written: add `harness-package-builder`, ask it in the chat for a
package (a CLI's name, or what you need an agent for), install what it wrote from its session's page, and tick
it in an environment.

The `shell` package, the smallest one and the template, is in the platform's own repository
(`packages/shell`), with the guide to writing a package.

## Using one

A new installation of the platform adds every package here, and its `default` environment carries them all.
A package added later, or one that was removed, is added from the catalog:

```
POST /v1/harnesses   {"catalog": "claude-code"}
```

or, in the console: Harnesses, Add from the catalog. A request may name a harness only in an environment that
carries it, so tick it in an environment too: in the console, in the environment's Harnesses checklist; over
the API, with the whole list the environment is to carry:

```
PATCH /v1/environments/default   {"harnesses": ["claude-code", "codex", "harness-package-builder", "pi"]}
```

The environment installs it on its image. Then name it in a request, every part of the model string named:
`environment/harness/provider/model`.

```python
client.responses.create(model="default/claude-code/deepseek/deepseek-flash", input="…")
```

## What each package does

Each has the same three parts:

- `harness.json` says which provider APIs the CLI speaks and which hosts its install needs.
- `install` installs the CLI at a pinned version under `$HG_HARNESS/tools`, by its makers' own method, and
  checks the version.
- `run` starts the CLI headless for one turn, resumes the CLI's own session when it has one, and translates
  each line the CLI prints into OpenAI Responses events.

## Checking a package

```
pip install git+https://github.com/HarnessGateway/harnessgateway
harnessgateway package check claude-code
pytest
```

Every package carries recordings of its CLI's real output under `tests/`. The check replays each through
`run` and holds the result to `expected.jsonl`, so a package's translation is tested without the CLI or a
model.

## Running the real CLIs without a provider

`tools/scripted_model.py` is a model that follows a script, behind the three provider APIs. Pointed at it,
a real CLI can be run end to end through a real platform, for nothing, with the same answer every time. The
recordings here were made that way. `tests/test_live.py` does the same against any platform:

```
HG_TEST_URL=http://localhost:8000 HG_TEST_KEY=hg_… pytest tests/test_live.py
```

It uses a provider named `scripted` unless `HG_TEST_PROVIDER` names another (a real one, with a real key
set on the platform), in which case the same tests run against a real model and assert less about its words.
`HG_TEST_MODEL` names that provider's model; without it, the first of the models the provider lists is used.
Each harness is added, the environment it runs in is made to carry it, and its install there is waited for.
