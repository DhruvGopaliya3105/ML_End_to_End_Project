@echo off
REM Start the 10 MCP servers (Windows). Localhost only, service-token protected.
REM The FastAPI app talks to them through the gateway - browsers never do.
cd /d "%~dp0"

if not exist .env (
    echo No .env found - copying .env.example to .env
    copy .env.example .env >nul
    echo Open .env and set DB_PASSWORD (and MCP_SERVICE_TOKEN in production^).
)

call .venv\Scripts\activate
python -m src.mcp.run_all
