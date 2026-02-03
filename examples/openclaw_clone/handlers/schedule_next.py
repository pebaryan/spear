from datetime import timedelta

from rdflib import Literal, RDF, XSD

from .common import AGT, MEM, get_agent_uri, get_cadence_seconds, log, now_utc


def make_handler(memory_graph):
    def handle(context):
        log("schedule_next: starting.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("schedule_next: no agent found.")
            return

        cadence = get_cadence_seconds(memory_graph, agent_uri)
        now = now_utc()
        next_run = now + timedelta(seconds=cadence)

        goal = memory_graph.value(agent_uri, AGT.currentGoal)
        if goal:
            snapshot = MEM[f"GoalSnapshot_{int(now.timestamp())}"]
            memory_graph.add((snapshot, RDF.type, MEM.GoalSnapshot))
            memory_graph.add((snapshot, MEM.content, Literal(str(goal))))
            memory_graph.add(
                (snapshot, MEM.createdAt, Literal(now, datatype=XSD.dateTime))
            )
            memory_graph.add((agent_uri, MEM.hasGoalSnapshot, snapshot))

        memory_graph.set((agent_uri, AGT.lastRunAt, Literal(now, datatype=XSD.dateTime)))
        memory_graph.set(
            (agent_uri, AGT.nextRunAt, Literal(next_run, datatype=XSD.dateTime))
        )

    return handle
