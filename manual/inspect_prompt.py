"""Reconstruct the full LLM payload for an agent — no server required.

Produces the exact things sent to the provider on every request:
  1. system_prompt        — base prompt + skills section + date injection
  2. system_prompt_final  — same, after MemoryInjectionHook has prepended the
                            pinned memory block + memory index (what the LLM
                             actually sees). Requires the configured memory dir
                             to exist on disk (``.openagentd/data/memory/`` in dev,
                             ``~/.local/share/openagentd/memory/`` in production).
  3. tools                — JSON array of tool definitions (as sent in the API body)

Output is a single JSON object:
  {
    "system_prompt": "...",
    "system_prompt_final": "...",
    "memory_block": "...",
    "tools": [...],
    "stats": { ... }
  }

Paste system_prompt_final + tools JSON into https://platform.openai.com/tokenizer
(or tiktoken) to get an accurate token count.

Usage:
  uv run python -m manual.inspect_prompt
  uv run python -m manual.inspect_prompt --dir .openagentd/agents
  uv run python -m manual.inspect_prompt --agent explorer
  uv run python -m manual.inspect_prompt --no-date
  uv run python -m manual.inspect_prompt --date 2026-04-12
  uv run python -m manual.inspect_prompt --out .openagentd/chat/payload.json
  uv run python -m manual.inspect_prompt --stats-only
  uv run python -m manual.inspect_prompt --no-memory            # skip hook injection
  uv run python -m manual.inspect_prompt --memory-only          # print just the memory block
  uv run python -m manual.inspect_prompt --final-only           # print just the final prompt
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _default_agents_dir() -> str:
    """Resolve the agents directory from settings.

    Falls back to ``.openagentd/config/agents`` (dev-mode default) if settings
    fail to import for some reason.
    """
    try:
        from app.core.config import settings

        return settings.AGENTS_DIR
    except Exception:
        return ".openagentd/config/agents"


DEFAULT_AGENTS_DIR = _default_agents_dir()


# ── Loader helpers ────────────────────────────────────────────────────────────


def _build_skills_section(skills: list[str]) -> str:
    """Replicate loader._build_skills_section() exactly."""
    from app.agent.tools.builtin.skill import discover_skills

    available = discover_skills()
    lines = ["\n## Available skills\n"]
    for skill_name in skills:
        meta = available.get(skill_name, {})
        desc = meta.get("description", "(no description)")
        lines.append(f"- **{skill_name}**: {desc}")
    lines += [
        "",
        "Call `skill` with the skill name to load its full instructions.",
    ]
    return "\n".join(lines)


def _build_tool_definitions(tool_names: list[str]) -> list[dict]:
    """Return tool definition dicts in the order the agent sends them."""
    from app.agent.loader import _default_tool_registry
    from app.agent.tools.builtin.skill import load_skill as _load_skill_tool

    registry = _default_tool_registry()

    # skill tool is always prepended (mirrors loader._build_agent)
    tools = [registry.get("skill", _load_skill_tool)]

    for name in tool_names:
        if name == "skill":
            continue
        if name not in registry:
            print(f"Warning: unknown tool '{name}' — skipped", file=sys.stderr)
            continue
        tools.append(registry[name])

    return [t.definition for t in tools]


def _inject_date(prompt: str, date_str: str) -> str:
    """Replicate inject_current_date hook."""
    return f"{prompt}\n\nCurrent date (UTC): {date_str}"


def _build_memory_block() -> str:
    """Invoke MemoryInjectionHook's block builder — exactly what the hook injects.

    Returns an empty string when the memory root does not exist, mirroring the
    hook's real behaviour.

    An empty query is passed because there is no user message available at
    prompt-inspection time; topic scoring will use no BM25 bias, so all topics
    remain in the residual index (the correct conservative fallback).
    """
    from app.agent.hooks.memory_injection import MemoryInjectionHook

    hook = MemoryInjectionHook()
    return hook._build_memory_block("")


def _apply_memory_injection(system_prompt: str, memory_block: str) -> str:
    """Replicate MemoryInjectionHook.wrap_model_call's prompt merge."""
    if not memory_block:
        return system_prompt
    if system_prompt:
        return f"{system_prompt}\n\n{memory_block}"
    return memory_block


# ── Stats ─────────────────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token (GPT-3/4 average for English+JSON)."""
    return len(text) // 4


def _print_stats(
    system_prompt: str,
    system_prompt_final: str,
    memory_block: str,
    tools_json: str,
    agent: str,
    model: str,
) -> None:
    sp_chars = len(system_prompt)
    final_chars = len(system_prompt_final)
    mem_chars = len(memory_block)
    t_chars = len(tools_json)
    total = final_chars + t_chars
    print(f"\nAgent: {agent}  model: {model}", file=sys.stderr)
    print(
        f"  system_prompt       : {sp_chars:>7,} chars  (~{_estimate_tokens(system_prompt):,} tokens)",
        file=sys.stderr,
    )
    print(
        f"  memory block        : {mem_chars:>7,} chars  (~{_estimate_tokens(memory_block):,} tokens)",
        file=sys.stderr,
    )
    print(
        f"  tools JSON          : {t_chars:>7,} chars  (~{_estimate_tokens(tools_json):,} tokens)",
        file=sys.stderr,
    )
    print(
        f"  tool_count          : {tools_json.count('"type": "function"')}",
        file=sys.stderr,
    )
    print(f"  {'─' * 49}", file=sys.stderr)
    print(
        f"  system_prompt_final : {final_chars:>7,} chars  (~{_estimate_tokens(system_prompt_final):,} tokens)",
        file=sys.stderr,
    )
    print(
        f"  total (final+tools) : {total:>7,} chars  (~{_estimate_tokens(system_prompt_final + tools_json):,} tokens)",
        file=sys.stderr,
    )
    print(file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Reconstruct the full LLM payload (system prompt + tools) for an agent"
    )
    p.add_argument(
        "--dir",
        default=DEFAULT_AGENTS_DIR,
        metavar="DIR",
        help=f"Agents directory with .md files (default: {DEFAULT_AGENTS_DIR})",
    )
    p.add_argument(
        "--agent",
        metavar="NAME",
        help="Agent name to inspect (default: lead agent)",
    )
    p.add_argument(
        "--no-date",
        action="store_true",
        help="Skip date injection (show base prompt only)",
    )
    p.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Override injected date (default: today UTC)",
    )
    p.add_argument(
        "--out",
        metavar="FILE",
        help="Write JSON output to a file instead of stdout",
    )
    p.add_argument(
        "--stats-only",
        action="store_true",
        help="Print char/token estimates only — no JSON output",
    )
    p.add_argument(
        "--no-memory",
        action="store_true",
        help="Skip MemoryInjectionHook — show base prompt only (no memory block)",
    )
    p.add_argument(
        "--memory-only",
        action="store_true",
        help="Print just the injected memory block (plain text) and exit",
    )
    p.add_argument(
        "--final-only",
        action="store_true",
        help="Print just the final system_prompt (after hook injection) and exit",
    )
    args = p.parse_args()

    agents_dir = Path(args.dir)
    if not agents_dir.exists():
        print(f"Error: agents directory not found: {agents_dir}", file=sys.stderr)
        sys.exit(1)

    from app.agent.loader import parse_agent_md

    md_files = sorted(agents_dir.glob("*.md"))
    if not md_files:
        print(f"Error: no .md files in {agents_dir}", file=sys.stderr)
        sys.exit(1)

    configs = []
    for md_path in md_files:
        try:
            cfg = parse_agent_md(md_path)
            configs.append(cfg)
        except Exception as exc:
            print(f"Warning: failed to parse {md_path.name}: {exc}", file=sys.stderr)

    if not configs:
        print("Error: no valid agent configs found", file=sys.stderr)
        sys.exit(1)

    # Select agent
    if args.agent:
        matches = [c for c in configs if c.name == args.agent]
        if not matches:
            names = [c.name for c in configs]
            print(
                f"Error: agent '{args.agent}' not found. Available: {names}",
                file=sys.stderr,
            )
            sys.exit(1)
        agent_cfg = matches[0]
    else:
        # Default to lead
        leads = [c for c in configs if c.role == "lead"]
        agent_cfg = leads[0] if leads else configs[0]

    # List all discovered agents
    print(f"\nDiscovered agents in {agents_dir}:", file=sys.stderr)
    for cfg in configs:
        marker = " <--" if cfg.name == agent_cfg.name else ""
        print(
            f"  {cfg.name:15s} role={cfg.role:6s} model={cfg.model or '(none)'}{marker}",
            file=sys.stderr,
        )
    print(file=sys.stderr)

    # 1. System prompt
    system_prompt = agent_cfg.system_prompt
    if agent_cfg.skills:
        system_prompt += _build_skills_section(agent_cfg.skills)

    # 2. Date injection
    if not args.no_date:
        date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        system_prompt = _inject_date(system_prompt, date_str)

    # 3. Memory injection (MemoryInjectionHook.wrap_model_call)
    if args.no_memory:
        memory_block = ""
    else:
        try:
            memory_block = _build_memory_block()
        except Exception as exc:
            print(f"Warning: memory injection failed: {exc}", file=sys.stderr)
            memory_block = ""
    system_prompt_final = _apply_memory_injection(system_prompt, memory_block)

    # Early exits for focused inspection
    if args.memory_only:
        if not memory_block:
            print(
                "(no memory block — memory root missing or --no-memory set)",
                file=sys.stderr,
            )
            sys.exit(1)
        print(memory_block)
        return
    if args.final_only:
        print(system_prompt_final)
        return

    # 4. Tool definitions
    tool_defs = _build_tool_definitions(agent_cfg.tools)
    tools_json = json.dumps(tool_defs, indent=2, ensure_ascii=False)

    payload = {
        "system_prompt": system_prompt,
        "memory_block": memory_block,
        "system_prompt_final": system_prompt_final,
        "tools": tool_defs,
        "stats": {
            "system_prompt_chars": len(system_prompt),
            "memory_block_chars": len(memory_block),
            "system_prompt_final_chars": len(system_prompt_final),
            "tools_json_chars": len(tools_json),
            "total_chars": len(system_prompt_final) + len(tools_json),
            "tool_count": len(tool_defs),
            "agent": agent_cfg.name,
            "model": agent_cfg.model,
            "role": agent_cfg.role,
            "memory_injected": bool(memory_block),
        },
    }
    output = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Written to {out_path}", file=sys.stderr)
    elif not args.stats_only:
        print(output)

    # Print stats last so they appear as a summary after the JSON payload
    _print_stats(
        system_prompt,
        system_prompt_final,
        memory_block,
        tools_json,
        agent_cfg.name,
        agent_cfg.model or "(none)",
    )


if __name__ == "__main__":
    main()
