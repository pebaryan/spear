from rdflib import Literal, RDF, XSD

from .common import AGT, MEM, get_agent_uri, log, now_utc


def make_handler(memory_graph):
    def handle(context):
        log("ingest_info: starting.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("ingest_info: no agent found.")
            return

        user_info = context.get_variable("user_info")
        if not user_info:
            log("ingest_info: no user_info set.")
            return

        info_text = str(user_info)
        info_node = MEM[f"UserInfo_{int(now_utc().timestamp())}"]
        memory_graph.add((info_node, RDF.type, MEM.UserInfo))
        memory_graph.add((info_node, MEM.content, Literal(info_text)))
        memory_graph.add(
            (info_node, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.add((agent_uri, MEM.hasNote, info_node))

        # Capture baseline goal if missing
        baseline_goal = memory_graph.value(agent_uri, AGT.baselineGoal)
        if baseline_goal is None:
            current_goal = memory_graph.value(agent_uri, AGT.currentGoal)
            if current_goal:
                memory_graph.add((agent_uri, AGT.baselineGoal, current_goal))
                baseline_goal = current_goal

        # If user provided identity, store it and suggest goal reset.
        lowered = info_text.lower()
        if "identity" in lowered or "i am" in lowered or "i'm" in lowered:
            memory_graph.set((agent_uri, AGT.identity, Literal(info_text)))
            if baseline_goal:
                context.set_variable("goal_suggestion", str(baseline_goal))
            else:
                context.set_variable(
                    "goal_suggestion",
                    "Continue agent self-improvement based on current memory.",
                )
            context.set_variable("needs_goal_update", True)

        # Treat user info as the summary so downstream steps can proceed.
        context.set_variable("summary", info_text)

    return handle
