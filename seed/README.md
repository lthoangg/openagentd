# seed/

Default agents, skills, and configuration shipped to first-time users.

When a user runs `openagentd init`, the CLI copies the contents of this
directory (locally if running from a source checkout, otherwise from the
published GitHub release / `main` branch) into
`{OPENAGENTD_CONFIG_DIR}/`.

Updating these files affects every **new** install. Existing users keep
their own copies untouched — once `openagentd init` has populated their
config dir, those files are theirs to edit. Users who want the newest
prompts or skills can browse this directory and copy what they want
into their own `{OPENAGENTD_CONFIG_DIR}/`.

## Layout

```
seed/
├── agents/                # one .md per agent — exactly one must have `role: lead`
├── skills/                # one subdirectory per skill, each containing SKILL.md
├── mcp.json               # default MCP server config (context7 enabled)
├── multimodal.yaml        # image / video provider config
├── summarization.md       # global summarization config + system prompt
└── title_generation.md    # title-generation config + system prompt
```

`README.md` (this file) is the only top-level item not copied — every
other top-level entry ships, but `init` skips files the user already
has, so re-running `init` after a release won't clobber edits.

## Conventions

- **Lead agent first.** `agents/openagentd.md` is the lead; the others are members.
- **Model placeholder.** Every agent's `model:` field is rewritten by
  `openagentd init` to match the provider/model the user picked.
  After install, users can run `self-healing` to swap individual member
  models (e.g. give the executor a faster model than the lead).
- **No secrets, ever.** These files are public. `mcp.json` should
  reference env vars (`${VAR}`) for any auth headers, never inline
  values.
- **Keep skills self-contained.** Each `skills/<name>/` should run with no
  outside files. Bundle reference scripts and templates in the same dir.
- **Top-level configs are fill-in-gap defaults.** `mcp.json`,
  `multimodal.yaml`, `summarization.md`, `title_generation.md` only
  land if the target file doesn't exist. Existing files are never
  overwritten.
