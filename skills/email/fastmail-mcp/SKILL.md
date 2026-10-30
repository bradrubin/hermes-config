---
name: fastmail-mcp
description: "Manage Fastmail MCP OAuth scopes and reauthorize."
version: 1.0.0
author: Hermes Agent
---

# Fastmail MCP

Use when setting up, re-authorizing, or troubleshooting Fastmail MCP access — specifically OAuth scope management and token lifecycle.

## Prerequisites

- Fastmail account with JMAP/MCP enabled
- MCP server configured in `~/.hermes/config.yaml`:
```yaml
mcp_servers:
  fastmail:
    url: "https://api.fastmail.com/mcp"
    auth: oauth
```

## OAuth Scopes

Fastmail MCP supports three access levels, presented as checkboxes on the consent screen:

1. **Read-only** — search and read mail
2. **Write** — create drafts, move, delete, organize
3. **Send** — send emails on behalf of the user

### Scope selection rules

- **Draft creation only (no send):** Check "Read-only" and "Write", UNCHECK "Send".
- **Full access:** Check all three.
- The user controls which scopes to select — always confirm scope selection before authorizing.

## Re-authorizing with New Scopes

The OAuth flow for remote sessions (when the gateway runs locally but the user authenticates in a browser):

1. Call `manage_connections` with `action=authorize` and `connectors=[{"mcp": true, "name": "fastmail"}]`.
2. The response returns a callback URL: `http://127.0.0.1:<PORT>/callback`.
3. The user opens Fastmail's consent screen and selects the desired scopes (checkboxes).
4. After consent, the user pastes the redirect URL back to the agent (it will be a `http://127.0.0.1:<PORT>/callback?code=...&state=...` URL).
5. The gateway at that port receives the callback and exchanges the code for tokens.
6. Tokens are stored in `/Users/hermes/.hermes/mcp-tokens/fastmail.json`.
7. If `manage_connections` settles with `state: connected` but `tools: []`, call `tool_describe` on `mcp__fastmail_*` tools to verify discovery.

### Pitfall: Past callbacks don't work after the port changes

Each `authorize` call uses a new ephemeral port. A callback URL from a previous authorize call will NOT work — it will be delivered to a port the gateway is no longer listening on. Always use the most recent callback URL.

### Pitfall: manage_connections settles before the callback is processed

If the callback URL is pasted but `manage_connections` already returned `settled: true`, the next `authorize` call may pick up a partially-processed state. Clear stale tokens first:
```bash
rm -f /Users/hermes/.hermes/mcp-tokens/fastmail.json /Users/hermes/.hermes/mcp-tokens/fastmail.meta.json
```
Then trigger a fresh `authorize`.

## Inspecting Current Token Scopes

The client registration lives at `/Users/hermes/.hermes/mcp-tokens/fastmail.client.json`. Read it with:
```bash
cat /Users/hermes/.hermes/mcp-tokens/fastmail.client.json
```

Look at the `scope` field. The old scopes were `https://www.fastmail.com/dev/mcp offline_access` — missing the full `mail` scope needed for draft operations.

## After Re-authorization

After tokens are refreshed, the MCP server needs tool discovery. If tools are not appearing:
1. Check that `fastmail.json` and `fastmail.meta.json` exist in the tokens directory.
2. The MCP server connection may need a gateway restart.

## Important Notes

- **DO NOT use Himalaya** for Fastmail operations — the user has explicitly rejected this.
- Fastmail is accessed via MCP server, not as a native Hermes connector.
- Never type, accept, or log Fastmail credentials or tokens in chat.
- Use `manage_connections` for all OAuth operations — never call the token endpoint directly.
