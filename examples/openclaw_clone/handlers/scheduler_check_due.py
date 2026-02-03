import json

from .common import AGT, log, now_utc


def make_handler(memory_graph):
    def scheduler_check_due(context):
        log("Scheduler: checking due agents.")
        now = now_utc()
        due_agents = []
        for agent, _, next_run in memory_graph.triples((None, AGT.nextRunAt, None)):
            try:
                next_dt = next_run.toPython()
            except Exception:
                continue
            if next_dt <= now:
                due_agents.append(str(agent))

        context.set_variable("due_agents", json.dumps(due_agents))

    return scheduler_check_due
