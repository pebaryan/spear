from .common import log


def handle(context):
    log("decide_next: starting.")
    summary = context.get_variable("summary")
    decision = "research_more"
    if summary:
        decision = "review_and_store"
    context.set_variable("decision", decision)
