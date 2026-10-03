#!/usr/bin/env python3
"""Second Brain Link — MCP server (stdio). Stdlib only; talks JSON-RPC over stdin/stdout, so it
opens no port. Lets any MCP client (Claude Desktop, Claude Code, Codex, an IDE) read a built brain:

  sbl_ask       graph retrieval — the notes and relations that answer a question
  sbl_query     exact answers by SQL (read-only): counts, people at a company, dormant ties…
  sbl_inbox     what needs you: reports with news, questions waiting, suggestions
  sbl_routines  routines and when they run
  sbl_sources   which exports a folder contains (dry run, nothing written)
  sbl_build     build a brain from an export (writes the brain folder you name)

Register it in your MCP client as:  python3 /path/to/second-brain-link/integrations/mcp/server.py
This shim lives OUTSIDE engine/: the engine's stdlib-only, zero-network promise is about engine/,
and so is this server's — it only runs the engine's own scripts.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
S = ROOT / "engine" / "scripts"
VERSION = "0.1.0"

TOOLS = [
    {"name": "sbl_ask", "description": "Graph retrieval over a built brain: the notes and typed relations that best answer a question.",
     "inputSchema": {"type": "object", "properties": {"brain": {"type": "string", "description": "path to a built brain"},
                                                      "question": {"type": "string"}, "as_role": {"type": "string"}},
                     "required": ["brain", "question"]}},
    {"name": "sbl_query", "description": "Exact answers by SQL over a brain (read-only). ask: counts | people-at | dormant-strong | orgs-by-people | runs; or a SELECT in sql.",
     "inputSchema": {"type": "object", "properties": {"brain": {"type": "string"}, "ask": {"type": "string"},
                                                      "arg": {"type": "string"}, "sql": {"type": "string"}}, "required": ["brain"]}},
    {"name": "sbl_inbox", "description": "What needs the user in this brain: reports with news, runs waiting, suggestions to review.",
     "inputSchema": {"type": "object", "properties": {"brain": {"type": "string"}}, "required": ["brain"]}},
    {"name": "sbl_routines", "description": "The brain's routines: schedule, whether each is on, and what runs next.",
     "inputSchema": {"type": "object", "properties": {"brain": {"type": "string"}}, "required": ["brain"]}},
    {"name": "sbl_sources", "description": "Detect which exports (LinkedIn, Google Takeout, Slack…) a folder contains. Writes nothing.",
     "inputSchema": {"type": "object", "properties": {"export": {"type": "string"}}, "required": ["export"]}},
    {"name": "sbl_build", "description": "Build a brain from an export folder into an output folder (local, zero network).",
     "inputSchema": {"type": "object", "properties": {"export": {"type": "string"}, "out": {"type": "string"},
                                                      "refresh": {"type": "boolean"}}, "required": ["export", "out"]}},
]


def run(*args, timeout=600):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=timeout,
                       env={**__import__("os").environ, "PYTHONUTF8": "1"})
    out = (r.stdout or "").strip()
    if r.returncode != 0 and not out:
        out = (r.stderr or "").strip()[-2000:] or f"exit {r.returncode}"
    return out


def call(name, a):
    if name == "sbl_ask":
        args = [S / "retrieval.py", a["brain"], a["question"], "--prompt"]
        if a.get("as_role"):
            args += ["--as", a["as_role"]]
        return run(*args)
    if name == "sbl_query":
        if a.get("sql"):
            return run(S / "query.py", a["brain"], "--sql", a["sql"])
        return run(S / "query.py", a["brain"], "--ask", a.get("ask") or "counts", *([a["arg"]] if a.get("arg") else []))
    if name == "sbl_inbox":
        return run(S / "harness.py", "--brain", a["brain"], "--json", "inbox")
    if name == "sbl_routines":
        return run(S / "harness.py", "--brain", a["brain"], "--json", "due")
    if name == "sbl_sources":
        return run(S / "build_vault.py", a["export"], "--dry-run")
    if name == "sbl_build":
        return run(S / "build_vault.py", a["export"], "-o", a["out"], *(["--refresh"] if a.get("refresh") else []))
    raise ValueError("unknown tool " + name)


def reply(i, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": i}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, i, p = m.get("method"), m.get("id"), m.get("params") or {}
        if i is None:  # a notification (e.g. notifications/initialized): no reply
            continue
        try:
            if method == "initialize":
                reply(i, {"protocolVersion": p.get("protocolVersion") or "2025-06-18", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "second-brain-link", "version": VERSION}})
            elif method == "tools/list":
                reply(i, {"tools": TOOLS})
            elif method == "tools/call":
                text = call(p.get("name"), p.get("arguments") or {})
                reply(i, {"content": [{"type": "text", "text": text[:60000]}], "isError": False})
            elif method == "ping":
                reply(i, {})
            else:
                reply(i, error={"code": -32601, "message": "method not found: " + str(method)})
        except Exception as e:  # a tool failure is a result the client can show, not a crash
            reply(i, {"content": [{"type": "text", "text": "error: " + str(e)}], "isError": True})


if __name__ == "__main__":
    main()
