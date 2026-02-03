import json
import os

from rdflib import Literal, RDF, URIRef, XSD

from .common import MEM, SRC, brave_search, get_agent_uri, log, now_utc


def make_handler(memory_graph):
    def handle(context):
        log("web_search: starting.")
        query = context.get_variable("query")
        if not query:
            log("web_search: no query set.")
            return

        api_key = os.getenv("BRAVE_API_KEY")
        results = []
        if api_key:
            try:
                results = brave_search(str(query), api_key)
            except Exception as exc:
                log(f"web_search: failed: {exc}")
                results = [{"title": "Brave search failed", "snippet": str(exc)}]
        else:
            log("web_search: BRAVE_API_KEY missing.")
            results = [{"title": "Brave API key missing", "snippet": "Set BRAVE_API_KEY"}]

        agent_uri = get_agent_uri(memory_graph, context)
        if agent_uri is None:
            return

        query_snapshot = MEM[f"QuerySnapshot_{int(now_utc().timestamp())}"]
        memory_graph.add((query_snapshot, RDF.type, MEM.QuerySnapshot))
        memory_graph.add((query_snapshot, MEM.content, Literal(str(query))))
        memory_graph.add(
            (query_snapshot, MEM.createdAt, Literal(now_utc(), datatype=XSD.dateTime))
        )
        memory_graph.add((agent_uri, MEM.hasQuerySnapshot, query_snapshot))
        context.set_variable("query_snapshot", str(query_snapshot))

        context.set_variable("search_results", json.dumps(results))

        result_nodes = []
        for idx, item in enumerate(results):
            node = SRC[f"WebResult_{int(now_utc().timestamp())}_{idx}"]
            memory_graph.add((node, RDF.type, SRC.WebResult))
            memory_graph.add((node, SRC.url, Literal(item.get("url", ""))))
            memory_graph.add((node, SRC.title, Literal(item.get("title", ""))))
            memory_graph.add((node, SRC.snippet, Literal(item.get("snippet", ""))))
            memory_graph.add(
                (node, SRC.fetchedAt, Literal(now_utc(), datatype=XSD.dateTime))
            )
            memory_graph.add((query_snapshot, MEM.hasResult, node))
            memory_graph.add((node, MEM.fromQuery, query_snapshot))
            result_nodes.append(str(node))

        if result_nodes:
            memory_graph.remove((agent_uri, SRC.latestResult, None))
            memory_graph.add((agent_uri, SRC.latestResult, URIRef(result_nodes[-1])))
        context.set_variable("result_nodes", json.dumps(result_nodes))

    return handle
