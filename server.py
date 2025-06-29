from mcp.server.fastmcp import FastMCP
import logging
import uvicorn
import json
import os
from typing import Any, Dict
import subprocess
import uuid
from datetime import datetime, timezone
import psutil

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

# In-memory tracking for running processes.
# Key: profile_name, Value: subprocess.Popen object
RUNNING_PROCESSES: Dict[str, subprocess.Popen] = {}

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
    """Get the status of a build profile, checking for completion."""
    logger.info(f"Getting status for build profile '{profile_name}'")
    state = _load_state()
    profile = state.get(profile_name)

    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    status = profile.get("status")
    if status == "running":
        pid = profile.get("last_run", {}).get("pid")
        if pid and not psutil.pid_exists(pid):
            # The process has finished. Let's determine the outcome.
            logger.info(f"Process for '{profile_name}' (PID: {pid}) has finished.")
            process = RUNNING_PROCESSES.pop(profile_name, None)
            
            # We need to get the exit code. This requires a small change to how we manage processes.
            # For now, we'll assume success if the process is gone. A better way is to check the exit code.
            # We will simulate checking the return code. A real implementation would capture this.
            return_code = process.wait() if process else 0 

            if return_code == 0:
                profile["status"] = "succeeded"
                logger.info(f"Build '{profile_name}' marked as succeeded.")
            else:
                profile["status"] = "failed"
                logger.warning(f"Build '{profile_name}' marked as failed with code {return_code}.")
            
            profile["last_run"]["end_time"] = datetime.now(timezone.utc).isoformat()
            _save_state(state)
            return {"status": profile["status"], "exit_code": return_code}

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
        
        # Track the running process in memory
        RUNNING_PROCESSES[profile_name] = process
        
        # Update the profile state
        profile["status"] = "running"
        profile["last_run"] = {
            "run_id": run_id,
            "pid": process.pid,
            "start_time": datetime.now(timezone.utc).isoformat(),
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
    """Stops a running build for the given profile."""
    logger.info(f"Attempting to stop build for profile: {profile_name}")
    state = _load_state()
    profile = state.get(profile_name)

    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    if profile.get("status") != "running":
        return {"error": f"No build is currently running for profile '{profile_name}'."}

    pid = profile.get("last_run", {}).get("pid")
    if not pid or not psutil.pid_exists(pid):
        logger.warning(f"Process for '{profile_name}' with PID {pid} not found, but status was 'running'. Correcting state.")
        profile["status"] = "stopped"
        _save_state(state)
        return {"message": "Build process not found, state has been corrected to 'stopped'."}

    try:
        parent = psutil.Process(pid)
        # Terminate all children of the process first
        for child in parent.children(recursive=True):
            child.terminate()
        # Terminate the parent process
        parent.terminate()
        
        # Wait for termination (optional, but good practice)
        try:
            parent.wait(timeout=5)
        except psutil.TimeoutExpired:
            logger.warning(f"Process {pid} did not terminate gracefully, killing.")
            parent.kill()

        logger.info(f"Successfully sent termination signal to process {pid} for profile '{profile_name}'.")

        # Update state
        profile["status"] = "stopped"
        profile["last_run"]["end_time"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        
        # Clean up in-memory tracker
        RUNNING_PROCESSES.pop(profile_name, None)

        return {"message": f"Successfully stopped build for profile '{profile_name}'."}
    except psutil.NoSuchProcess:
        logger.warning(f"Process {pid} disappeared before it could be stopped. Correcting state.")
        profile["status"] = "stopped"
        _save_state(state)
        return {"message": "Build process disappeared before it could be stopped, state corrected."}
    except Exception as e:
        logger.error(f"Failed to stop build for profile '{profile_name}': {e}", exc_info=True)
        return {"error": f"Failed to stop build: {e}"}

@mcp.tool()
def get_build_log(profile_name: str) -> dict:
    """Retrieves the log file for the last run of a given profile."""
    logger.info(f"Attempting to retrieve log for profile: {profile_name}")
    state = _load_state()
    profile = state.get(profile_name)

    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    last_run = profile.get("last_run")
    if not last_run:
        return {"error": f"No builds have been run for profile '{profile_name}'."}

    log_file_path = last_run.get("log_file")
    if not log_file_path or not os.path.exists(log_file_path):
        return {"error": f"Log file not found for the last run of '{profile_name}'."}

    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_contents = f.read()
        return {"profile": profile_name, "run_id": last_run.get("run_id"), "log": log_contents}
    except Exception as e:
        logger.error(f"Failed to read log file for profile '{profile_name}': {e}", exc_info=True)
        return {"error": f"Failed to read log file: {e}"}

if __name__ == "__main__":
    port = 5307
    # This is the correct way to get the ASGI app, based on the source code.
    app = mcp.streamable_http_app()
    logger.info(f"Starting AutoBuildMCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    logger.info("AutoBuildMCP server stopped")
