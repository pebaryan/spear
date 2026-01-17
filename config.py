# SPEAR Configuration Module
# This file contains configuration settings for the SPEAR BPMN engine

# SPARQL Query Endpoint URL
# This is the endpoint for the RDF triplestore used to store process definitions and instances
QUERY_ENDPOINT = "http://localhost:7200/repositories/spear"

# Optional: Set to True to enable debug logging
DEBUG = False

# Optional: Default BPMN namespace
BPMN_NAMESPACE = "http://example.org/bpmn/"

# Optional: Default process instance namespace
INSTANCE_NAMESPACE = "http://example.org/instance/"

# Optional: Default variable namespace
VARIABLE_NAMESPACE = "http://example.org/variables/"

# Optional: Default audit log namespace
AUDIT_NAMESPACE = "http://example.org/audit/"
