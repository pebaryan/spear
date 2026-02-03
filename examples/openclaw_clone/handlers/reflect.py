import json

from rdflib import Literal, RDF, URIRef, XSD

from .common import (
    AGT,
    MEM,
    get_agent_uri,
    llm_summary,
    log,
    now_utc,
    normalize_goal,
    strip_json_fence,
)


def make_handler(memory_graph):
    def handle(context):
        log("reflect: starting.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("reflect: no agent found.")
            return

        # Only alter the goal if memory-only answer was insufficient.
        needs_goal_update = context.get_variable("needs_goal_update")
        if needs_goal_update is not None and not bool(needs_goal_update):
            log("reflect: answer sufficient; skipping goal update.")
            return

        summary = context.get_variable("summary")
        last_goal = memory_graph.value(agent_uri, AGT.currentGoal)
        user_question = context.get_variable("user_question")
        identity_known = context.get_variable("identity_known")

        if user_question:
            reflection_input = (
                "The agent could not fully answer the user's question from memory. "
                "Set a refined goal that focuses on answering the question. "
                "Return ONLY JSON with keys critique, new_goal. "
                "The new_goal must explicitly mention answering the user's question.\n\n"
                f"User question: {user_question}\n"
                f"Last goal: {last_goal}\n"
                f"Memory answer: {summary}\n"
            )
        else:
            reflection_input = (
                "You are an autonomous agent improving itself. "
                "Given the last summary, propose: (1) a critique, "
                "(2) a refined goal. "
                "Return ONLY JSON with keys critique, new_goal.\n\n"
                f"Last goal: {last_goal}\n"
                f"Summary: {summary}\n"
            )

        reflection_text = llm_summary(reflection_input)
        cleaned_text = strip_json_fence(reflection_text)
        critique = ""
        new_goal = ""
        try:
            parsed = json.loads(cleaned_text)
            critique = parsed.get("critique", "")
            new_goal = parsed.get("new_goal", "")
        except Exception:
            # Retry with a stricter instruction if the model didn't return JSON.
            retry_input = (
                "Return ONLY JSON with keys critique, new_goal. "
                "No prose.\n\n"
                f"User question: {user_question}\n"
                f"Last goal: {last_goal}\n"
                f"Summary: {summary}\n"
            )
            retry_text = llm_summary(retry_input)
            reflection_text = retry_text
            cleaned_retry = strip_json_fence(retry_text)
            try:
                parsed = json.loads(cleaned_retry)
                critique = parsed.get("critique", "")
                new_goal = parsed.get("new_goal", "")
            except Exception:
                # Fallback: extract labeled lines if present.
                for line in reflection_text.splitlines():
                    lower = line.lower().strip()
                    if lower.startswith("critique"):
                        critique = line.split(":", 1)[-1].strip()
                    elif lower.startswith("new_goal") or lower.startswith("new goal"):
                        new_goal = line.split(":", 1)[-1].strip()
                if not critique:
                    critique = reflection_text

        note = MEM[f"Reflection_{int(now_utc().timestamp())}"]
        memory_graph.add((note, RDF.type, MEM.Reflection))
        memory_graph.add((note, MEM.content, Literal(reflection_text)))
        if critique:
            memory_graph.add((note, MEM.critique, Literal(critique)))
        if new_goal:
            memory_graph.add((note, MEM.newGoal, Literal(new_goal)))
        memory_graph.add(
            (note, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.add((agent_uri, MEM.hasNote, note))

        summary_node = context.get_variable("summary_node")
        if summary_node:
            summary_uri = URIRef(str(summary_node))
            memory_graph.add((note, MEM.basedOnSummary, summary_uri))
            memory_graph.add((summary_uri, MEM.reflectedBy, note))

        if new_goal:
            if user_question and str(user_question) not in str(new_goal):
                new_goal = f"Answer the user's question: {user_question}"
            if user_question and identity_known is False:
                new_goal = (
                    f"Determine the agent's identity from configuration or stored memory "
                    f"to answer: {user_question}"
                )
            new_goal = normalize_goal(new_goal)
            memory_graph.set((agent_uri, AGT.currentGoal, Literal(new_goal)))
            memory_graph.add((note, MEM.updatedGoal, Literal(new_goal)))
            context.set_variable("goal", new_goal)
        # Query planning happens in a separate handler.

    return handle
