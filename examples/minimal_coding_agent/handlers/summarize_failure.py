"""Handler that summarizes pytest failures and prepares a web query."""

from .common import build_failure_summary, build_search_query, literal_to_text


def handle(context) -> None:
    task = literal_to_text(context.get_variable("task"))
    before_output = literal_to_text(context.get_variable("before_output"))
    summary = build_failure_summary(before_output)
    query = build_search_query(task, summary)
    context.set_variable("failure_summary", summary)
    context.set_variable("search_query", query)
