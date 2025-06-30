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
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import pathspec
from pathlib import Path

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

# --- Autobuild Watcher and Debounce Logic ---
class DebounceHandler(FileSystemEventHandler):
    """A watchdog event handler that debounces events to trigger a build, respecting ignore patterns."""
    def __init__(self, profile_name: str, project_path: str, ignore_patterns: list[str], debounce_seconds: int = 5):
        self.profile_name = profile_name
        self.debounce_seconds = debounce_seconds
        self._loop = asyncio.get_running_loop()
        self._timer = None
        # Use pathlib for robust path operations
        self._project_path = Path(project_path).resolve()
        # Compile the ignore patterns for efficient matching.
        self._spec = pathspec.PathSpec.from_lines('gitwildmatch', ignore_patterns)
        logger.info(f"Debounce handler initialized for '{self.profile_name}' with patterns: {ignore_patterns}.")

    def on_any_event(self, event):
        """Called by watchdog on any file system event."""
        if event.is_directory:
            return

        try:
            event_path = Path(event.src_path).resolve()
            # This is the key: check if the event path is truly inside the project path.
            if not event_path.is_relative_to(self._project_path):
                return
            
            # Get the relative path for matching.
            relative_path = event_path.relative_to(self._project_path)
            
            # Convert to a cross-platform (forward-slash) string for pathspec
            match_path = str(relative_path.as_posix())

            if self._spec.match_file(match_path):
                return # Path is ignored, do nothing.
        except Exception:
            # Broad exception to catch any potential path errors and prevent crashing the watcher.
            return
        
        self._loop.call_soon_threadsafe(self._reset_timer)

    def _reset_timer(self):
        """Resets the build trigger timer. Runs in the main asyncio thread."""
        if self._timer:
            self._timer.cancel()
        
        self._timer = self._loop.call_later(
            self.debounce_seconds,
            lambda: asyncio.create_task(self._trigger_build())
        )

    async def _trigger_build(self):
        """The callback that fires after the debounce delay."""
        logger.info(f"Debounced trigger for '{self.profile_name}'. Checking status...")
        state = _load_state()
        profile = state.get(self.profile_name)

        if not profile or not profile.get("autobuild_enabled"):
            logger.warning(f"Autobuild trigger for '{self.profile_name}' fired, but autobuild is now disabled. Ignoring.")
            return

        status = profile.get("status")
        if status in ["running", "queued"]:
            logger.info(f"Build for '{self.profile_name}' is busy. Setting 'rebuild_on_completion' flag.")
            profile["rebuild_on_completion"] = True
            _save_state(state)
        else:
            logger.info(f"Build for '{self.profile_name}' is idle. Adding to build queue.")
            # This logic is duplicated from the start_build tool, but is necessary here.
            profile["status"] = "queued"
            profile["rebuild_on_completion"] = False # Reset flag
            _save_state(state)
            BUILD_QUEUE.append(self.profile_name)


# --- Background Worker Tasks ---
ACTIVE_WATCHERS: Dict[str, Observer] = {}
async def watcher_manager():
    """Manages the file system watchers, keeping them in sync with profile configs."""
    logger.info("Watcher manager started.")
    while True:
        state = _load_state()
        profiles_to_watch = {name for name, profile in state.items() if profile.get("autobuild_enabled")}
        watched_profiles = set(ACTIVE_WATCHERS.keys())
        
        # Start new watchers
        for profile_name in profiles_to_watch - watched_profiles:
            profile = state[profile_name]
            path = profile.get("project_path")
            if not path or not os.path.isdir(path):
                logger.error(f"Cannot start watcher for '{profile_name}': project_path '{path}' is invalid.")
                continue
            
            logger.info(f"Starting watcher for profile '{profile_name}' at path '{path}'.")
            ignore_patterns = profile.get("autobuild_ignore_patterns", [])
            event_handler = DebounceHandler(profile_name, path, ignore_patterns)
            observer = Observer()
            observer.schedule(event_handler, path, recursive=True)
            observer.start()
            ACTIVE_WATCHERS[profile_name] = observer

        # Stop old watchers
        for profile_name in watched_profiles - profiles_to_watch:
            logger.info(f"Stopping watcher for profile '{profile_name}'.")
            observer = ACTIVE_WATCHERS.pop(profile_name)
            observer.stop()
            observer.join() # Wait for the thread to finish

        await asyncio.sleep(10) # Re-check configurations every 10 seconds

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
            
            # Reset rebuild flag at the start of a run
            profile["rebuild_on_completion"] = False

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
                
                # The worker's job is now just to start the process and update the state.
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
                logger.error(f"Worker failed to execute build for '{profile_name}': {e}", exc_info=True)
                fail_state = _load_state()
                fail_profile = fail_state.get(profile_name, {})
                fail_profile["status"] = "failed"
                fail_profile["last_run"] = {"outcome_note": f"Worker failed to start build: {e}"}
                _save_state(fail_state)
                RUNNING_PROCESSES.pop(profile_name, None)
        
        await asyncio.sleep(1) # Check queue more frequently

async def status_monitor():
    """The background worker that monitors running processes and handles completion."""
    logger.info("Status monitor started.")
    while True:
        # Iterate over a copy of the items, as the dictionary may be modified during the loop.
        for profile_name, process in list(RUNNING_PROCESSES.items()):
            return_code = process.poll()
            
            # If poll() returns None, the process is still running.
            if return_code is None:
                continue

            logger.info(f"Status monitor detected build '{profile_name}' finished with exit code {return_code}.")
            
            # Process finished, remove it from active tracking.
            RUNNING_PROCESSES.pop(profile_name, None)
            
            # Reload the state to get the most recent version before modifying it.
            current_state = _load_state()
            current_profile = current_state.get(profile_name)

            if not current_profile:
                logger.error(f"Profile '{profile_name}' was not found in state when its process finished. Cannot update status.")
                continue

            if return_code == 0:
                current_profile["status"] = "succeeded"
            else:
                current_profile["status"] = "failed"
            
            if "last_run" in current_profile:
                 current_profile["last_run"]["end_time"] = datetime.now(timezone.utc).isoformat()

            # Check if a rebuild was requested while it was running
            if current_profile.get("rebuild_on_completion"):
                logger.info(f"Rebuild requested for '{profile_name}'. Adding back to queue.")
                current_profile["status"] = "queued"
                current_profile["rebuild_on_completion"] = False
                BUILD_QUEUE.append(profile_name)
            
            _save_state(current_state)
            logger.info(f"Status for '{profile_name}' updated to '{current_profile['status']}'.")

        await asyncio.sleep(2) # Check every 2 seconds


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Manages the startup and shutdown of the background worker task."""
    # Start all background tasks
    build_worker_task = asyncio.create_task(build_worker())
    watcher_manager_task = asyncio.create_task(watcher_manager())
    status_monitor_task = asyncio.create_task(status_monitor())
    yield
    # Stop all background tasks
    logger.info("Server shutting down, stopping background tasks...")
    status_monitor_task.cancel()
    watcher_manager_task.cancel()
    build_worker_task.cancel()
    try:
        await status_monitor_task
    except asyncio.CancelledError:
        logger.info("Status monitor successfully cancelled.")
    try:
        await watcher_manager_task
    except asyncio.CancelledError:
        logger.info("Watcher manager successfully cancelled.")
    try:
        await build_worker_task
    except asyncio.CancelledError:
        logger.info("Build worker successfully cancelled.")
    
    # Gracefully stop any running watchdog observers
    for observer in ACTIVE_WATCHERS.values():
        observer.stop()
        observer.join()


# Create MCP server, now with the lifespan manager for our worker
mcp = FastMCP("AutoBuildMCP", lifespan=lifespan)
logger.info("MCP Server 'AutoBuildMCP' initialized")

@mcp.tool()
def get_server_info() -> dict:
    """Returns a comprehensive overview of the server's capabilities, best practices, and API."""
    return {
        "server_name": "AutoBuildMCP",
        "version": "1.0.0",
        "description": "A profile-based build automation server that can start, stop, monitor, and automatically trigger builds based on file system changes.",
        "best_practices": {
            "workflow_overview": "1. Use `configure_build` to create a profile for your project. 2. Use `toggle_autobuild` to enable file watching. 3. Let the server handle the rest, or use `start_build` for manual runs.",
            "understanding_build_lifecycle": "Builds are asynchronous. A triggered build first goes into a 'queued' state. A background worker will then pick it up, changing the status to 'running'. Once complete, the status will become 'succeeded' or 'failed'. Always anticipate this slight delay.",
            "preventing_recursion_user_responsibility": "CRITICAL: Your build process likely creates files (logs, build artifacts). To prevent infinite build loops, you MUST use the `autobuild_ignore_patterns` parameter in `configure_build` to exclude these paths. Good examples: `['build/', 'dist/', '*.pyc', 'node_modules/']`.",
            "preventing_recursion_server_protection": f"NOTE: The server automatically ignores its own state file ('{STATE_FILE}') and common patterns like '.git/' and 'logs/' for you. You do not need to add these to your ignore patterns.",
            "checking_status": "Because builds are asynchronous, polling `get_build_status` is the best way to get real-time status of a build you have just triggered."
        },
        "api_reference": {
            "get_server_info": "Returns this help object.",
            "configure_build": {
                "description": "Creates or updates a build profile. This is the primary tool for managing builds.",
                "example": {
                    "tool_call": "configure_build",
                    "profile_name": "my-web-app",
                    "project_path": "./frontend",
                    "build_command": "npm run build",
                    "autobuild_ignore_patterns": ["dist/", "node_modules/"]
                }
            },
            "toggle_autobuild": "Enables (`enabled: true`) or disables (`enabled: false`) the autobuild watcher for a profile.",
            "start_build": "Manually adds a build to the queue. Returns the queue position.",
            "list_builds": "Lists all profiles and their current status. This is a snapshot-in-time.",
            "get_build_status": "Gets the status of a single profile. Expect the status to be 'queued' or 'running' before it becomes 'succeeded' or 'failed'.",
            "stop_build": "Stops a currently running build.",
            "delete_build_profile": "Deletes a profile.",
            "get_build_log": "Retrieves the full log or tails the last N lines using the `lines` parameter. Useful for debugging failed builds."
        }
    }

@mcp.tool()
def configure_build(profile_name: str, project_path: str, build_command: str, environment: dict = None, timeout: int = 300, autobuild_ignore_patterns: list[str] = None) -> dict:
    """Configure a build profile."""
    logger.info(f"Configuring build profile '{profile_name}'")
    state = _load_state()

    # Set default ignore patterns if none are provided.
    if autobuild_ignore_patterns is None:
        autobuild_ignore_patterns = []

    # Add default and essential patterns, ensuring no duplicates.
    # The state file MUST be ignored to prevent recursion.
    default_patterns = {".git/", "logs/", STATE_FILE}
    final_ignore_patterns = list(set(autobuild_ignore_patterns) | default_patterns)

    state[profile_name] = {
        "project_path": project_path,
        "build_command": build_command,
        "environment": environment,
        "timeout": timeout,
        "status": "configured",
        "autobuild_enabled": False,
        "rebuild_on_completion": False,
        "autobuild_ignore_patterns": final_ignore_patterns
    }
    _save_state(state)
    return {"message": f"Build profile '{profile_name}' configured successfully."}

@mcp.tool()
def toggle_autobuild(profile_name: str, enabled: bool) -> dict:
    """Enables or disables the autobuild feature for a profile."""
    logger.info(f"Setting autobuild for profile '{profile_name}' to {enabled}.")
    state = _load_state()
    profile = state.get(profile_name)

    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    profile["autobuild_enabled"] = enabled
    _save_state(state)

    return {"message": f"Autobuild for profile '{profile_name}' has been {'enabled' if enabled else 'disabled'}."}

@mcp.tool()
def get_build_status(profile_name: str) -> dict:
    """Get the status of a build profile, checking for completion."""
    logger.info(f"Getting status for build profile '{profile_name}'")
    state = _load_state()
    profile = state.get(profile_name)

    if not profile:
        return {"error": f"Profile '{profile_name}' not found."}

    # For a running process, we can still provide instant feedback
    if profile.get("status") == "running":
        pid = profile.get("last_run", {}).get("pid")
        if pid and not psutil.pid_exists(pid):
             return {"status": "unknown", "note": "Process finished but worker has not updated state yet."}
    
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
    profile["rebuild_on_completion"] = False # Ensure flag is reset on manual start
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
