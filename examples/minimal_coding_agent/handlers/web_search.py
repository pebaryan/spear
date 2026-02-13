"""Handler that performs live web search for debugging context."""

from .common import WebSearchTool, literal_to_text, serialize_search_results


def handle(context) -> None:
    query = literal_to_text(context.get_variable("search_query"))
    tool = WebSearchTool()
    results = tool.search(query, max_results=5)
    context.set_variable("search_results_json", serialize_search_results(results))
