from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import asyncio
import time

app = FastAPI(title="AutoBuildMCP")

# --- In-memory state (to be replaced with real logic) ---
config = {
    "work_dir": None,
    "build_command": None,
    "build_delay": 2.0,
    "ignore_patterns": [],
    "use_gitignore": False,
    "env": {},
}
build_status = {
    "status": "idle",
    "last_build_time": None,
    "last_build_result": None,
    "current_log_tail": "",
    "history": [],
}

# --- JSON-RPC 2.0 Handler ---

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    data = await request.json()
    method = data.get("method")
    params = data.get("params", {})
    rpc_id = data.get("id")
    
    if method == "get_help_info":
        result = get_help_info()
        return {"jsonrpc": "2.0", "result": result, "id": rpc_id}
    elif method == "configure_build":
        result = configure_build(params)
        return {"jsonrpc": "2.0", "result": result, "id": rpc_id}
    elif method == "get_build_status":
        result = get_build_status()
        return {"jsonrpc": "2.0", "result": result, "id": rpc_id}
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method '{method}' not found."},
            "id": rpc_id,
        }

# --- Streaming Endpoint (SSE) ---

@app.get("/mcp/sse")
async def mcp_sse():
    async def event_generator():
        # TODO: Replace with real log/status streaming
        for i in range(5):
            yield f"data: status=idle, tick={i}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- JSON-RPC Method Implementations ---

def get_help_info() -> Dict[str, Any]:
    return {
        "description": "AutoBuildMCP: A generic MCP server for build automation. Configure at runtime via API.",
        "tools": [
            {
                "name": "get_help_info",
                "description": "Returns this help message and usage info.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "configure_build",
                "description": "Configure the build environment and file watching.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "work_dir": {"type": "string", "description": "Absolute path to codebase"},
                        "build_command": {"type": "string", "description": "Build command to run"},
                        "build_delay": {"type": "number", "description": "Seconds to wait after change before building"},
                        "ignore_patterns": {"type": "array", "items": {"type": "string"}, "description": "Glob patterns to ignore"},
                        "use_gitignore": {"type": "boolean", "description": "Whether to ignore files in .gitignore"},
                        "env": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Environment variables for build"}
                    },
                    "required": ["work_dir", "build_command"]
                }
            },
            {
                "name": "get_build_status",
                "description": "Get the current build status and log tail.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ],
        "usage_steps": [
            "1. Call get_help_info to see available tools.",
            "2. Call configure_build with your project settings.",
            "3. The server will watch for changes and run builds.",
            "4. Poll get_build_status or connect to /mcp/sse for updates."
        ]
    }

def configure_build(params: Dict[str, Any]) -> Dict[str, Any]:
    # Update in-memory config (no validation for now)
    config.update({
        "work_dir": params.get("work_dir"),
        "build_command": params.get("build_command"),
        "build_delay": params.get("build_delay", 2.0),
        "ignore_patterns": params.get("ignore_patterns", []),
        "use_gitignore": params.get("use_gitignore", False),
        "env": params.get("env", {}),
    })
    # TODO: Start/Restart file watching and build logic
    return {"result": "Configuration set. (Build watching not yet implemented)", "config": config}

def get_build_status() -> Dict[str, Any]:
    # Return current in-memory build status
    return build_status

# TODO: Add file watching, build execution, log streaming, etc.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=5501, ssl_keyfile="ssl/key.pem", ssl_certfile="ssl/cert.pem") 