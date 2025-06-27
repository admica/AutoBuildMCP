# AutoBuildMCP (MCP-Compliant)

The AutoBuildMCP server is a Model Context Protocol (MCP) server designed to automate and monitor code builds. It exposes a set of tools that an MCP-compliant agent can use to watch a directory for code changes, trigger builds, and monitor the status.

It uses a JSON-RPC 2.0 interface, as required by the MCP standard.

## Setup

1.  **Build the Environment:**
    Run the `build.sh` script. This will create a Python virtual environment, upgrade pip, and install all necessary dependencies.
    ```bash
    ./build.sh
    ```

2.  **Start the Server:**
    Use the `run.sh` script, which activates the virtual environment and starts the server on `http://localhost:5501`.
    ```bash
    ./run.sh
    ```

## Interacting with the MCP Server

All interactions happen via JSON-RPC 2.0 messages sent to the `/api/v1/jsonrpc` endpoint. You can use `curl` to interact with it manually.

### Discovering Tools (`mcp.getSpec`)

To see what tools the server provides, call the `mcp.getSpec` method.

```bash
curl -X POST -H "Content-Type: application/json" \
-d '{"jsonrpc": "2.0", "method": "mcp.getSpec", "id": 1}' \
http://localhost:5501/api/v1/jsonrpc
```

### Configuring the Build (`mcp.setConfig`)

To start watching a directory, call the `mcp.setConfig` method with the required parameters.

```bash
curl -X POST -H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "method": "mcp.setConfig",
  "params": {
    "work_dir": "/home/user/mcp/AutoBuildMCP", 
    "build_command": "./build.sh", 
    "build_delay": 2.0
  },
  "id": 2
}' \
http://localhost:5501/api/v1/jsonrpc
```
*Note: Replace `"/home/user/mcp/AutoBuildMCP"` with the absolute path to the project you want to monitor.*

### Checking Status (`mcp.getStatus`)

To check the current build status, call the `mcp.getStatus` method.

```bash
curl -X POST -H "Content-Type: application/json" \
-d '{"jsonrpc": "2.0", "method": "mcp.getStatus", "id": 3}' \
http://localhost:5501/api/v1/jsonrpc
```