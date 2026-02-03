import json

from rdflib import Literal, RDF, XSD

from .common import AGT, MEM, get_agent_uri, llm_summary, log, now_utc, strip_json_fence


def make_handler(memory_graph):
    def handle(context):
        log("answer_memory: starting.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("answer_memory: no agent found.")
            return

        question = context.get_variable("user_question")
        if not question:
            log("answer_memory: no user question set.")
            return

        question_text = str(question).lower()
        identity_known = False
        for _, pred, obj in memory_graph.triples((agent_uri, None, None)):
            pred_str = str(pred).lower()
            if pred_str.endswith("identity") or pred_str.endswith("name"):
                if obj:
                    identity_known = True
                    break
        context.set_variable("identity_known", bool(identity_known))

        goal = memory_graph.value(agent_uri, AGT.currentGoal)
        summaries = []
        for node, _, _ in memory_graph.triples((None, RDF.type, MEM.Summary)):
            created = memory_graph.value(node, MEM.createdAt)
            content = memory_graph.value(node, MEM.content)
            summaries.append((created, content))
        summaries.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)

        reflections = []
        for node, _, _ in memory_graph.triples((None, RDF.type, MEM.Reflection)):
            created = memory_graph.value(node, MEM.createdAt)
            content = memory_graph.value(node, MEM.content)
            reflections.append((created, content))
        reflections.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)

        memory_context = []
        if goal:
            memory_context.append(f"Current goal: {goal}")
        if summaries:
            memory_context.append("Recent summaries:")
            for created, content in summaries[:5]:
                memory_context.append(f"- {created} {content}")
        if reflections:
            memory_context.append("Recent reflections:")
            for created, content in reflections[:5]:
                memory_context.append(f"- {created} {content}")

        prompt = (
            "Answer the user's question using only the agent's memory. "
            "Do NOT invent identity details. If memory is insufficient, say so "
            "and suggest what to search for next.\n\n"
            f"Memory:\n{chr(10).join(memory_context)}\n\n"
            f"User question: {question}\n"
        )

        answer = llm_summary(prompt)
        context.set_variable("summary", answer)
        context.set_variable("answer_text", answer)

        if not identity_known and (
            "who are you" in question_text
            or "your identity" in question_text
            or "what are you" in question_text
        ):
            answer = (
                "I don't have identity details in memory. "
                "I can only describe my current goals and stored context."
            )
            context.set_variable("summary", answer)
            context.set_variable("answer_text", answer)
            context.set_variable("needs_goal_update", True)

        classifier_prompt = (
            "Given the user's question and the agent's answer, decide if the "
            "answer is sufficient. Return ONLY JSON: {\"sufficient\": true|false}.\n\n"
            f"Question: {question}\n"
            f"Answer: {answer}\n"
        )
        classifier_text = llm_summary(classifier_prompt)
        cleaned = strip_json_fence(classifier_text)
        sufficient = None
        insufficiency_phrases = [
            "i don't have",
            "i do not have",
            "insufficient",
            "not enough information",
            "cannot answer",
            "unable to answer",
        ]
        try:
            parsed = json.loads(cleaned)
            sufficient = bool(parsed.get("sufficient"))
        except Exception:
            lowered = answer.lower()
            sufficient = not any(phrase in lowered for phrase in insufficiency_phrases)

        if sufficient:
            lowered = answer.lower()
            if any(phrase in lowered for phrase in insufficiency_phrases):
                sufficient = False

        if context.get_variable("needs_goal_update") is None:
            context.set_variable("needs_goal_update", not sufficient)

        q_node = MEM[f"UserQuestion_{int(now_utc().timestamp())}"]
        a_node = MEM[f"AgentAnswer_{int(now_utc().timestamp())}"]
        memory_graph.add((q_node, RDF.type, MEM.UserQuestion))
        memory_graph.add((q_node, MEM.content, Literal(str(question))))
        memory_graph.add(
            (q_node, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.add((a_node, RDF.type, MEM.AgentAnswer))
        memory_graph.add((a_node, MEM.content, Literal(str(answer))))
        memory_graph.add(
            (a_node, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.add((agent_uri, MEM.askedQuestion, q_node))
        memory_graph.add((agent_uri, MEM.answeredBy, a_node))
        memory_graph.add((q_node, MEM.answer, a_node))

        answer_node = MEM[f"Summary_{int(now_utc().timestamp())}"]
        memory_graph.add((answer_node, RDF.type, MEM.Summary))
        memory_graph.add((answer_node, MEM.content, Literal(str(answer))))
        memory_graph.add(
            (answer_node, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.remove((agent_uri, MEM.latestSummary, None))
        memory_graph.add((agent_uri, MEM.latestSummary, answer_node))

    return handle
