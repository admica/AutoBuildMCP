# AutoBuildMCP (MCP-Compliant)

The AutoBuildMCP server is a Model Context Protocol (MCP) server designed to automate and monitor code builds. It exposes a set of tools that an MCP-compliant agent can use to watch a directory for code changes, trigger builds, and monitor the status.

It uses a JSON-RPC 2.0 interface.

## Setup

1.  **Build the Environment:**
    Run the `build.sh` script. This will create a Python virtual environment, upgrade pip, and install all necessary dependencies.
    ```bash
    ./build.sh
    ```

2.  **Start the Server:**
    Use the `run.sh` script, which activates the virtual environment and starts the server on `http://localhost:5305`.
    ```bash
    ./run.sh
    ```

3.  **Run the self-tests (Optional)**
    Use the `test.sh` script to perform self test of all endpoints. This will call build.sh on itself.
    ```bash
    ./test.sh
    ```

## Interacting with the MCP Server

All interactions happen via JSON-RPC 2.0 messages sent to the `/mcp` endpoint. You can use `curl` to interact with it manually.

### Getting Help (`get_help_info`)

To retrieve information about the available methods and their usage, call the `get_help_info` method.

```bash
curl -X POST -H "Content-Type: application/json" \
-d '{"jsonrpc": "2.0", "method": "get_help_info", "params": {}, "id": 3}' \
http://localhost:5305/mcp
```

### Configuring the Build (`configure_build`)

To start watching a directory, call the `configure_build` method with the required parameters.

```bash
curl -X POST -H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "method": "configure_build",
  "params": {
    "work_dir": "/home/user/mcp/AutoBuildMCP",
    "build_command": "./build.sh",
    "build_delay": 2.0
  },
  "id": 1
}' \
http://localhost:5305/mcp
```
*Note: Replace `"/home/user/mcp/AutoBuildMCP"` with the absolute path to the project you want to monitor.*

### Checking Status (`get_build_status`)

To check the current build status, call the `get_build_status` method.

```bash
curl -X POST -H "Content-Type: application/json" \
-d '{"jsonrpc": "2.0", "method": "get_build_status", "params": {}, "id": 2}' \
http://localhost:5305/mcp
```

## Testing

To run the test suite, execute the `test.sh` script:

```bash
./test.sh
```
This script activates the virtual environment and runs the `test/curl.py` script, which contains automated tests for the server's endpoints.

## Build History

The server maintains a `build_history.json` file in the working directory to store the duration of successful and failed builds. This data is used to provide estimated build times.

