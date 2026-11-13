# claude-code

Claude Code, unmodified, at version 2.1.323.

- **Provider API:** Anthropic Messages. Any provider with an Anthropic-compatible endpoint works.
- **Installed with:** npm (`@anthropic-ai/claude-code`), under `/harness/tools`. The image needs Node.js 22
  or later and Python 3.
- **Session:** kept by Claude Code under `~/.claude`; its id is kept in the package's state and resumed with
  `--resume`. If Claude Code cannot resume it, a new session is started and the turn's log says so.
- **Output:** text and reasoning word by word; `Bash` as shell calls; `Write`, `Edit` as file changes; MCP
  tools as MCP calls; every other tool as a custom tool call.
- **Request fields honoured:** `instructions` (appended to its system prompt), `tools` of type `mcp`, input
  files and images (put under `inputs/` in the work folder, and named to the agent).

What this package handles for you: Claude Code wants a second, background model
(`ANTHROPIC_SMALL_FAST_MODEL`), which is set to the same model so that it exists at any provider; it is run
with permission prompts off, because the sandbox is the boundary.
