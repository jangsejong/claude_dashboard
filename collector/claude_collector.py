#!/usr/bin/env python3
"""
Claude Code usage collector.

Reads ~/.claude/projects/**/*.jsonl (local logs only; Claude Code Max does NOT
provide an API), extracts token usage from assistant turns, and POSTs to the
Usage API. Run on each developer's machine (e.g. cron every 5 min).
"""

import argparse
import json
import os
import sys
from pathlib import Path
import time as _time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_CLAUDE_HOME = os.path.expanduser("~/.claude")
STATE_FILE = os.path.expanduser("~/.claude-usage-collector-state.json")
FAILURES_FILE = os.path.expanduser("~/.claude-usage-collector-failures.jsonl")
BATCH_SIZE = 100


def decode_project_slug(slug: str) -> str:
    """Convert URL-encoded project path back to filesystem path.

    Claude stores project dirs like '-home-tsp--03-workspace' where '--' escapes
    a literal dash. We split on single '-' (path separator) and rejoin with '/'.
    """
    if not slug or slug == "-":
        return "(root)"
    # Claude CLI encodes paths: '/' -> '-', literal '-' -> '--'
    # Restore by replacing '--' with a placeholder, splitting on '-', then restoring dashes.
    placeholder = "\x00"
    restored = slug.replace("--", placeholder)
    parts = restored.split("-")
    parts = [p.replace(placeholder, "-") for p in parts]
    # First part is empty if slug started with '-' (absolute path)
    path = "/".join(parts)
    if slug.startswith("-"):
        path = "/" + path[1:]  # remove leading empty segment, add /
    return path or slug


def collect_from_file(
    path: Path,
    project_slug: str,
    last_line_num: int,
) -> tuple[list[dict], int]:
    """Read jsonl from path from line last_line_num+1; return (usage dicts, new last_line_num)."""
    records = []
    line_num = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_num += 1
                if line_num <= last_line_num:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage")
                if not usage or not isinstance(usage, dict):
                    continue
                inp = int(usage.get("input_tokens") or 0)
                out = int(usage.get("output_tokens") or 0)
                if inp == 0 and out == 0:
                    continue
                ts = obj.get("timestamp")
                if isinstance(ts, str):
                    try:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except Exception:
                        created = datetime.now(timezone.utc)
                else:
                    created = datetime.now(timezone.utc)
                records.append({
                    "user_name": "",  # filled by caller
                    "machine": "",
                    "project": decode_project_slug(project_slug),
                    "model": msg.get("model") or "unknown",
                    "input_tokens": inp,
                    "output_tokens": out,
                    "session_id": obj.get("sessionId") or path.stem or "",
                    "message_uuid": obj.get("uuid") or "",
                    "created_at": created.isoformat(),
                })
    except (OSError, PermissionError) as e:
        print(f"Skip {path}: {e}", file=sys.stderr)
    return records, line_num


def find_jsonl_files(claude_home: str) -> list[tuple[Path, str]]:
    """Return [(path, project_slug), ...] under claude_home/projects."""
    projects_dir = Path(claude_home) / "projects"
    if not projects_dir.is_dir():
        return []
    out = []
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        slug = proj_dir.name
        for p in proj_dir.rglob("*.jsonl"):
            if p.is_file():
                out.append((p, slug))
    return out


def load_state() -> dict:
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def append_failure(record: dict) -> None:
    with open(FAILURES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Collect Claude Code usage from local logs")
    parser.add_argument("--user", default=os.environ.get("USER", "unknown"), help="Developer user name")
    parser.add_argument("--machine", default=os.environ.get("HOSTNAME", "unknown"), help="Machine name")
    parser.add_argument("--claude-home", default=DEFAULT_CLAUDE_HOME, help="Path to ~/.claude")
    parser.add_argument("--api-url", default=os.environ.get("CLAUDE_USAGE_API_URL", "http://localhost:8000"), help="Usage API base URL")
    parser.add_argument("--api-key", default=os.environ.get("API_KEY"), help="Bearer token for API")
    parser.add_argument("--full-scan", action="store_true", help="Ignore state file and send all records (server will upsert)")
    args = parser.parse_args()

    state = {} if args.full_scan else load_state()
    all_records = []
    new_state = dict(state)

    for path, project_slug in find_jsonl_files(args.claude_home):
        key = str(path)
        last = state.get(key, 0)
        records, line_num = collect_from_file(path, project_slug, last)
        for r in records:
            r["user_name"] = args.user
            r["machine"] = args.machine
            all_records.append(r)
        new_state[key] = line_num

    if not all_records:
        save_state(new_state)
        print("No new usage records.")
        return 0

    url = f"{args.api_url.rstrip('/')}/usage"
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    saved = 0
    for i in range(0, len(all_records), BATCH_SIZE):
        batch = all_records[i : i + BATCH_SIZE]
        for attempt in range(3):
            try:
                r = requests.post(url, json=batch, headers=headers, timeout=30)
                r.raise_for_status()
                data = r.json()
                saved += data.get("saved_count", len(batch))
                break
            except Exception as e:
                if attempt == 2:
                    for rec in batch:
                        append_failure(rec)
                    print(f"Failed to send batch: {e}", file=sys.stderr)
                else:
                    _time.sleep(2 ** attempt)
    save_state(new_state)
    print(f"Sent {saved} usage records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
