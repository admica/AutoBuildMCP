# AutoBuildMCP

The AutoBuildMCP server is a focused FastAPI-based MCP server designed to automate and monitor code builds for any project. It watches for code changes, triggers builds, ensures only one build runs at a time, and logs outputs. Future build time estimates are based on past builds using recent build weighting.

## Setup

1.  **Build the environment:**

    Run the `build.sh` script to create a Python virtual environment and install the required dependencies.
    ```bash
    ./build.sh
    ```

2.  **Start the server:**

    Activate the virtual environment and run the `server.py` script.
    ```bash
    source venv/bin/activate
    python server.py
    ```
    The server will start on port 5501.

3.  **Configure the project:**

    Query the `/setup` endpoint to check the initial (unconfigured) status. Then, POST to `/set_directory_and_command` to set the working directory and the build command to execute.

    Tell your LLM to do this, or you can manually do it:

    Example using `curl`:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
    -d '{"work_dir": "/path/to/your/project", "build_command": "./build.sh", "build_delay": 2.0}' \
    http://localhost:5501/set_directory_and_command
    ```

Once configured, the server will monitor the `work_dir` for file changes and automatically run the specified `build_command`.
