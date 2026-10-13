"""The 10 logical MCP servers (5 User / 3 Admin / 2 System).

Each module builds its own FastMCP instance with the shared factory
(``src/mcp/server_base.py``) and exposes its tools over streamable HTTP on
its own port. See ``src/services/mcp_rbac.py`` for the canonical catalog.
"""
