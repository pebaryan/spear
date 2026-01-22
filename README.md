
## SPEAR: Semantic Process Engine as RDF

### 1. Overview

The **Semantic Process Engine** is a lightweight, Python-based BPMN orchestrator that uses **RDF (Resource Description Framework)** and **SPARQL** as its core execution language. Unlike traditional engines that store state in relational tables, this engine treats business processes as a living Knowledge Graph.

### 2. Why Semantic? (The Value Proposition)

* **Schema-less Flexibility:** Add new process variables or metadata on the fly without database migrations.
* **Logical Reasoning:** Use SPARQL `ASK` queries to make complex routing decisions based on the entire knowledge base, not just local variables.
* **Native Audit Trail:** Every process step is an immutable event in the graph, making the engine "Audit-Ready" by design.
* **Interoperability:** Your process data is stored in W3C standard formats, making it instantly readable by AI, BI tools, and other RDF-compatible systems.

---

### 3. High-Level Architecture

The engine follows a decoupled, asynchronous pattern:

* **Data Layer:** A Triplestore (Fuseki, GraphDB) storing Process Definitions and Runtime State.
* **Orchestration:** A Python core using `rdflib` to move "Tokens" through the graph.
* **Execution:** Background workers that trigger Python functions based on `bpmn:topic`.
* **Interface:** A Flask Web API for starting instances and completing human tasks.

---

### 4. Core Concepts

| Concept | Implementation |
| --- | --- |
| **Definitions** | Turtle (.ttl) files defining the BPMN graph structure. |
| **State** | RDF Triples tracking token positions and process variables. |
| **Gateways** | SPARQL `ASK` queries evaluated in real-time. |
| **Audit** | A dedicated Named Graph containing a stream of activity events. |

---

### 5. Getting Started

1. **Start Triplestore:** Ensure a SPARQL 1.1 compatible store is running.
2. **Import BPMN Models:** Convert BPMN 2.0 XML files to RDF using the bpmn2rdf converter:
   ```bash
   python bpmn2rdf.py myprocess.bpmn -o myprocess.ttl
   ```
   Or use programmatically:
   ```python
   from bpmn2rdf import BPMNToRDFConverter
   converter = BPMNToRDFConverter()
   graph = converter.parse_bpmn_to_graph("myprocess.bpmn")
   ```
3. **Bootstrap:** Run `python bootstrap.py` to upload process maps.
4. **Launch Engine:** Run `python app.py` to start the Flask API and Worker thread.
5. **Monitor:** Use the included SPARQL queries to view real-time performance and bottlenecks.

---

### 6. Process Mining & Analytics

The engine includes a built-in export utility to generate XES-compatible CSVs. This allows for immediate visualization of process heatmaps and performance analysis in standard mining tools.

---

### 7. Security Considerations

While SPEAR is designed as a lightweight BPMN orchestrator for process automation, it's important to understand the security implications when deploying in production environments.

#### 7.1 XML Parsing (XXE Vulnerability)

**Issue**: The BPMN-to-RDF converter uses Python's `xml.etree.ElementTree` to parse BPMN 2.0 XML files. By default, this parser is vulnerable to XML External Entity (XXE) attacks if deployed with untrusted input.

**Location**: `src/conversion/bpmn2rdf.py:50`
```python
tree = ET.parse(file_path)  # Vulnerable to XXE if untrusted
```

**Risk Level**: Medium
- **Impact**: If an attacker can upload malicious BPMN files, they could potentially read local files or perform server-side request forgery (SSRF).
- **Exploitability**: Requires ability to deploy processes with custom BPMN files.

**Mitigations**:
1. **Input Validation**: Only accept BPMN files from trusted sources
2. **Disable External Entities**: Use a safer XML parser configuration:
   ```python
   from lxml import etree
   parser = etree.XMLParser(no_network=True, dtd_validation=False)
   tree = etree.parse(file_path, parser)
   ```
3. **Content Security Policy**: Restrict file upload endpoints to authenticated/authorized users only

#### 7.2 CORS Configuration

**Issue**: The FastAPI application is configured with permissive CORS settings allowing all origins with credentials.

**Location**: `src/api/main.py:77-78`
```python
allow_origins=["*"],
allow_credentials=True,
```

**Risk Level**: Medium
- **Impact**: Could allow cross-origin attacks if the API is exposed on a public network
- **Exploitability**: Only exploitable if the API is accessible from browser-based applications

**Mitigations**:
1. **Restrict Origins**: Use environment variables for allowed origins:
   ```python
   from os import getenv
   allow_origins = getenv("ALLOWED_ORIGINS", "*").split(",")
   ```
2. **Production Configuration**: Set `ALLOWED_ORIGINS=https://yourdomain.com` in production
3. **Network Segmentation**: Deploy API on internal network, not publicly accessible

#### 7.3 Input Validation

**Issue**: API endpoints currently lack input validation for:
- BPMN XML content size
- Process variable lengths
- Request body sizes
- Topic handler names

**Risk Level**: Low-Medium
- **Impact**: Potential Denial of Service (DoS) with large/malformed payloads
- **Exploitability**: Requires network access to API endpoints

**Mitigations**:
1. **Add FastAPI Validation**:
   ```python
   from fastapi import FastAPI, Request
   from fastapi.middleware.trusthost import TrustHost
   from pydantic import Field, constr

   MAX_BPMN_SIZE = 10 * 1024 * 1024  # 10MB

   @app.post("/processes")
   async def deploy_process(request: Request):
       content_length = request.headers.get("content-length")
       if content_length and int(content_length) > MAX_BPMN_SIZE:
           raise HTTPException(status_code=413, detail="File too large")
   ```

2. **Add Pydantic Validation**:
   ```python
   from pydantic import constr

   class DeployProcessRequest(BaseModel):
       name: constr(min_length=1, max_length=255)
       bpmn_content: constr(max_length=10_000_000)
   ```

#### 7.4 Rate Limiting

**Issue**: No rate limiting is currently implemented on API endpoints.

**Risk Level**: Low
- **Impact**: API could be vulnerable to brute-force attacks or DoS
- **Exploitability**: Requires network access, easy to exploit

**Mitigations**:
1. **Use FastAPI-Limiter**:
   ```python
   from fastapi_limiter import Limiter
   from fastapi_limiter.depends import RateLimiter

   limiter = Limiter(key_func=get_remote_address)

   @app.post("/topics", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
   async def register_topic(request: Request):
       ...
   ```

2. **Reverse Proxy**: Configure rate limiting at nginx/Apache level

#### 7.5 Process Variables

**Issue**: Process variables are stored as RDF literals without type validation or sanitization.

**Risk Level**: Low
- **Impact**: Could lead to unexpected behavior but not direct security vulnerability
- **Exploitability**: Limited impact

**Best Practices**:
1. **Validate Variable Types**: Ensure variables match expected types before storing
2. **Sanitize User Input**: If variables contain user input, sanitize to prevent injection
3. **Limit Variable Size**: Set maximum size for variable values

#### 7.6 Topic Handler Security

**Issue**: Topic handlers are registered dynamically and execute arbitrary Python code.

**Risk Level**: High (if misconfigured)
- **Impact**: Malicious handlers could execute arbitrary code or access sensitive resources
- **Exploitability**: Requires access to topic registration endpoints

**Best Practices**:
1. **Restrict Handler Registration**: Only allow trusted users to register topic handlers
2. **Sandbox Handlers**: Run handlers in isolated environments (containers, separate processes)
3. **Audit Handlers**: Log all handler registrations and executions
4. **Validate Handler Functions**: Ensure handlers don't accept unsafe parameters

#### 7.7 RDF Graph Security

**Issue**: The RDF triples store (definitions, instances, audit) is not access-controlled.

**Risk Level**: Medium
- **Impact**: If the triplestore is compromised, all process data is exposed
- **Exploitability**: Requires access to triplestore endpoint

**Best Practices**:
1. **Network Segmentation**: Isolate the triplestore on internal network
2. **Authentication**: Enable authentication on the triplestore (Fuseki, GraphDB)
3. **Encryption**: Use TLS for all connections to the triplestore
4. **Named Graphs**: Use named graphs for logical separation of data

#### 7.8 Audit Log Integrity

**Issue**: Audit logs are stored as RDF triples that could be modified.

**Risk Level**: Low
- **Impact**: Audit trail could be tampered with to hide malicious activity
- **Exploitability**: Requires access to the RDF store with write permissions

**Best Practices**:
1. **Read-Only Audit Store**: Use separate, immutable storage for audit logs
2. **Digital Signatures**: Sign audit entries to detect tampering
3. **Separate Storage**: Store audit logs in a separate system (database, SIEM)

---

### 8. Deployment Recommendations

#### 8.1 Development vs Production

| Component | Development | Production |
|-----------|-------------|------------|
| **CORS** | `allow_origins=["*"]` | Restrict to specific domains |
| **XML Parser** | `ElementTree` | Use `lxml` with XXE protection |
| **Rate Limiting** | Disabled | Enabled (100 req/min) |
| **Input Validation** | Minimal | Strict (Pydantic models) |
| **Authentication** | None | OAuth2/JWT |
| **Triplestore** | Local Fuseki | Secured Fuseki/GraphDB |
| **Network** | localhost | Internal network only |

#### 8.2 Security Checklist

- [ ] Restrict CORS origins for production deployment
- [ ] Implement XXE protection on XML parsing
- [ ] Add input validation and size limits on API endpoints
- [ ] Configure rate limiting on all API endpoints
- [ ] Enable authentication on API endpoints
- [ ] Enable authentication on triplestore
- [ ] Use TLS for all connections (API, triplestore)
- [ ] Restrict topic handler registration to admins
- [ ] Network segment all internal services
- [ ] Regular security audits and updates
- [ ] Monitor logs for suspicious activity

#### 8.3 Environment Variables for Production

```bash
# CORS Configuration
ALLOWED_ORIGINS=https://frontend.example.com,https://admin.example.com

# API Security
API_KEY=your-secret-api-key
AUTH_ENABLED=true

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60

# Triplestore
SPARQL_ENDPOINT=https://triplestore.example.com/query
SPARQL_UPDATE=https://triplestore.example.com/update
SPARQL_USER=admin
SPARQL_PASSWORD=secure-password

# Logging
LOG_LEVEL=WARNING
AUDIT_LOG_ENDPOINT=https://audit.example.com/api
```

---

### 9. Reporting Security Issues

If you discover a security vulnerability in SPEAR, please report it responsibly:

1. **Do NOT** disclose the vulnerability publicly
2. **Do NOT** create issues or pull requests for security vulnerabilities
3. **Email** security concerns to the development team
4. **Provide** detailed information about the vulnerability

We appreciate responsible disclosure and will respond promptly to security reports.

---

**Note**: This document is for informational purposes only. Always conduct a thorough security assessment before deploying in production environments.