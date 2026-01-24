# SPEAR FastAPI Application
# REST API for BPMN Process Engine with RDF Storage

import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api.models import HealthResponse, ApiInfoResponse, ErrorResponse
from src.api.processes import router as processes_router
from src.api.instances import router as instances_router
from src.api.tasks import router as tasks_router
from src.api.topics import router as topics_router
from src.api.errors import router as errors_router

# Use the unified get_storage function from storage package
# This automatically uses StorageFacade when SPEAR_USE_FACADE=true
from src.api.storage import get_storage

# Initialize storage on module load
storage = get_storage()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    startup_time = time.time()
    print("SPEAR API starting up...")
    print("RDF storage initialized")
    yield
    # Shutdown
    print("SPEAR API shutting down...")


# Create FastAPI application
app = FastAPI(
    title="SPEAR BPMN Engine API",
    description="""
    ## Semantic Process Engine as RDF (SPEAR)
    
    A lightweight BPMN orchestrator using RDF and SPARQL as its core execution language.
    All process data is stored and managed as RDF triples.
    
    ### Features
    - **Process Deployment**: Deploy BPMN 2.0 XML processes
    - **Instance Management**: Start, stop, and monitor process instances
    - **Variable Management**: Get and set process variables
    - **Audit Logging**: Complete execution history
    - **Statistics**: Real-time process metrics
    
    ### Architecture
    All data is stored as RDF triples in a flexible, queryable format.
    Process definitions, instances, and audit logs are all managed through SPARQL.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "Process Definitions",
            "description": "Manage BPMN process definitions",
        },
        {
            "name": "Process Instances",
            "description": "Manage running process instances",
        },
        {"name": "Variables", "description": "Process instance variables"},
        {"name": "Audit", "description": "Execution audit logs"},
        {
            "name": "Error Handling",
            "description": "Error throwing and instance cancellation",
        },
        {"name": "System", "description": "Health and system information"},
    ],
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(processes_router, prefix="/api/v1")
app.include_router(instances_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(topics_router, prefix="/api/v1")
app.include_router(errors_router, prefix="/api/v1")


# ==================== Health & Info Endpoints ====================


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.

    Returns the current status of the SPEAR API.
    """
    stats = storage.get_statistics()

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime_seconds=time.time() - 1710000000,  # Would need proper startup tracking
        triple_count=stats["total_triples"],
    )


@app.get("/info", response_model=ApiInfoResponse, tags=["System"])
async def api_info():
    """
    Get API information.

    Returns basic information about the SPEAR API.
    """
    return ApiInfoResponse(
        name="SPEAR BPMN Engine API",
        version="1.0.0",
        description="Semantic Process Engine as RDF - REST API",
        endpoints_count=15,
        documentation_url="/docs",
    )


@app.get("/", tags=["System"])
async def root():
    """
    Root endpoint with API overview.

    Returns basic information and links to documentation.
    """
    return {
        "name": "SPEAR BPMN Engine API",
        "version": "1.0.0",
        "description": "Semantic Process Engine as RDF",
        "documentation": "/docs",
        "health": "/health",
        "info": "/info",
        "endpoints": {
            "processes": "/api/v1/processes",
            "instances": "/api/v1/instances",
        },
    }


# ==================== Global Error Handler ====================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "code": f"HTTP_{exc.status_code}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc) if app.debug else "An unexpected error occurred",
            "code": "INTERNAL_ERROR",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


# ==================== Statistics Endpoint ====================


@app.get("/statistics", tags=["System"])
async def get_statistics():
    """
    Get system statistics.

    Returns overall statistics about the SPEAR system.
    """
    stats = storage.get_statistics()

    # Get instance counts by status
    all_instances = storage.list_instances()
    status_counts = {}
    for inst in all_instances["instances"]:
        status = inst.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "processes": {"total": stats["process_count"]},
        "instances": {"total": stats["instance_count"], "by_status": status_counts},
        "rdf_storage": {"total_triples": stats["total_triples"]},
    }


# ==================== Export Endpoints ====================


@app.get("/export/processes", tags=["System"])
async def export_all_processes():
    """
    Export all process definitions as RDF.

    Returns all process definitions in Turtle format.
    """
    return {
        "format": "turtle",
        "triples": len(storage.definitions_graph),
        "rdf": storage.definitions_graph.serialize(format="turtle"),
    }


# Main entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
