# pi

pi, unmodified, at version 1.5.2.

- **Provider APIs:** Anthropic Messages, OpenAI Responses, OpenAI Chat Completions, in that order of
  preference.
- **Installed with:** npm (`@earendil-works/pi-coding-agent`), under `/harness/tools`. The image needs
  Node.js 22.19 or later and Python 3.
- **Session:** kept by pi under `~/.pi`; continued with `--continue`.
- **Output:** text and reasoning word by word; `bash` as shell calls; `write`, `edit` as file changes; every
  other tool as a custom tool call.
- **Request fields honoured:** `instructions`, put in front of the prompt; input files and images (put under
  `inputs/` in the work folder, and named to the agent).

What this package handles for you: pi learns of the provider from `~/.pi/agent/models.json`, which is
written before every turn.
