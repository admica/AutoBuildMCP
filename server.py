from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import EventSourceResponse
from pydantic import BaseModel
import os
import subprocess
import json
import shlex
import shutil
from datetime import datetime
import time
import asyncio
import tempfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

app = FastAPI()

# Configuration
CONFIG = {
    "work_dir": None,
    "build_command": None,
    "build_delay": 2.0,
    "output_log": "build_output.log",
    "error_log": "build_errors.log"
}
BUILD_STATUS = {
    "status": "idle",
    "last_output": "No builds yet",
    "last_started": None,
    "last_ended": None
}
BUILD_HISTORY_FILE = "build_history.json"
BUILD_HISTORY = {"successful_builds": [], "failed_builds": []}
BUILD_LOCK = threading.Lock()
BUILD_TIMER = None
OBSERVER = None

# MCP tool schema for discovery
TOOLS_SCHEMA = {
    "tools": [
        {
            "name": "configure_build",
            "description": "Configures the build process and starts file watching",
            "input_schema": {
                "type": "object",
                "properties": {
                    "work_dir": {"type": "string", "description": "Absolute path to the directory to monitor"},
                    "build_command": {"type": "string", "description": "Shell command to execute for building"},
                    "build_delay": {"type": "number", "minimum": 0.5, "maximum": 10.0, "description": "Delay in seconds before triggering a build"}
                },
                "required": ["work_dir", "build_command"]
            }
        },
        {
            "name": "get_build_status",
            "description": "Retrieves the current build status and last build output",
            "input_schema": {"type": "object", "properties": {}}
        },
        {
            "name": "get_help_info",
            "description": "Provides information about available methods and their usage",
            "input_schema": {"type": "object", "properties": {}}
        }
    ]
}

HELP_INFO = {
    "description": "This server provides Model Context Protocol (MCP) endpoints for automating and monitoring code builds.",
    "methods": {
        "configure_build": {
            "description": "Configures the build process and starts file watching.",
            "params": {
                "work_dir": "Absolute path to the directory to monitor for changes.",
                "build_command": "The shell command to execute for building (e.g., './build.sh' or 'pio run').",
                "build_delay": "Optional: Delay in seconds before triggering a build after a file change (default: 2.0, min: 0.5, max: 10.0)."
            },
            "returns": "Success message if configuration is applied, or an error."
        },
        "get_build_status": {
            "description": "Retrieves the current build status and last build output.",
            "params": {},
            "returns": {
                "status": "Current build status (idle, building, success, failed).",
                "last_output": "Output from the last build attempt.",
                "last_started": "Timestamp of when the last build started (ISO format).",
                "last_ended": "Timestamp of when the last build ended (ISO format).",
                "message": "Optional: Estimated time until current build finishes (only if building)."
            }
        },
        "get_help_info": {
            "description": "Provides information about the available methods and their usage.",
            "params": {},
            "returns": "JSON object describing all available methods and their usage."
        }
    }
}

# Load build history safely
if os.path.exists(BUILD_HISTORY_FILE):
    try:
        with open(BUILD_HISTORY_file, "r") as f:
            BUILD_HISTORY.update(json.load(f))
    except json.JSONDecodeError:
        BUILD_HISTORY = {"successful_builds": [], "failed_builds": []}

class SetupRequest(BaseModel):
    work_dir: str
    build_command: str
    build_delay: float = 2.0

def trigger_build():
    """Acquires lock and runs the build."""
    if BUILD_LOCK.acquire(blocking=False):
        try:
            run_build()
        finally:
            BUILD_LOCK.release()

class FileChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory or event.src_path.endswith((".log", ".json")):
            return
        global BUILD_TIMER
        if BUILD_TIMER and BUILD_TIMER.is_alive():
            BUILD_TIMER.cancel()
        BUILD_TIMER = threading.Timer(CONFIG["build_delay"], trigger_build)
        BUILD_TIMER.start()

def run_build():
    if not CONFIG["work_dir"] or not CONFIG["build_command"]:
        return
    BUILD_STATUS["status"] = "building"
    BUILD_STATUS["last_started"] = datetime.now().isoformat()
    BUILD_STATUS["last_ended"] = None

    output_log = os.path.join(CONFIG["work_dir"], CONFIG["output_log"])
    error_log = os.path.join(CONFIG["work_dir"], CONFIG["error_log"])
    os.makedirs(os.path.dirname(output_log) or ".", exist_ok=True)

    try:
        process = subprocess.run(
            shlex.split(CONFIG["build_command"]),
            capture_output=True,
            text=True,
            cwd=CONFIG["work_dir"],
            timeout=300  # 5-minute timeout
        )
        with open(output_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}]\n{process.stdout}\n")
        if process.returncode == 0:
            BUILD_STATUS["status"] = "success"
            build_time = (datetime.now() - datetime.fromisoformat(BUILD_STATUS["last_started"])).total_seconds()
            BUILD_HISTORY["successful_builds"].append(build_time)
            if len(BUILD_HISTORY["successful_builds"]) > 20:
                BUILD_HISTORY["successful_builds"].pop(0)
        else:
            BUILD_STATUS["status"] = "failed"
            build_time = (datetime.now() - datetime.fromisoformat(BUILD_STATUS["last_started"])).total_seconds()
            BUILD_HISTORY["failed_builds"].append(build_time)
            if len(BUILD_HISTORY["failed_builds"]) > 20:
                BUILD_HISTORY["failed_builds"].pop(0)
            with open(error_log, "a") as f:
                f.write(f"[{datetime.now().isoformat()}]\n{process.stderr}\n")
        BUILD_STATUS["last_output"] = process.stdout
    except subprocess.TimeoutExpired:
        BUILD_STATUS["status"] = "failed"
        BUILD_STATUS["last_output"] = "Build timed out"
        with open(error_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] Error: Build timed out\n")
    except Exception as e:
        BUILD_STATUS["status"] = "failed"
        BUILD_STATUS["last_output"] = str(e)
        with open(error_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] Error: {str(e)}\n")
    BUILD_STATUS["last_ended"] = datetime.now().isoformat()
    with BUILD_LOCK:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp:
            json.dump(BUILD_HISTORY, temp)
            temp_file = temp.name
        os.replace(temp_file, BUILD_HISTORY_FILE)

def calculate_estimated_time():
    successful_times = BUILD_HISTORY["successful_builds"]
    failed_times = BUILD_HISTORY["failed_builds"]

    def weighted_avg(times):
        if not times:
            return CONFIG["build_delay"]
        weights = [(1 - i * 0.05) ** 2 for i in range(min(len(times), 20))]
        weights.reverse()
        total = sum(t * w for t, w in zip(times[-20:], weights))
        weight_sum = sum(weights)
        return total / weight_sum if weight_sum else CONFIG["build_delay"]

    return {
        "success_estimate": round(weighted_avg(successful_times), 1),
        "fail_estimate": round(weighted_avg(failed_times), 1)
    }

@app.get("/mcp/tools")
async def get_tools():
    return TOOLS_SCHEMA

@app.get("/mcp/sse")
async def sse_endpoint():
    async def event_generator():
        last_status = None
        while True:
            current_status = json.dumps(BUILD_STATUS)
            if current_status != last_status:
                yield {
                    "event": "build_status",
                    "data": current_status
                }
                last_status = current_status
            await asyncio.sleep(1)  # Check every second
    return EventSourceResponse(event_generator())

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    try:
        req = await request.json()
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or "method" not in req or "id" not in req:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid Request"},
                "id": req.get("id", None)
            }

        method = req["method"]
        params = req.get("params", {})

        if method == "configure_build":
            if not isinstance(params, dict):
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Invalid params"},
                    "id": req["id"]
                }
            try:
                setup = SetupRequest(**params)
                if not os.path.isdir(setup.work_dir):
                    return {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": "Invalid working directory"},
                        "id": req["id"]
                    }
                # Validate build command
                cmd_parts = shlex.split(setup.build_command)
                if not cmd_parts or not shutil.which(cmd_parts[0]):
                    return {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": "Invalid or non-executable build command"},
                        "id": req["id"]
                    }
                global OBSERVER, BUILD_TIMER
                if OBSERVER and OBSERVER.is_alive():
                    OBSERVER.stop()
                    OBSERVER.join()  # Ensure full cleanup
                if BUILD_TIMER and BUILD_TIMER.is_alive():
                    BUILD_TIMER.cancel()
                CONFIG["work_dir"] = setup.work_dir
                CONFIG["build_command"] = setup.build_command
                CONFIG["build_delay"] = min(max(0.5, setup.build_delay), 10.0)
                observer = Observer()
                observer.schedule(FileChangeHandler(), path=CONFIG["work_dir"], recursive=True)
                observer.start()
                OBSERVER = observer
                return {
                    "jsonrpc": "2.0",
                    "result": "Configuration set, file watching started",
                    "id": req["id"]
                }
            except ValueError as e:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": f"Invalid params: {str(e)}"},
                    "id": req["id"]
                }

        elif method == "get_build_status":
            estimates = calculate_estimated_time()
            response = {
                "status": BUILD_STATUS["status"],
                "last_output": BUILD_STATUS["last_output"],
                "last_started": BUILD_STATUS["last_started"],
                "last_ended": BUILD_STATUS["last_ended"]
            }
            if BUILD_STATUS["status"] == "building":
                response["message"] = f"Check back in ~{estimates['success_estimate']} seconds"
            return {
                "jsonrpc": "2.0",
                "result": response,
                "id": req["id"]
            }

        elif method == "get_help_info":
            return {
                "jsonrpc": "2.0",
                "result": HELP_INFO,
                "id": req["id"]
            }
        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": req["id"]
            }

    except json.JSONDecodeError:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error"},
            "id": None
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_PORT", 5501))
    uvicorn.run(app, host="0.0.0.0", port=port)
