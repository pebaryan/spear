from rdflib import Literal, RDF, XSD

from .common import AGT, MEM, get_agent_uri, llm_summary, log, now_utc


def make_handler(memory_graph):
    def handle(context):
        log("plan_query: starting.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("plan_query: no agent found.")
            return

        goal = memory_graph.value(agent_uri, AGT.currentGoal)
        goal_text = context.get_variable("goal") or goal
        if goal_text is None:
            return
        goal_text = str(goal_text)

        prompt = (
            "Convert the agent goal into a concise, specific web search query. "
            "Avoid human self-help phrasing. Keep it under 12 words. "
            "Return only the query text.\n\n"
            f"Goal: {goal_text}\n"
        )

        query = llm_summary(prompt).strip().strip('"')
        if not query:
            return

        context.set_variable("query", query)

        node = MEM[f"PlannedQuery_{int(now_utc().timestamp())}"]
        memory_graph.add((node, RDF.type, MEM.QueryPlan))
        memory_graph.add((node, MEM.content, Literal(query)))
        memory_graph.add((node, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime)))
        memory_graph.add((agent_uri, MEM.hasQueryPlan, node))

    return handle
