#!/usr/bin/env python3
"""
SPEAR BPMN Engine REST API
=========================

A FastAPI-based REST API for managing BPMN processes with RDF storage.

Usage:
    python main.py                    # Run on default port 8000
    python main.py --port 8080        # Run on port 8080
    python main.py --reload           # Auto-reload on changes

API Documentation:
    http://localhost:8000/docs       # Swagger UI
    http://localhost:8000/redoc       # ReDoc

Endpoints:
    GET    /health                   # Health check
    GET    /info                     # API information
    GET    /statistics               # System statistics
    
    GET    /api/v1/processes          # List processes
    POST   /api/v1/processes          # Deploy process
    GET    /api/v1/processes/{id}     # Get process
    PUT    /api/v1/processes/{id}     # Update process
    DELETE /api/v1/processes/{id}     # Delete process
    
    GET    /api/v1/instances          # List instances
    POST   /api/v1/instances          # Start instance
    GET    /api/v1/instances/{id}     # Get instance
    POST   /api/v1/instances/{id}/stop # Stop instance
    GET    /api/v1/instances/{id}/variables  # Get variables
    PUT    /api/v1/instances/{id}/variables/{name}  # Set variable
    GET    /api/v1/instances/{id}/audit-log  # Get audit log
"""

import sys
import argparse
from src.api.main import app
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="SPEAR BPMN Engine REST API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("SPEAR BPMN Engine API")
    print("=" * 60)
    print()
    print(f"API Documentation: http://{args.host}:{args.port}/docs")
    print(f"ReDoc: http://{args.host}:{args.port}/redoc")
    print(f"Health Check: http://{args.host}:{args.port}/health")
    print()
    print("Endpoints:")
    print("   - GET    /api/v1/processes")
    print("   - POST   /api/v1/processes")
    print("   - GET    /api/v1/instances")
    print("   - POST   /api/v1/instances")
    print()
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info" if not args.debug else "debug"
    )


if __name__ == "__main__":
    main()
