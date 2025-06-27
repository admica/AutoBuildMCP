#!/usr/bin/env python3
# PATH: ./server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import subprocess
import json
import shlex
from datetime import datetime
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import tempfile

app = FastAPI()

# Configuration
CONFIG = {
    "work_dir": None,
    "build_command": None,
    "build_delay": 2.0, # Default delay in seconds
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

# Load build history safely
if os.path.exists(BUILD_HISTORY_FILE):
    try:
        with open(BUILD_HISTORY_FILE, "r") as f:
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
            cwd=CONFIG["work_dir"]
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
    except Exception as e:
        BUILD_STATUS["status"] = "failed"
        with open(error_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] Error: {str(e)}\n")
        BUILD_STATUS["last_output"] = str(e)
    BUILD_STATUS["last_ended"] = datetime.now().isoformat()
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

@app.get("/setup")
async def setup():
    if not CONFIG["work_dir"] or not CONFIG["build_command"]:
        return {
            "message": "Setup required: POST to /set_directory_and_command with work_dir, build_command, and optional build_delay.",
            "defaults": {
                "output_log": CONFIG["output_log"],
                "error_log": CONFIG["error_log"],
                "build_delay": CONFIG["build_delay"]
            }
        }
    return {
        "message": "Server configured.",
        "config": {
            "work_dir": CONFIG["work_dir"],
            "build_command": CONFIG["build_command"],
            "build_delay": CONFIG["build_delay"],
            "output_log": os.path.join(CONFIG["work_dir"], CONFIG["output_log"]),
            "error_log": os.path.join(CONFIG["work_dir"], CONFIG["error_log"])
        }
    }

@app.post("/set_directory_and_command")
async def set_directory_and_command(request: SetupRequest):
    if not os.path.isdir(request.work_dir):
        raise HTTPException(status_code=400, detail="Invalid working directory")
    if not request.build_command.strip() or not request.build_command.startswith(("pio ", "./build.sh")):
        raise HTTPException(status_code=400, detail="Invalid build command")
    global OBSERVER
    if OBSERVER:
        OBSERVER.stop()
        try:
            OBSERVER.join(timeout=1)
        except TimeoutError:
            with open(os.path.join(CONFIG["work_dir"] or ".", CONFIG["error_log"]), "a") as f:
                f.write(f"[{datetime.now().isoformat()}] Warning: Observer did not stop cleanly\n")
    CONFIG["work_dir"] = request.work_dir
    CONFIG["build_command"] = request.build_command
    CONFIG["build_delay"] = min(max(0.5, request.build_delay), 10.0) # 0.5s to 10s
    observer = Observer()
    observer.schedule(FileChangeHandler(), path=CONFIG["work_dir"], recursive=True)
    observer.start()
    OBSERVER = observer
    return {"message": "Configuration set, file watching started"}

@app.get("/build_status")
async def build_status():
    estimates = calculate_estimated_time()
    response = {
        "status": BUILD_STATUS["status"],
        "last_output": BUILD_STATUS["last_output"],
        "last_started": BUILD_STATUS["last_started"],
        "last_ended": BUILD_STATUS["last_ended"]
    }
    if BUILD_STATUS["status"] == "building":
        response["message"] = f"Check back in ~{estimates['success_estimate']} seconds"
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5501)
