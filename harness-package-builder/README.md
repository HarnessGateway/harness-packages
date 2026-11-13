# harness-package-builder

Claude Code, set up to write harness packages: for an agent CLI the platform does not ship, or for a
customised version of one it does.

It is the `claude-code` package with a skill and an instructions file seeded into the session's mind
(`seeds/mind/.claude/`). Its `install` and `run` are `claude-code`'s, byte for byte.

Ask it for a package; it writes one as a folder in the session's work. Add that folder as a harness with
`POST /v1/harnesses {"session": "sess_…", "path": "<folder>"}`, or in the console.
