# Safety — what this plugin will not do, and how that is enforced

| Rule | Enforced by |
|---|---|
| Never sends an email or message | Studio admits Gmail tools to agents **by exact name**, and only draft-creation tools are admitted (`AGENT_TOOL_CEILING`); the skills forbid send tools; a record becomes `contacted` only via `ledger.py sent`, which only the founder's confirmation triggers (`FOUNDER_ONLY` in `ledger.py`) |
| Never states an unsupported fact | `lint_claims.py` on every answer set and every draft; red stops at every autonomy level |
| Never treats a list as a source | imports create 📋 records; list text is `origin_text`, never a claim |
| Never types secrets, pays, or creates accounts | `raise-apply/references/field-policy.md`; `detect_form.py` flags login, fee and video signals before drafting |
| Never re-applies with the same profile silently | `rejected → queued` and `passed → queued` require `--different` |
| Never writes into engine layers | the skills write only `46-fundraising/`; the renderer keeps its own manifest |
| Never automates LinkedIn or X | drafts for those channels are notes only |

## The Gmail connector

The draft path uses the Gmail connector available to Claude Code. Admit only a tool whose purpose
is creating a draft; if the connector offers only send-capable tools, leave it out of the ceiling —
the plugin then writes notes with a `mailto:` link, and says so.
