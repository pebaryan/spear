# SPEAR Pitch Deck Speaker Notes (Semantic Web Audience)

## Timing
Target: 10-12 minutes + Q&A.

## Slide-by-Slide Notes
1. **Title / Executable Knowledge Graphs**
Talk track: "This is not BPMN visualization. This is BPMN execution with RDF-native runtime state and SPARQL introspection."

2. **Research Problem**
Talk track: "Process engines handle control flow well, but semantic explainability is often an afterthought."

3. **Approach**
Talk track: "SPEAR persists definitions + runtime artifacts as RDF and keeps them queryable throughout execution."

4. **Standards Fit**
Talk track: "Current implementation is RDF/SPARQL-native. PROV-O and SHACL alignment is explicit roadmap work, not hand-wavy future language."

5. **SPARQL View**
Talk track: "These are representative diagnostic queries you can run live against runtime state, not synthetic static examples."

6. **Use Cases (1-3)**
Talk track: "Numbers are pilot target bands with assumptions shown. They are not guarantees."

7. **Pilot Plan**
Talk track: "We evaluate against baseline with median/p90 and transparent sample-size reporting."

8. **Evidence Protocol**
Talk track: "Claims are accepted only if query-backed and reproducible under controlled pilot conditions."

9. **Limitations**
Talk track: "Current runtime is file-backed RDF in this repo and semantic profiles are still formalizing."

10. **Demo Roadmap**
Talk track: "We have a concrete runbook and deterministic demo kit in `examples/conference_demo/`."

11. **Collaboration Close**
Talk track: "We're looking for collaborators with real workflow datasets where explainability and governance matter."

## Likely Questions And Suggested Responses
1. **Q: What is semantically novel here?**
A: "The novelty is runtime BPMN state represented as queryable RDF with immediate SPARQL introspection; we are formalizing PROV-O/SHACL alignment as part of the next phase."

2. **Q: Why not just logs + SQL?**
A: "Logs are event-centric and fragmented. RDF enables cross-artifact linking and standards-based graph queries over process, variables, tasks, and audit in one model."

3. **Q: Is this production-ready?**
A: "It is maturing quickly and has strong automated test coverage. For production scale we still need triplestore-first deployment and broader benchmark publication."

4. **Q: Are KPI claims real?**
A: "They are pilot target bands with assumptions. We intentionally avoid claiming universal gains before controlled measurement."

5. **Q: How do you validate data quality?**
A: "SHACL sanity shapes are included in the demo kit and can be expanded per domain."

## Demo Tie-In
Before Q&A, mention:
- `python examples/conference_demo/demo_runner.py --reset`
- query pack in `examples/conference_demo/queries/`
- PROV/SHACL artifacts in `examples/conference_demo/semantic/`
