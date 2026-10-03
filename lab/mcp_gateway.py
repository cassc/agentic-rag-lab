"""An MCP gateway: one place between agents and a fleet of MCP servers.

registry: which servers exist, how to start them, and the approved
          fingerprint (hash) of their tool definitions
roles:    which tools a role may call - checked on every call, not only
          when the tool list is built
audit:    every call and every refusal
"""
import asyncio
import hashlib
import json
import os
import sys
from contextlib import AsyncExitStack
from mcp import Client, StdioServerParameters


def fingerprint(tools):
    """Tool names, descriptions and schemas go into the model's prompt. Hash them."""
    body = json.dumps([[t.name, t.description, t.input_schema] for t in tools], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


class McpGateway:
    def __init__(self, registry, roles, approved=None):
        self.registry, self.roles, self.approved = registry, roles, approved or {}
        self.catalog, self.fingerprints, self.audit = {}, {}, []  # catalog: "server__tool" -> (client, Tool)

    async def __aenter__(self):
        self.stack = AsyncExitStack()
        for name, entry in self.registry.items():
            params = StdioServerParameters(command=sys.executable, args=entry["args"],
                                           env={**os.environ, **entry.get("env", {})})
            client = await self.stack.enter_async_context(Client(params))
            tools = (await client.list_tools()).tools
            self.fingerprints[name] = fingerprint(tools)
            if self.approved.get(name, self.fingerprints[name]) != self.fingerprints[name]:
                self.audit.append(("gateway", name, "BLOCKED: tool definitions changed since approval"))
                continue
            for t in tools:  # prefix with the server name: two servers may both have "search"
                self.catalog[f"{name}__{t.name}"] = (client, t)
        return self

    async def __aexit__(self, *exc):
        await self.stack.aclose()

    def allowed(self, role, full):
        server, tool = full.split("__", 1)
        may = self.roles[role].get(server, [])
        return "*" in may or tool in may

    def specs(self, role=None):
        """Tool schemas in the OpenAI format. role=None: everything in the catalog."""
        return {full: {"type": "function", "function": {
            "name": full, "description": t.description, "parameters": t.input_schema}}
            for full, (_, t) in self.catalog.items() if role is None or self.allowed(role, full)}

    async def call(self, role, full, args):
        if full not in self.catalog or not self.allowed(role, full):
            self.audit.append((role, full, "DENIED"))
            return f"DENIED by policy: role '{role}' may not call {full}"
        client, t = self.catalog[full]
        r = await client.call_tool(t.name, args)
        self.audit.append((role, full, "error" if r.is_error else "ok"))
        return "\n".join(c.text for c in r.content if c.type == "text")

    def tools(self, role, event_loop):
        """{name: (function, schema)} for lab.loop.run, which is sync and runs in a thread."""
        def bridge(full):
            return lambda **args: asyncio.run_coroutine_threadsafe(
                self.call(role, full, args), event_loop).result()
        return {full: (bridge(full), spec) for full, spec in self.specs(role).items()}
