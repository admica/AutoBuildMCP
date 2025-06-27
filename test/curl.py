import subprocess
import json
import time
import os
import shlex

# Configuration
SERVER_URL = "http://localhost:5501/mcp"
TEST_DIR = "./"
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

def test_configure_build():
    """Test the configure_build method."""
    print("Testing configure_build...")
    json_payload = f'{{"jsonrpc": "2.0", "method": "configure_build", "params": {{"work_dir": "{TEST_DIR}", "build_command": {json.dumps(BUILD_COMMAND)}, "build_delay": 2.0}}, "id": 1}}'
    cmd = (
        f'curl -X POST -H "Content-Type: application/json" -d {shlex.quote(json_payload)} {SERVER_URL}'
    )
    response = run_curl_command(cmd)
    if response and "result" in response and response["result"] == "Configuration set, file watching started":
        print("configure_build: SUCCESS")
    else:
        print(f"configure_build: FAILED, response: {response}")

def test_get_build_status():
    """Test get_build_status at different stages."""
    print("Testing get_build_status...")
    cmd = (
        f'curl -X POST -H "Content-Type: application/json" -d \''
        f'{{"jsonrpc": "2.0", "method": "get_build_status", "params": {{}}, "id": 2}}\' {SERVER_URL}'
    )
    
    # Check initial status (should be idle)
    response = run_curl_command(cmd)
    if response and "result" in response and response["result"]["status"] == "idle":
        print("get_build_status (idle): SUCCESS")
    else:
        print(f"get_build_status (idle): FAILED, response: {response}")
    
    # Simulate a file change (create a dummy file in TEST_DIR)
    if os.path.isdir(TEST_DIR):
        dummy_file = os.path.join(TEST_DIR, "test.txt")
        with open(dummy_file, "w") as f:
            f.write("Test file")
        print("Simulated file change")
        
        # Wait for build to start (slightly more than build_delay)
        time.sleep(2.5)
        response = run_curl_command(cmd)
        if response and "result" in response and response["result"]["status"] == "building":
            print("get_build_status (building): SUCCESS")
        else:
            print(f"get_build_status (building): FAILED, response: {response}")
        
        # Wait for build to complete (assume max 10s)
        time.sleep(10)
        response = run_curl_command(cmd)
        if response and "result" in response and response["result"]["status"] in ["success", "failed"]:
            print(f"get_build_status (completed): SUCCESS, status: {response['result']['status']}")
        else:
            print(f"get_build_status (completed): FAILED, response: {response}")
        
        # Clean up dummy file
        os.remove(dummy_file)
    else:
        print(f"Skipping file change test: {TEST_DIR} does not exist")

def test_invalid_request():
    """Test an invalid JSON-RPC request."""
    print("Testing invalid JSON-RPC request...")
    cmd = (
        f'curl -X POST -H "Content-Type: application/json" -d \''
        f'{{"jsonrpc": "2.0", "params": {{}}, "id": 3}}\' {SERVER_URL}'
    )
    response = run_curl_command(cmd)
    if response and "error" in response and response["error"]["code"] == -32600:
        print("invalid_request: SUCCESS")
    else:
        print(f"invalid_request: FAILED, response: {response}")

def test_unknown_method():
    """Test an unknown method."""
    print("Testing unknown method...")
    cmd = (
        f'curl -X POST -H "Content-Type: application/json" -d \''
        f'{{"jsonrpc": "2.0", "method": "invalid_method", "params": {{}}, "id": 4}}\' {SERVER_URL}'
    )
    response = run_curl_command(cmd)
    if response and "error" in response and response["error"]["code"] == -32601:
        print("unknown_method: SUCCESS")
    else:
        print(f"unknown_method: FAILED, response: {response}")

if __name__ == "__main__":
    print("Starting AutoBuildMCP tests...")
    if not os.path.isdir(TEST_DIR):
        print(f"ERROR: Test directory {TEST_DIR} does not exist. Please update TEST_DIR.")
    else:
        test_configure_build()
        test_get_build_status()
        test_invalid_request()
        test_unknown_method()
    print("Tests completed.")
