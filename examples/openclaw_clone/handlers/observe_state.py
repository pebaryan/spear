from rdflib import Literal

from .common import AGT, get_agent_uri, log, normalize_goal


def make_handler(memory_graph):
    def handle(context):
        log("observe_state: loading agent goal into variables.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("observe_state: no agent found.")
            return

        goal = memory_graph.value(agent_uri, AGT.currentGoal)
        if goal:
            normalized = normalize_goal(str(goal))
            if normalized and normalized != str(goal):
                memory_graph.set((agent_uri, AGT.currentGoal, Literal(normalized)))
                goal = normalized
            context.set_variable("goal", str(goal))
            context.set_variable("query", str(goal))

    return handle
