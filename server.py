from mcp.server.fastmcp import FastMCP
import logging
import socket
import uvicorn

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create MCP server
mcp = FastMCP("AutoBuildMCP")
logger.info("MCP Server 'AutoBuildMCP' initialized")

@mcp.tool()
def configure_build(project_path: str, build_command: str, environment: dict = None, timeout: int = 300) -> str:
    """Configure a build for a project."""
    logger.info(f"Configuring build for {project_path} with command '{build_command}'")
    return f"Configured build for {project_path} with command '{build_command}'"

@mcp.tool()
def get_build_status(build_id: str) -> str:
    """Get the status of a build."""
    logger.info(f"Getting status for build {build_id}")
    return f"Status for build {build_id}: not_started"

# Additional methods for build management
def list_builds():
    logger.info("Listing all builds")
    return {"builds": []}

def start_build(project_path: str):
    logger.info(f"Starting build for {project_path}")
    return {"message": f"Started build for {project_path}"}

def stop_build(build_id: str):
    logger.info(f"Stopping build {build_id}")
    return {"message": f"Stopped build {build_id}"}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.error(f"Could not detect local IP: {e}")
        return '127.0.0.1'  # Fallback to localhost

if __name__ == "__main__":
    port = 5335
    logger.info(f"Starting AutoBuildMCP server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    logger.info("AutoBuildMCP server stopped")
