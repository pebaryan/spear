from .scheduler_check_due import make_handler as make_scheduler_check_due
from .scheduler_spawn_cycle import make_handler as make_scheduler_spawn_cycle
from .observe_state import make_handler as make_observe_state
from .web_search import make_handler as make_web_search
from .summarize import make_handler as make_summarize
from .decide_next import handle as decide_next
from .write_memory import make_handler as make_write_memory
from .reflect import make_handler as make_reflect
from .plan_query import make_handler as make_plan_query
from .answer_memory import make_handler as make_answer_memory
from .ingest_info import make_handler as make_ingest_info
from .schedule_next import make_handler as make_schedule_next


def build_handlers(engine, memory_graph):
    return {
        "scheduler_check_due": make_scheduler_check_due(memory_graph),
        "scheduler_spawn_cycle": make_scheduler_spawn_cycle(engine),
        "observe_state": make_observe_state(memory_graph),
        "web_search": make_web_search(memory_graph),
        "summarize": make_summarize(memory_graph),
        "decide_next": decide_next,
        "write_memory": make_write_memory(memory_graph),
        "reflect": make_reflect(memory_graph),
        "plan_query": make_plan_query(memory_graph),
        "answer_memory": make_answer_memory(memory_graph),
        "ingest_info": make_ingest_info(memory_graph),
        "schedule_next": make_schedule_next(memory_graph),
    }
