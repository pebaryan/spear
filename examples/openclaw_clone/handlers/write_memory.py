from rdflib import Literal, RDF, XSD

from .common import MEM, get_agent_uri, log, now_utc


def make_handler(memory_graph):
    def handle(context):
        log("write_memory: starting.")
        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            log("write_memory: no agent found.")
            return

        summary = context.get_variable("summary")
        if not summary:
            return

        note = MEM[f"Note_{int(now_utc().timestamp())}"]
        memory_graph.add((note, RDF.type, MEM.Note))
        memory_graph.add((note, MEM.content, Literal(str(summary))))
        memory_graph.add(
            (note, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.add((agent_uri, MEM.hasNote, note))

    return handle
