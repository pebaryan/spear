# PROV-O Mapping Draft for SPEAR Runtime Data

This note defines a practical mapping profile from current SPEAR runtime RDF
artifacts to PROV-O concepts for conference discussion and pilot alignment.

## Mapping Intent
- Keep existing SPEAR namespaces unchanged for runtime compatibility.
- Add parallel PROV-O assertions as an interoperability layer.
- Enable provenance queries that can be shared across tools.

## Proposed Mapping Table
1. `log:Event` -> `prov:Activity`
2. `inst:ProcessInstance` -> `prov:Activity` (long-running process execution)
3. `task:UserTask` -> `prov:Activity` (human-centric sub-activity)
4. `inst:hasVariable` resources -> `prov:Entity`
5. `log:user` literal -> `prov:wasAssociatedWith` (IRI form recommended)
6. `log:timestamp` -> `prov:startedAtTime`/`prov:endedAtTime` (event-model dependent)
7. `log:instance` -> `prov:wasInformedBy` or `prov:qualifiedAssociation` context

## Example Triple Sketch
```turtle
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix log: <http://example.org/audit/> .
@prefix inst: <http://example.org/instance/> .

log:event_123 a log:Event, prov:Activity ;
  log:eventType "SERVICE_TASK" ;
  log:instance inst:abc ;
  prov:wasAssociatedWith <http://example.org/agent/system> .
```

## Open Decisions
1. Should a full process instance be modeled as `prov:Activity` or `prov:Bundle` + activity chain?
2. Should variable changes be represented as immutable `prov:Entity` versions?
3. Should task assignment and completion be modeled with qualified PROV relations?

## Conference Statement
This mapping is a compatibility profile in progress, not a finalized ontology.
The short-term target is reproducible query interoperability across SPEAR and
PROV-aware analytics tooling.
