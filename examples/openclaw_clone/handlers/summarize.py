import json

from rdflib import Literal, RDF, URIRef, XSD

from .common import MEM, get_agent_uri, llm_summary, log, now_utc


def make_handler(memory_graph):
    def handle(context):
        log("summarize: starting.")
        raw = context.get_variable("search_results")
        if not raw:
            log("summarize: no search results.")
            return

        try:
            results = json.loads(str(raw))
        except Exception:
            results = []

        prompt = "\n".join(
            f"- {item.get('title', '')}: {item.get('snippet', '')}" for item in results
        )
        summary = llm_summary(prompt)
        context.set_variable("summary", summary)

        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            return

        node = MEM[f"Summary_{int(now_utc().timestamp())}"]
        memory_graph.add((node, RDF.type, MEM.Summary))
        memory_graph.add((node, MEM.content, Literal(summary)))
        memory_graph.add(
            (node, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.remove((agent_uri, MEM.latestSummary, None))
        memory_graph.add((agent_uri, MEM.latestSummary, node))

        query_snapshot = context.get_variable("query_snapshot")
        if query_snapshot:
            qsnap = URIRef(str(query_snapshot))
            memory_graph.add((qsnap, MEM.hasSummary, node))
            memory_graph.add((node, MEM.fromQuery, qsnap))

        result_nodes_raw = context.get_variable("result_nodes")
        if result_nodes_raw:
            try:
                result_nodes = json.loads(str(result_nodes_raw))
            except Exception:
                result_nodes = []
            for result_uri in result_nodes:
                memory_graph.add((node, MEM.basedOnResult, URIRef(result_uri)))

        context.set_variable("summary_node", str(node))

    return handle
