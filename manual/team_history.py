"""Print full team history for a session.

Usage: uv run python -m manual.team_history SESSION_ID
"""

import argparse

import httpx

BASE = "http://localhost:8000/api"


def print_history(base: str, sid: str):
    r = httpx.get(f"{base}/team/{sid}/history", params={"limit": 1000})
    r.raise_for_status()
    data = r.json()

    lead = data["lead"]
    _print_agent(lead["agent_name"], lead["messages"], is_lead=True)

    for mb in data.get("members", []):
        _print_agent(mb["name"], mb["messages"])

    total = len(lead["messages"]) + sum(
        len(mb["messages"]) for mb in data.get("members", [])
    )
    done_ct = sum(
        1
        for mb in data.get("members", [])
        for m in mb["messages"]
        if m.get("content") == "[DONE]"
    )
    social_ct = 0
    for mb in data.get("members", []):
        for m in mb["messages"]:
            for t in m.get("tool_calls") or []:
                if t["function"]["name"] == "send_message":
                    a = t["function"]["arguments"].lower()
                    if any(
                        w in a
                        for w in ["hello", "ready", "hi ", "ok", "chào", "sẵn sàng"]
                    ):
                        social_ct += 1

    # Me count unique IDs
    all_ids = [m["id"] for m in lead["messages"]]
    for mb in data.get("members", []):
        all_ids += [m["id"] for m in mb["messages"]]
    dupes = len(all_ids) - len(set(all_ids))

    print("\n--- summary ---")
    print(f"total: {total} | [DONE]: {done_ct} | dupes: {dupes} | social: {social_ct}")


def _print_agent(name: str, messages: list, *, is_lead: bool = False):
    label = f"{name} [lead]" if is_lead else name
    print(f"\n{'=' * 60}")
    print(f"  {label}: {len(messages)} msgs")
    print("=" * 60)
    for i, m in enumerate(messages, 1):
        role = m["role"]
        content = (m.get("content") or "")[:140]
        extra = m.get("extra")
        tc = m.get("tool_calls")

        if tc:
            for t in tc:
                fn = t["function"]["name"]
                args = t["function"]["arguments"][:120]
                print(f"  {i:2d}. [{role}] CALL {fn}({args})")
        elif role == "user" and extra:
            # Me support both old (from_agent) and new (from_agents) format
            frm = extra.get("from_agent") or ",".join(extra.get("from_agents", ["?"]))
            bcast = " [broadcast]" if extra.get("is_broadcast") else ""
            print(f"  {i:2d}. [{role}] from={frm}{bcast} | {content}")
        else:
            print(f"  {i:2d}. [{role}] {content}")


def main():
    p = argparse.ArgumentParser(description="Print team session history")
    p.add_argument("session_id", help="Team session ID")
    p.add_argument("--base", default=BASE)
    args = p.parse_args()
    base = args.base.rstrip("/")

    print_history(base, args.session_id)


if __name__ == "__main__":
    main()
