"""Execute paper-aligned SPARQL templates against SPEAR provenance output."""
import argparse
import sys
from pathlib import Path
from rdflib import Graph


BASE = Path(__file__).resolve().parent
DEFAULT_GRAPH = BASE / "spear-demo-prov.ttl"
QUERY_DIR = BASE / "queries"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run why/why-not/impact SPARQL templates on SPEAR demo output."
    )
    parser.add_argument(
        "--graph",
        default=str(DEFAULT_GRAPH),
        help=f"Path to Turtle provenance graph (default: {DEFAULT_GRAPH})",
    )
    parser.add_argument(
        "--run-uri",
        default=None,
        help="Process instance URI to bind as $runUri (auto-detected if omitted).",
    )
    parser.add_argument(
        "--action-uri",
        default=None,
        help="Seed action URI to bind as $actionUri for impact (auto-detected edit action if omitted).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of rows to print per query.",
    )
    return parser.parse_args()


def load_graph(path: Path) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def quote_uri(uri: str) -> str:
    return f"<{uri}>"


def read_query(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def detect_latest_run_uri(graph: Graph):
    q = """
    PREFIX ag: <http://example.org/agent#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT ?run ?t WHERE {
      ?a a ag:Action ;
         prov:wasAssociatedWith ?run ;
         prov:startedAtTime ?t .
    } ORDER BY DESC(?t) LIMIT 1
    """
    rows = list(graph.query(q))
    return str(rows[0][0]) if rows else None


def detect_latest_edit_action_uri(graph: Graph, run_uri: str):
    q = f"""
    PREFIX ag: <http://example.org/agent#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT ?a ?t WHERE {{
      ?a a ag:Action ;
         ag:tool "edit" ;
         prov:wasAssociatedWith {quote_uri(run_uri)} ;
         prov:startedAtTime ?t .
    }} ORDER BY DESC(?t) LIMIT 1
    """
    rows = list(graph.query(q))
    return str(rows[0][0]) if rows else None


def bind_template(query: str, run_uri: str = None, action_uri: str = None) -> str:
    if run_uri:
        query = query.replace("$runUri", quote_uri(run_uri))
    if action_uri:
        query = query.replace("$actionUri", quote_uri(action_uri))
    return query


def format_term(term) -> str:
    return str(term)


def run_named_query(graph: Graph, name: str, query: str, limit: int):
    result = graph.query(query)
    var_names = [str(v) for v in result.vars]
    rows = list(result)
    print(f"\n== {name} ({len(rows)} rows)")
    if not rows:
        print("(no rows)")
        return
    print("columns:", ", ".join(var_names))
    for idx, row in enumerate(rows[:limit], start=1):
        values = [format_term(row[i]) for i in range(len(var_names))]
        print(f"{idx:02d}: " + " | ".join(values))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more rows")


def main():
    args = parse_args()
    graph_path = Path(args.graph).expanduser().resolve()
    if not graph_path.exists():
        print(f"Graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)

    g = load_graph(graph_path)
    run_uri = args.run_uri or detect_latest_run_uri(g)
    if not run_uri:
        print("Could not auto-detect run URI from graph.", file=sys.stderr)
        sys.exit(1)

    action_uri = args.action_uri or detect_latest_edit_action_uri(g, run_uri)
    if not action_uri:
        print("Could not auto-detect edit action URI for impact query.", file=sys.stderr)
        sys.exit(1)

    why_q = bind_template(read_query(QUERY_DIR / "why.sparql"), run_uri=run_uri)
    why_not_q = bind_template(read_query(QUERY_DIR / "why-not.sparql"), run_uri=run_uri)
    impact_q = bind_template(
        read_query(QUERY_DIR / "impact.sparql"), action_uri=action_uri
    )

    print(f"Graph: {graph_path}")
    print(f"Run URI: {run_uri}")
    print(f"Impact seed action URI: {action_uri}")

    run_named_query(g, "why", why_q, args.limit)
    run_named_query(g, "why-not", why_not_q, args.limit)
    run_named_query(g, "impact", impact_q, args.limit)


if __name__ == "__main__":
    main()
