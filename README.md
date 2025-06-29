# AutoBuildMCP: An MCP-Powered Build Automation Server

AutoBuildMCP is a robust, profile-based build automation server powered by the Model Context Protocol (MCP). It allows an MCP-compliant client, such as Cursor, to manage, execute, and monitor build processes across multiple projects seamlessly.

The server is built on a persistent, stateful architecture that uses a build queue to manage concurrent operations, preventing system overloads.

## Features

- **Profile-Based Management:** Define unique build "profiles" for each of your projects. Each profile encapsulates the project's path, build command, environment variables, and timeouts.
- **Persistent State:** All build profiles are stored in a simple `builds.json` file, ensuring your configurations persist across server restarts.
- **Build Queuing System:** A sophisticated queuing system manages a pool of concurrent builds (default: 2), preventing the server from being overloaded by multiple simultaneous requests. New builds are queued and executed as slots become available.
- **Asynchronous, Non-Blocking Execution:** Builds run as background processes, allowing the server to remain responsive and handle other API calls while builds are in progress.
- **Full Lifecycle Management:** A complete suite of tools to configure, start, monitor, stop, and delete builds.
- **Log Capture:** The full `stdout` and `stderr` of every build run are captured to a dedicated log file for easy debugging.
- **Restart Resiliency:** The server intelligently detects and marks builds as "unknown" if the server was restarted during their execution, preventing stuck "running" states.

## Setup & Installation

The setup process is streamlined for both Windows and Linux/macOS environments.

### 1. Build the Environment

This script creates a Python virtual environment and installs all necessary dependencies from `requirements.txt`, including `psutil` for process management.

**On Windows:**
```cmd
.\build.bat
```

**On Linux/macOS:**
```bash
./build.sh
```

### 2. Run the Server

This starts the AutoBuildMCP server and its background build worker. The server will be available at `http://localhost:5307`.

**On Windows:**
```cmd
.\run.bat
```

**On Linux/macOS:**
```bash
./run.sh
```
The server is now running and ready to accept requests from an MCP client.

## API / Tool Reference

The server exposes a set of tools that can be called by any MCP-compliant client.

---

### `configure_build`
Creates or updates a build profile.

- **`profile_name`** (str): A unique name for the profile (e.g., `my-web-app`).
- **`project_path`** (str): The absolute or relative path to the project's root directory.
- **`build_command`** (str): The shell command to execute for the build (e.g., `npm run build`).
- **`environment`** (dict, optional): A dictionary of environment variables to set for the build process.
- **`timeout`** (int, optional): A timeout for the build in seconds (not yet implemented).

---

### `list_builds`
Lists all configured build profiles and their last known status.

---

### `get_build_status`
Retrieves the current status of a specific build profile.
- **`profile_name`** (str): The name of the profile to check.
- **Returns:** The status, which can be `configured`, `queued`, `running`, `succeeded`, `failed`, `stopped`, or `unknown`.

---

### `start_build`
Adds a build request for a profile to the queue.
- **`profile_name`** (str): The name of the profile to build.
- **Returns:** A confirmation message and the build's position in the queue.

---

### `stop_build`
Stops a currently running build.
- **`profile_name`** (str): The name of the running profile to stop.

---

### `delete_build_profile`
Deletes a build profile from the server.
- **`profile_name`** (str): The name of the profile to delete.

---

### `get_build_log`
Retrieves the log file for the last run of a profile.
- **`profile_name`** (str): The name of the profile.
- **`lines`** (int, optional): If provided, returns only the last N lines of the log (log tailing).

## The `builds.json` State File

This file is the heart of the server, storing all profile configurations and their last run state. You can view it to see the current state of the system.

**Example `builds.json`:**
```json
{
  "my-web-app": {
    "project_path": "C:/Users/Admin/projects/my-app",
    "build_command": "npm install && npm run build",
    "environment": {
      "NODE_ENV": "production"
    },
    "timeout": 600,
    "status": "succeeded",
    "last_run": {
      "run_id": "08f7e57e-e46c-4ac3-b564-f3588018b9fd",
      "pid": 12052,
      "start_time": "2025-06-29T22:45:00.123456Z",
      "end_time": "2025-06-29T22:46:12.123456Z",
      "log_file": "logs/08f7e57e-e46c-4ac3-b564-f3588018b9fd.log",
      "outcome_note": "Build status is unknown; server was restarted during execution."
    }
  }
}
```

