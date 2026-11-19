# hermes

Hermes Agent, unmodified, at version 0.23.1.

- **Provider API:** OpenAI Chat Completions.
- **Install:** a checkout of the release under `$HG_HARNESS/tools`, and Hermes's own package manager for its
  Python environment, with Hermes's full feature set. What its terminal and web interfaces and its browser
  tools use (its own Node.js, FFmpeg, a browser, the computer-use driver) is left out: a headless turn uses
  none of it. It takes a few minutes, once for each environment image. The image
  needs `git` and a `python3` of the minor Hermes's package manager pins (3.14 for this version); the
  platform's sandbox image has both.

  Hermes keeps its dependency state with the home that installed it, and every session's home is a new one:
  started the usual way, it would build its dependencies again into each session's mind. So `run` starts it on
  the environment the install built, by its path, which Hermes uses as it is whatever the home. That is the
  layout of Hermes's own image: one read-only install, any number of homes.
- **Session:** kept by Hermes in `~/.hermes`; its id is kept in the package's state and resumed with
  `--resume`. Hermes holds a session whose turn was cut short until that turn is acknowledged, so after a
  turn that was stopped the package runs `hermes sessions discard` before it resumes: the conversation up to
  the stopped turn is kept, and what the stopped turn was asked is not replayed. Hermes reports a session's id
  when a turn ends, so a session whose very first turn was stopped starts again.
- **Output:** text word by word; its `terminal` tool as shell calls; `write_file` and `patch` as file
  changes; every other tool as a custom tool call.
- **Request fields honoured:** `instructions`, put in front of the prompt; input files and images (put under
  `inputs/` in the work folder, and named to the agent).

What this package handles for you: Hermes will not resume a session with a different key on its command
line, so the key is given through the environment; its file tools are told they may write in the work
folder; no messaging platform, scheduler job or service of Hermes's is set up, only the agent, for one turn.
