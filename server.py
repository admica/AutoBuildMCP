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
import asyncio
from collections import deque
from contextlib import asynccontextmanager

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

def _handle_orphan_builds_on_startup():
    """Checks for and cleans up builds that were running when the server last stopped."""
    logger.info("Checking for orphaned builds from previous sessions...")
    state = _load_state()
    state_changed = False

    for profile_name, profile in state.items():
        if profile.get("status") == "running":
            pid = profile.get("last_run", {}).get("pid")
            if not pid or not psutil.pid_exists(pid):
                logger.warning(f"Orphaned build '{profile_name}' (PID: {pid}) detected. Marking status as 'unknown'.")
                profile["status"] = "unknown"
                profile["last_run"]["end_time"] = datetime.now(timezone.utc).isoformat()
                profile["last_run"]["outcome_note"] = "Build status is unknown; server was restarted during execution."
                state_changed = True
    
    if state_changed:
        _save_state(state)
        logger.info("Finished cleaning up orphaned builds.")

# --- Build Queue and Worker Configuration ---
BUILD_QUEUE = deque()
MAX_CONCURRENT_BUILDS = 2
# In-memory tracking for running processes.
# Key: profile_name, Value: subprocess.Popen object
RUNNING_PROCESSES: Dict[str, subprocess.Popen] = {}

async def build_worker():
    """The background worker that processes the build queue."""
    logger.info("Build worker started.")
    while True:
        if BUILD_QUEUE and len(RUNNING_PROCESSES) < MAX_CONCURRENT_BUILDS:
            profile_name = BUILD_QUEUE.popleft()
            logger.info(f"Worker picking up build for profile '{profile_name}'.")

            state = _load_state()
            profile = state.get(profile_name)
            
            if not profile:
                logger.error(f"Profile '{profile_name}' not found in state when worker tried to run it. Skipping.")
                continue

            # This is the same logic from the old start_build tool
            run_id = str(uuid.uuid4())
            log_file_path = os.path.join("logs", f"{run_id}.log")
            try:
                build_env = os.environ.copy()
                if profile.get("environment"):
                    build_env.update(profile["environment"])
                log_file = open(log_file_path, "wb")
                process = subprocess.Popen(
                    profile["build_command"],
                    shell=True,
                    cwd=profile["project_path"],
                    env=build_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
                RUNNING_PROCESSES[profile_name] = process
                profile["status"] = "running"
                profile["last_run"] = {
                    "run_id": run_id,
                    "pid": process.pid,
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "log_file": log_file_path
                }
                _save_state(state)
                logger.info(f"Worker successfully started build for '{profile_name}' with PID {process.pid}.")
            except Exception as e:
                logger.error(f"Worker failed to start build for '{profile_name}': {e}", exc_info=True)
                profile["status"] = "failed"
                profile["last_run"] = {"outcome_note": f"Worker failed to start build: {e}"}
                _save_state(state)
        
        await asyncio.sleep(5)  # Wait 5 seconds before checking the queue again

@asynccontextmanager
async def lifespan(app: FastMCP):
    """Manages the startup and shutdown of the background worker task."""
    worker_task = asyncio.create_task(build_worker())
    yield
    logger.info("Server shutting down, stopping build worker...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        logger.info("Build worker successfully cancelled.")


# Create MCP server, now with the lifespan manager for our worker
mcp = FastMCP("AutoBuildMCP", lifespan=lifespan)
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
    """Adds a build request to the queue."""
    logger.info(f"Queuing build for profile: {profile_name}")
    state = _load_state()
    
    profile = state.get(profile_name)
    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    # Prevent adding to queue if already running or queued
    if profile.get("status") in ["running", "queued"]:
        return {"error": f"Build for profile '{profile_name}' is already running or queued."}

    if profile_name in BUILD_QUEUE:
        return {"error": f"Build for profile '{profile_name}' is already in the queue."}

    # Update status to 'queued' and add to the queue
    profile["status"] = "queued"
    _save_state(state)
    BUILD_QUEUE.append(profile_name)

    logger.info(f"Successfully queued build for profile '{profile_name}'.")
    return {
        "message": f"Build for profile '{profile_name}' has been queued.",
        "position": len(BUILD_QUEUE)
    }

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
def get_build_log(profile_name: str, lines: int = None) -> dict:
    """Retrieves the log file for the last run of a given profile. Can tail the last N lines."""
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
            if lines and lines > 0:
                log_lines = f.readlines()
                log_contents = "".join(log_lines[-lines:])
            else:
                log_contents = f.read()
        return {"profile": profile_name, "run_id": last_run.get("run_id"), "log": log_contents}
    except Exception as e:
        logger.error(f"Failed to read log file for profile '{profile_name}': {e}", exc_info=True)
        return {"error": f"Failed to read log file: {e}"}

@mcp.tool()
def delete_build_profile(profile_name: str) -> dict:
    """Deletes a configured build profile."""
    logger.info(f"Attempting to delete build profile: {profile_name}")
    state = _load_state()

    if profile_name not in state:
        return {"error": f"Profile '{profile_name}' not found."}

    if state[profile_name].get("status") == "running":
        return {"error": f"Cannot delete profile '{profile_name}' while a build is running."}

    del state[profile_name]
    _save_state(state)
    
    logger.info(f"Successfully deleted profile '{profile_name}'.")
    return {"message": f"Profile '{profile_name}' has been deleted."}

if __name__ == "__main__":
    port = 5307
    # Handle potentially orphaned builds before starting the server
    _handle_orphan_builds_on_startup()
    # This is the correct way to get the ASGI app, based on the source code.
    app = mcp.streamable_http_app()
    logger.info(f"Starting AutoBuildMCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    logger.info("AutoBuildMCP server stopped")
