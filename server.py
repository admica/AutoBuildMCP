from mcp.server.fastmcp import FastMCP
import logging
import uvicorn

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create MCP server - this is the correct way.
mcp = FastMCP("AutoBuildMCP")
logger.info("MCP Server 'AutoBuildMCP' initialized")

@mcp.tool()
def configure_build(project_path: str, build_command: str, environment: dict = None, timeout: int = 300) -> dict:
    """Configure a build for a project."""
    logger.info(f"Configuring build for {project_path} with command '{build_command}'")
    return {"message": f"Configured build for {project_path} with command '{build_command}'"}

@mcp.tool()
def get_build_status(build_id: str) -> dict:
    """Get the status of a build."""
    logger.info(f"Getting status for build {build_id}")
    return {"status": f"Status for build {build_id}: not_started"}

@mcp.tool()
def list_builds() -> dict:
    """List all builds."""
    logger.info("Listing all builds")
    return {"builds": []}

@mcp.tool()
def start_build(project_path: str) -> dict:
    """Start a build for a project."""
    logger.info(f"Starting build for {project_path}")
    return {"message": f"Started build for {project_path}"}

@mcp.tool()
def stop_build(build_id: str) -> dict:
    """Stop a running build."""
    logger.info(f"Stopping build {build_id}")
    return {"message": f"Stopped build {build_id}"}

if __name__ == "__main__":
    port = 5307
    # This is the correct way to get the ASGI app, based on the source code.
    app = mcp.streamable_http_app()
    logger.info(f"Starting AutoBuildMCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    logger.info("AutoBuildMCP server stopped")
