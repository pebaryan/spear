import json
from rdflib import URIRef

from .common import AGT, log


def make_handler(engine):
    def scheduler_spawn_cycle(context):
        log("Scheduler: spawning agent cycles.")
        graph = context.g
        due_agents_raw = context.get_variable("due_agents")
        if not due_agents_raw:
            log("Scheduler: no due agents.")
            return

        try:
            due_agents = json.loads(str(due_agents_raw))
        except Exception:
            due_agents = []

        if not due_agents:
            log("Scheduler: no due agents after parsing.")
            return

        cycle_process_uri = graph.value(AGT.Agent_1, AGT.cycleProcess)
        if not cycle_process_uri:
            cycle_process_uri = URIRef("http://example.org/bpmn/AgentCycleProcess")

        for agent_uri in due_agents:
            log(f"Scheduler: starting AgentCycleProcess for {agent_uri}.")
            engine.start_process_instance(
                str(cycle_process_uri),
                initial_variables={"agent_uri": agent_uri},
                start_event_id="StartEvent_Cycle",
            )

    return scheduler_spawn_cycle
