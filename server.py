import subprocess
import json
import time
import os
import shlex

# Configuration
SERVER_URL = "https://localhost:5501/mcp"
TEST_DIR = os.path.abspath("./")  # Ensure absolute path for work_dir
BUILD_COMMAND = "./build.sh"

def run_curl_command(curl_cmd):
    """Execute a curl command and return the parsed JSON response."""
    try:
        result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running curl: {result.stderr}")
            return None
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Failed to parse response: {result.stdout}")
        return None

def post_rpc(method, params, id_):
    """Helper to post JSON-RPC requests to the MCP server."""
    json_payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": id_
    })
    cmd = (
        f'curl -s -X POST -H "Content-Type: application/json" -d {shlex.quote(json_payload)} {SERVER_URL}'
    )
    return run_curl_command(cmd)

def test_configure_build():
    print("Testing configure_build...")
    params = {
        "work_dir": TEST_DIR,
        "build_command": BUILD_COMMAND,
        "build_delay": 2.0
    }
    response = post_rpc("configure_build", params, 1)
    if response and "result" in response and response["result"] == "Configuration set, file watching started":
        print("configure_build: SUCCESS")
    else:
        print(f"configure_build: FAILED, response: {response}")

def test_get_build_status_idle():
    print("Testing get_build_status (should be idle)...")
    response = post_rpc("get_build_status", {}, 2)
    if response and "result" in response and response["result"]["status"] == "idle":
        print("get_build_status (idle): SUCCESS")
    else:
        print(f"get_build_status (idle): FAILED, response: {response}")

def test_get_build_status_building_and_completed():
    print("Testing get_build_status during build process...")

    # Simulate a file change to trigger build
    dummy_file = os.path.join(TEST_DIR, "test_dummy_file.txt")
    with open(dummy_file, "w") as f:
        f.write("Trigger build test.")

    # Wait slightly more than build_delay for build to start
    time.sleep(2.5)
    response = post_rpc("get_build_status", {}, 3)
    if response and "result" in response and response["result"]["status"] == "building":
        print("get_build_status (building): SUCCESS")
    else:
        print(f"get_build_status (building): FAILED, response: {response}")

    # Wait up to 15 seconds for build to complete
    wait_time = 0
    status = None
    while wait_time < 15:
        response = post_rpc("get_build_status", {}, 4)
        if response and "result" in response:
            status = response["result"]["status"]
            if status in ["success", "failed"]:
                print(f"get_build_status (completed): SUCCESS, status: {status}")
                break
        time.sleep(1)
        wait_time += 1
    else:
        print(f"get_build_status (completed): FAILED or timeout, last status: {status}")

    # Clean up dummy file
    if os.path.exists(dummy_file):
        os.remove(dummy_file)

def test_get_help_info():
    print("Testing get_help_info...")
    response = post_rpc("get_help_info", {}, 5)
    if response and response.get("result") and "description" in response["result"]:
        print("get_help_info: SUCCESS")
    else:
        print(f"get_help_info: FAILED, response: {response}")

def test_invalid_request():
    print("Testing invalid JSON-RPC request (missing method)...")
    # Missing "method" key
    json_payload = '{"jsonrpc": "2.0", "params": {}, "id": 6}'
    cmd = f'curl -s -X POST -H "Content-Type: application/json" -d {shlex.quote(json_payload)} {SERVER_URL}'
    response = run_curl_command(cmd)
    if response and "error" in response and response["error"]["code"] == -32600:
        print("invalid_request: SUCCESS")
    else:
        print(f"invalid_request: FAILED, response: {response}")

def test_unknown_method():
    print("Testing unknown method...")
    response = post_rpc("nonexistent_method", {}, 7)
    if response and "error" in response and response["error"]["code"] == -32601:
        print("unknown_method: SUCCESS")
    else:
        print(f"unknown_method: FAILED, response: {response}")

if __name__ == "__main__":
    print("Starting AutoBuildMCP tests...")

    if not os.path.isdir(TEST_DIR):
        print(f"ERROR: Test directory {TEST_DIR} does not exist. Please update TEST_DIR.")
        exit(1)

    test_configure_build()
    test_get_build_status_idle()
    test_get_build_status_building_and_completed()
    test_get_help_info()
    test_invalid_request()
    test_unknown_method()

    print("Tests completed.")
