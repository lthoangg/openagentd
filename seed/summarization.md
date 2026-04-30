---
# Summarization configuration.
#
# The YAML frontmatter below controls *when* and *how* the summariser runs.
# The Markdown body (everything after the closing '---') is the system prompt
# sent to the summariser LLM. The body is REQUIRED — an empty body raises at
# startup. To disable summarization entirely, set token_threshold: 0.
#
# Fields:
#   model:                provider:model string for the summarizer LLM.
#                         If omitted, each agent's own model is used.
#   token_threshold:      Trigger summarization when prompt tokens reach this
#                         count. Set to 0 to disable globally.
#   keep_last_assistants: Number of most-recent assistant turns kept verbatim.
#   max_token_length:     Max tokens for the summarizer LLM response (0 = no limit).
#
# Per-agent `summarization:` blocks in each agent .md file override these
# values (except `prompt`, which is global-only).

model: googlegenai:gemini-3.1-flash-lite-preview
token_threshold: 100000
keep_last_assistants: 3
max_token_length: 10000
---

You are a conversation summariser. Produce a concise but complete summary of
the conversation so far. Capture key facts, decisions, and outcomes. Write in
third-person narrative form. Do not include pleasantries or meta-commentary.
