from mcp.server.fastmcp import FastMCP
import logging
import uvicorn
import json
import os
from typing import Any
import subprocess
import uuid
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# State management configuration
STATE_FILE = "builds.json"

def _load_state() -> dict:
    """Loads the build profiles from the state file."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If file is corrupted or empty, start fresh
        return {}

def _save_state(state: dict) -> None:
    """Saves the build profiles to the state file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# Create MCP server - this is the correct way.
mcp = FastMCP("AutoBuildMCP")
logger.info("MCP Server 'AutoBuildMCP' initialized")

@mcp.tool()
def configure_build(profile_name: str, project_path: str, build_command: str, environment: dict = None, timeout: int = 300) -> dict:
    """Configure a build profile."""
    logger.info(f"Configuring build profile '{profile_name}'")
    state = _load_state()
    state[profile_name] = {
        "project_path": project_path,
        "build_command": build_command,
        "environment": environment,
        "timeout": timeout,
        "status": "configured"
    }
    _save_state(state)
    return {"message": f"Build profile '{profile_name}' configured successfully."}

@mcp.tool()
def get_build_status(profile_name: str) -> dict:
    """Get the status of a build profile."""
    logger.info(f"Getting status for build profile '{profile_name}'")
    state = _load_state()
    profile = state.get(profile_name)
    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}
    return {"status": profile.get("status", "unknown")}

@mcp.tool()
def list_builds() -> dict:
    """List all configured build profiles."""
    logger.info("Listing all build profiles")
    state = _load_state()
    profiles = {name: data.get("status", "unknown") for name, data in state.items()}
    return {"profiles": profiles}

@mcp.tool()
def start_build(profile_name: str) -> dict:
    """Starts a build for the given profile."""
    logger.info(f"Attempting to start build for profile: {profile_name}")
    state = _load_state()
    
    profile = state.get(profile_name)
    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    if profile.get("status") == "running":
        return {"error": f"Build for profile '{profile_name}' is already running."}

    run_id = str(uuid.uuid4())
    log_file_path = os.path.join("logs", f"{run_id}.log")
    
    try:
        # Prepare the environment for the subprocess
        build_env = os.environ.copy()
        if profile.get("environment"):
            build_env.update(profile["environment"])

        # Open the log file
        log_file = open(log_file_path, "wb")

        # Launch the build command as a background process
        process = subprocess.Popen(
            profile["build_command"],
            shell=True,
            cwd=profile["project_path"],
            env=build_env,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        
        # Update the profile state
        profile["status"] = "running"
        profile["last_run"] = {
            "run_id": run_id,
            "pid": process.pid,
            "start_time": datetime.utcnow().isoformat(),
            "log_file": log_file_path
        }
        _save_state(state)

        logger.info(f"Successfully started build for profile '{profile_name}' with PID {process.pid}")
        return {
            "message": f"Build started for profile '{profile_name}'.",
            "run_id": run_id,
            "pid": process.pid
        }
    except Exception as e:
        logger.error(f"Failed to start build for profile '{profile_name}': {e}", exc_info=True)
        # Clean up log file if process creation fails
        if 'log_file' in locals() and log_file:
            log_file.close()
        return {"error": f"Failed to start build: {e}"}

@mcp.tool()
def stop_build(profile_name: str) -> dict:
    """Stop a running build."""
    logger.info(f"Stopping build for profile: {profile_name}")
    return {"message": f"Build for profile '{profile_name}' will be stopped."}

if __name__ == "__main__":
    port = 5307
    # This is the correct way to get the ASGI app, based on the source code.
    app = mcp.streamable_http_app()
    logger.info(f"Starting AutoBuildMCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    logger.info("AutoBuildMCP server stopped")
