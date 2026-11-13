# Tailoring: an organization's agent as a package

A tailored package is one package: the CLI, headless in the sandbox, and what makes it this organization's
agent. What it is for, what it may do, what it may reach, and what an operator sets. It is versioned,
reviewed and installed like any other, under a name of its own.

## The questions

One message, numbered, each with the answer you would pick. Skip what the request already answered.

| Ask | Where the answer goes |
|---|---|
| What is the agent for, and what does a typical request look like? | The instructions; the tools; the hosts |
| Who calls it, and how must it answer (prose, files in the work folder, JSON)? | The instructions; the README |
| Which CLI? (or: recommend one for this provider and purpose) | `install`, `run`, `apis` |
| What must it reach: repositories, internal services, MCP servers? | `run.egress`; `secrets` bound to those hosts |
| What must it never do: paths, commands, hosts, kinds of change? | The CLI's own permission rules and hooks |
| What should an operator change without editing the package? | `settings`, `secrets` |

Then the plan, as a short table, and a go.

## Where each thing lives

A turn sees the package in two places, and they behave differently:

| | `/harness` (the package itself) | `seeds/mind/` (copied into `$HOME`) |
|---|---|---|
| When | Every turn, as installed | Once: at a session's first turn. A file that is already in the mind is left alone. |
| Can the agent change it | No: read-only | Yes: the mind is the agent's |
| After the package is upgraded | The next turn of every session has the new files | Sessions that exist keep what they were given |

So:

- **What must hold on every turn goes in the package, and `run` hands it to the CLI every turn:** by an
  option naming a file under `$HG_HARNESS` (a settings file, an MCP configuration, a system prompt), or by a
  variable. The agent cannot edit it, and an upgrade reaches every session.
- **What the agent may keep and grow goes in `seeds/mind/`:** starting notes, a memory file, skills it may
  extend. Call `hgkit.seed_mind()` at the start of `run`.

When a CLI will only read a rule from its own folder under `$HOME`, have `run` write that file from the
package's copy at the start of every turn, and say in the README that the agent could change it during a
turn and that it is put back at the next.

| Layer | Mechanism | Who enforces it |
|---|---|---|
| Purpose, voice, what it declines | The CLI's instructions, from a file in the package | The model, as instructed |
| Which tools, commands and paths | The CLI's own permission rules and pre-tool hooks, from files in the package | The CLI, before each tool call |
| MCP servers, and which of their tools | The CLI's MCP configuration, written by `run`: the package's own servers, then the request's (`request.mcp_servers`) | The CLI |
| Credentials | `secrets` in the manifest, each bound to hosts | The platform's proxy: placeholders inside, real values only toward those hosts |
| Which hosts at all | `run.egress`, and the hosts of its secrets | The proxy, outside the sandbox |
| What the operator sets | `settings`: variables in the turn | `run` passes them to the CLI |
| Provider and model | Set on the installed harness by the organization, or named in the request | The platform |
| Time, CPU, memory, disk, image | The environment the request names | The platform |

The last two are not the package's. When the purpose needs a longer turn or another image, the README says
which environment to create and how the model is then named (`<environment>:<name>/…`).

The outer layers (the proxy, the placeholders, the sandbox) hold whatever the agent does. The inner ones
(the CLI's own rules) make it this agent and not a general one; they can never widen what the outer ones
allow. Narrowing is safe. A tailored package grants nothing the purpose does not need.

## What to find out about the CLI

Beyond what every package needs (`BUILDER.md`), from its current documentation:

1. How it is given standing instructions: an option taking text or a file, or only a file under `$HOME`.
2. How it allows and denies tools: allow and deny lists, patterns for commands and paths, an approval mode;
   and how that mode is made to never ask (there is no one to answer).
3. Whether it runs hooks before a tool call, and how a hook refuses one: this expresses what lists cannot
   ("no `git push`", "nothing outside `src/`").
4. Where it reads MCP servers from, and whether an option can name the file.

Starting points, each to be checked against the CLI's current documentation before you rely on it:

- *Claude Code*: `--append-system-prompt`; `--settings <file>` with `permissions.allow`, `permissions.deny`
  and `hooks`; `--mcp-config <file or JSON>`; skills under `~/.claude/skills/`. It runs headless with
  `--dangerously-skip-permissions`, so deny rules and hooks are the fence.
- *Codex*: `~/.codex/AGENTS.md`; `~/.codex/config.toml` and `-c key=value` for the approval policy, the
  sandbox mode and MCP servers; `codex exec` runs headless.

When a CLI has no way to deny something the purpose forbids, say so. The README's "may not" table lists
only what the package enforces, and the person decides whether the outer fence is enough.

## Settings and secrets

- A value that is not secret (a project key, a team name, a base URL): a **setting**. The turn gets it as a
  variable when it has a value; `run` passes it on. Give it a `default` when there is a sensible one, and
  `"required": true` when a turn cannot do without it.
- A token for an MCP server or an API: a **secret**, bound to that host. The turn gets a placeholder in the
  variable; put the variable's value where the token goes (a header in the MCP configuration, an
  `Authorization` header the agent is told to send). The proxy swaps it in toward the bound hosts only.

The organization sets both on the installed harness: in the console on the harness's page, or
`PATCH /v1/harnesses/<name>` with `{"settings": {…}}` and `{"secrets": {…}}`. Never put a value in the
package. List in the README which must be set before the first turn.

A secret has no value until then, so a trial cannot make an authenticated call. Pass a stand-in
(`--set EXAMPLE_TOKEN=stand-in`), check that it lands in the right header toward the right host (the trial
lists the hosts), and say in the README that the call itself was not tried.

## Showing that it holds

Two trials, both kept as cases:

```
python3 /harness/guide/trial.py turn /work/<name> "<a typical request>" --fresh --case typical
python3 /harness/guide/trial.py turn /work/<name> "<something it must not do>" --fresh --case refused
```

The second must end with the action refused by the package's own rules: the hook's denial, the CLI's
permission error, or the proxy's `403` in the CLI's output. The README's "may and may not" table then states
what these two showed, and nothing that was only intended.
