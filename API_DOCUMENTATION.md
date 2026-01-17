# SPEAR REST API Documentation

## Overview

SPEAR provides a comprehensive REST API for managing BPMN processes with all data stored as RDF triples. The API is built with FastAPI and provides automatic OpenAPI documentation.

## Base URL

```
http://localhost:8000
```

## API Version

```
/api/v1
```

## Endpoints Summary

### System Endpoints
- `GET /` - API root with overview
- `GET /health` - Health check
- `GET /info` - API information
- `GET /statistics` - System statistics

### Process Definition Endpoints
- `GET /api/v1/processes` - List all processes
- `POST /api/v1/processes` - Deploy new process
- `GET /api/v1/processes/{id}` - Get process details
- `PUT /api/v1/processes/{id}` - Update process
- `DELETE /api/v1/processes/{id}` - Delete process
- `GET /api/v1/processes/{id}/rdf` - Get RDF representation
- `GET /api/v1/processes/{id}/statistics` - Get process statistics

### Process Instance Endpoints
- `GET /api/v1/instances` - List all instances
- `POST /api/v1/instances` - Start new instance
- `GET /api/v1/instances/{id}` - Get instance details
- `POST /api/v1/instances/{id}/stop` - Stop instance
- `DELETE /api/v1/instances/{id}` - Delete instance
- `GET /api/v1/instances/{id}/variables` - Get variables
- `PUT /api/v1/instances/{id}/variables/{name}` - Set variable
- `GET /api/v1/instances/{id}/audit-log` - Get audit log
- `GET /api/v1/instances/{id}/statistics` - Get instance statistics

## Quick Start

### 1. Start the API Server

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API
python main.py

# Or with custom port
python main.py --port 8080

# Or with auto-reload
python main.py --reload
```

### 2. Access Documentation

Once the server is running:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 3. Example Usage

#### Deploy a Process

```bash
curl -X POST "http://localhost:8000/api/v1/processes" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Order Processing",
    "description": "Order fulfillment process",
    "version": "1.0.0",
    "bpmn_file": "<?xml version=\"1.0\"...><bpmn:definitions>...</bpmn:definitions>"
  }'
```

Response:
```json
{
  "id": "abc123-def456",
  "name": "Order Processing",
  "description": "Order fulfillment process",
  "version": "1.0.0",
  "status": "active",
  "rdf_triples_count": 150,
  "created_at": "2024-01-17T10:30:00Z",
  "updated_at": "2024-01-17T10:30:00Z"
}
```

#### Start an Instance

```bash
curl -X POST "http://localhost:8000/api/v1/instances" \
  -H "Content-Type: application/json" \
  -d '{
    "process_id": "abc123-def456",
    "variables": {
      "customer_name": "John Doe",
      "order_total": 150.00
    }
  }'
```

Response:
```json
{
  "id": "inst-123-456",
  "process_id": "abc123-def456",
  "process_version": "1.0.0",
  "status": "RUNNING",
  "current_nodes": ["http://example.org/bpmn/StartEvent_1"],
  "variables": {
    "customer_name": "John Doe",
    "order_total": "150.00"
  },
  "created_at": "2024-01-17T10:30:05Z",
  "updated_at": "2024-01-17T10:30:05Z",
  "completed_at": null
}
```

#### Get Instance Status

```bash
curl "http://localhost:8000/api/v1/instances/inst-123-456"
```

#### Stop an Instance

```bash
curl -X POST "http://localhost:8000/api/v1/instances/inst-123-456/stop" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Customer cancelled order"
  }'
```

## RDF Storage

All data is stored as RDF triples in Turtle format:

### Process Definitions
```turtle
@prefix proc: <http://example.org/process/> .
@prefix meta: <http://example.org/meta/> .

proc:abc123-def456 rdf:type proc:ProcessDefinition ;
  meta:name "Order Processing" ;
  meta:version "1.0.0" ;
  meta:status "active" ;
  meta:deployedAt "2024-01-17T10:30:00Z" .
```

### Process Instances
```turtle
@prefix inst: <http://example.org/instance/> .
@prefix var: <http://example.org/variables/> .

inst:inst-123-456 rdf:type inst:ProcessInstance ;
  inst:processDefinition proc:abc123-def456 ;
  inst:status "RUNNING" ;
  inst:hasVariable var:inst-123-456_customer_name ;
  var:inst-123-456_customer_name var:name "customer_name" ;
  var:inst-123-456_customer_name var:value "John Doe" .
```

## Query Examples

### SPARQL Query - Find All Running Instances

```sparql
SELECT ?instance ?process WHERE {
  ?instance rdf:type inst:ProcessInstance .
  ?instance inst:status "RUNNING" .
  ?instance inst:processDefinition ?process .
}
```

### SPARQL Query - Get Process Statistics

```sparql
SELECT ?process (COUNT(?instance) as ?count) WHERE {
  ?process rdf:type proc:ProcessDefinition .
  ?instance inst:processDefinition ?process .
} GROUP BY ?process
```

## Error Handling

All errors return a consistent JSON response:

```json
{
  "error": "Process not found",
  "code": "NOT_FOUND",
  "timestamp": "2024-01-17T10:30:00Z"
}
```

### Common Error Codes

| Code | Status | Description |
|------|--------|-------------|
| NOT_FOUND | 404 | Resource not found |
| VALIDATION_ERROR | 400 | Invalid request data |
| INTERNAL_ERROR | 500 | Server error |
| HTTP_404 | 404 | Endpoint not found |

## Pagination

List endpoints support pagination:

```bash
GET /api/v1/processes?page=1&page_size=20
```

Response:
```json
{
  "processes": [...],
  "total": 50,
  "page": 1,
  "page_size": 20
}
```

## Filtering

List endpoints support filtering:

```bash
# Filter by status
GET /api/v1/processes?status=active

# Filter by process
GET /api/v1/instances?process_id=abc123&status=RUNNING
```

## Rate Limiting

Not currently implemented, but can be added with middleware.

## Authentication

Not currently implemented. Future versions will support:
- API Key authentication
- OAuth 2.0
- JWT tokens

## WebSocket Support

Future versions will add WebSocket endpoints for:
- Real-time instance monitoring
- Push notifications for task assignments
- Live audit log streaming

## Versioning

API versioning follows semantic versioning:
- Major version in URL (`/api/v1`)
- Minor version in headers
- Backward-compatible changes in same version
- Breaking changes increment major version

## SDKs

Official SDKs planned for:
- Python (coming soon)
- JavaScript/TypeScript (coming soon)
- Java (coming soon)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

MIT License - see [LICENSE](../LICENSE) for details.
