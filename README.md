
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
2. **Bootstrap:** Run `python bootstrap.py` to upload process maps.
3. **Launch Engine:** Run `python app.py` to start the Flask API and Worker thread.
4. **Monitor:** Use the included SPARQL queries to view real-time performance and bottlenecks.

---

### 6. Process Mining & Analytics

The engine includes a built-in export utility to generate XES-compatible CSVs. This allows for immediate visualization of process heatmaps and performance analysis in standard mining tools.

---

### Next Step

