#!/usr/bin/env python3
"""
AutoBuildMCP Server - FastAPI implementation with full MCP protocol compliance
Designed to work with Cursor's MCP client
"""

import asyncio
import json
import logging
import ssl
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory state (in production, use a proper database)
build_configs = {}
build_status = {}
build_logs = {}

class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

class JSONRPCNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None

class ToolParameter(BaseModel):
    type: str
    description: str
    required: bool = False

class Tool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]

class BuildConfig(BaseModel):
    project_path: str
    build_command: str
    environment: Optional[Dict[str, str]] = None
    timeout: Optional[int] = 300

class BuildStatus(BaseModel):
    build_id: str
    status: str  # "pending", "running", "completed", "failed"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    output: Optional[str] = None
    error: Optional[str] = None

# MCP Server implementation
class AutoBuildMCPServer:
    def __init__(self):
        self.name = "AutoBuildMCP"
        self.version = "1.0.0"
        self.description = "Automated build monitoring and management server"
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {}
        }
        
    def initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MCP initialize method"""
        logger.info("MCP server initialized")
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": self.capabilities,
            "serverInfo": {
                "name": self.name,
                "version": self.version,
                "description": self.description
            }
        }
    
    def tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MCP tools/list method"""
        return {
            "tools": [
                {
                    "name": "configure_build",
                    "description": "Configure a new build with project path and build command",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_path": {
                                "type": "string",
                                "description": "Path to the project directory"
                            },
                            "build_command": {
                                "type": "string", 
                                "description": "Command to run for building the project"
                            },
                            "environment": {
                                "type": "object",
                                "description": "Environment variables for the build",
                                "additionalProperties": {"type": "string"}
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Build timeout in seconds (default: 300)"
                            }
                        },
                        "required": ["project_path", "build_command"]
                    }
                },
                {
                    "name": "get_build_status",
                    "description": "Get the current status of a build",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "build_id": {
                                "type": "string",
                                "description": "ID of the build to check"
                            }
                        },
                        "required": ["build_id"]
                    }
                },
                {
                    "name": "list_builds",
                    "description": "List all configured builds",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                },
                {
                    "name": "start_build",
                    "description": "Start a build for a configured project",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_path": {
                                "type": "string",
                                "description": "Path to the project to build"
                            }
                        },
                        "required": ["project_path"]
                    }
                },
                {
                    "name": "stop_build",
                    "description": "Stop a running build",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "build_id": {
                                "type": "string",
                                "description": "ID of the build to stop"
                            }
                        },
                        "required": ["build_id"]
                    }
                }
            ]
        }
    
    def tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MCP tools/call method"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        logger.info(f"Calling tool: {tool_name} with arguments: {arguments}")
        
        # Route to appropriate tool method
        if tool_name == "configure_build":
            result = self.configure_build(arguments)
        elif tool_name == "get_build_status":
            result = self.get_build_status(arguments)
        elif tool_name == "list_builds":
            result = self.list_builds(arguments)
        elif tool_name == "start_build":
            result = self.start_build(arguments)
        elif tool_name == "stop_build":
            result = self.stop_build(arguments)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    
    def configure_build(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Configure a new build"""
        try:
            config = BuildConfig(**params)
            build_id = str(uuid.uuid4())
            build_configs[build_id] = config.dict()
            
            logger.info(f"Configured build {build_id} for project: {config.project_path}")
            
            return {
                "build_id": build_id,
                "message": f"Build configured successfully for {config.project_path}",
                "config": config.dict()
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid build configuration: {str(e)}")
    
    def get_build_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get build status"""
        build_id = params.get("build_id")
        if not build_id:
            raise HTTPException(status_code=400, detail="build_id is required")
        
        if build_id not in build_status:
            raise HTTPException(status_code=404, detail=f"Build {build_id} not found")
        
        return build_status[build_id]
    
    def list_builds(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all configured builds"""
        return {
            "builds": [
                {
                    "build_id": bid,
                    "config": config,
                    "status": build_status.get(bid, {"status": "not_started"})
                }
                for bid, config in build_configs.items()
            ]
        }
    
    def start_build(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a build (simulated)"""
        project_path = params.get("project_path")
        if not project_path:
            raise HTTPException(status_code=400, detail="project_path is required")
        
        # Find build config for this project
        build_id = None
        for bid, config in build_configs.items():
            if config.get("project_path") == project_path:
                build_id = bid
                break
        
        if not build_id:
            raise HTTPException(status_code=404, detail=f"No build configuration found for {project_path}")
        
        # Simulate build start
        build_status[build_id] = {
            "build_id": build_id,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "output": "Build started...",
            "error": None
        }
        
        logger.info(f"Started build {build_id} for project: {project_path}")
        
        return {
            "build_id": build_id,
            "message": f"Build started for {project_path}",
            "status": "running"
        }
    
    def stop_build(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop a running build"""
        build_id = params.get("build_id")
        if not build_id:
            raise HTTPException(status_code=400, detail="build_id is required")
        
        if build_id not in build_status:
            raise HTTPException(status_code=404, detail=f"Build {build_id} not found")
        
        current_status = build_status[build_id]
        if current_status.get("status") != "running":
            raise HTTPException(status_code=400, detail=f"Build {build_id} is not running")
        
        # Stop the build
        build_status[build_id] = {
            **current_status,
            "status": "stopped",
            "end_time": datetime.now().isoformat(),
            "output": current_status.get("output", "") + "\nBuild stopped by user."
        }
        
        logger.info(f"Stopped build {build_id}")
        
        return {
            "build_id": build_id,
            "message": f"Build {build_id} stopped successfully",
            "status": "stopped"
        }

# Create server instance
mcp_server = AutoBuildMCPServer()

# FastAPI app
app = FastAPI(
    title="AutoBuildMCP Server",
    description="MCP server for automated build monitoring and management",
    version="1.0.0"
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "AutoBuildMCP Server is running", "version": "1.0.0"}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/mcp")
async def handle_jsonrpc(request: JSONRPCRequest):
    """Handle JSON-RPC 2.0 requests for MCP protocol"""
    try:
        logger.info(f"Received MCP request: {request.method}")
        
        # Route to appropriate MCP method
        if request.method == "initialize":
            result = mcp_server.initialize(request.params or {})
        elif request.method == "tools/list":
            result = mcp_server.tools_list(request.params or {})
        elif request.method == "tools/call":
            result = mcp_server.tools_call(request.params or {})
        else:
            return JSONRPCResponse(
                error={
                    "code": -32601,
                    "message": f"Method not found: {request.method}"
                },
                id=request.id
            )
        
        return JSONRPCResponse(result=result, id=request.id)
        
    except HTTPException as e:
        return JSONRPCResponse(
            error={
                "code": e.status_code,
                "message": e.detail
            },
            id=request.id
        )
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONRPCResponse(
            error={
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            },
            id=request.id
        )

@app.get("/mcp/sse")
async def sse_endpoint():
    """Server-Sent Events endpoint for MCP streaming"""
    async def event_stream():
        """Generate SSE events for MCP protocol"""
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"
            
            # Send tool discovery events
            tools_info = mcp_server.tools_list({})
            for tool in tools_info["tools"]:
                yield f"data: {json.dumps({'type': 'tool_discovered', 'tool': tool})}\n\n"
            
            # Keep connection alive and send periodic updates
            while True:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                
        except asyncio.CancelledError:
            logger.info("MCP SSE connection closed")
        except Exception as e:
            logger.error(f"MCP SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )

if __name__ == "__main__":
    # Run server on HTTP for development
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=5305,
        log_level="info",
        reload=False
    ) 
