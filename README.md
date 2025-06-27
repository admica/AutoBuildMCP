# AutoBuildMCP
The AutoBuildMCP server is a focused FastAPI-based MCP server designed to automate and monitor code builds for any project. It watches for code changes, triggers builds, ensures only one build runs at a time, and logs outputs. Future build time estimates are based on past builds using recent build weighting.

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Run `server.py` to start the server on port 5501.
3. Query the `/setup` endpoint to check configuration status.
4. POST to `/set_directory_and_command` to set the working directory and build command. Example:
   ```bash
   curl -X POST -H "Content-Type: application/json" -d '{"work_dir": "/path/to/project", "build_command": "pio run", "build_delay": 2.0}' http://localhost:5000/set_directory_and_command
   ```
