# integrations/ — optional shims, outside the engine

The engine (`engine/`) is stdlib-only and makes zero network calls; that promise is about
`engine/`. These are optional ways to reach a brain from other tools. They only run the engine's
own scripts and open no port.

| Folder | What | Status |
|---|---|---|
| `mcp/` | An MCP server over stdio: `sbl_ask` (graph retrieval), `sbl_query` (exact SQL answers), `sbl_inbox`, `sbl_routines`, `sbl_sources`, `sbl_build` | developer preview |

Register the MCP server in any MCP client:

```json
{ "mcpServers": { "second-brain-link": { "command": "python3", "args": ["/path/to/second-brain-link/integrations/mcp/server.py"] } } }
```
