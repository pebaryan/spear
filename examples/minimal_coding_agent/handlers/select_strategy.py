"""Handler that selects fix strategy based on RDF query results."""

from .common import TARGET_DIR, PythonTestTool


def handle(context) -> None:
    """Select the fix strategy based on error analysis from RDF."""
    error_type = context.get_variable("error_type")
    chosen_strategy = context.get_variable("chosen_strategy")
    attempt = context.get_variable("retry_count")
    relevant_skills = context.get_variable("relevant_skills")

    if error_type == "None" or error_type is None:
        context.set_variable("strategy_result", "no_fix_needed")
        context.set_variable("fix_approach", "none")
        return

    if chosen_strategy == "llm_fix":
        approach = "Use LLM to analyze error and generate fix"
    elif chosen_strategy == "different_approach":
        approach = "Use different fix strategy based on skill patterns"
    elif chosen_strategy == "escalate":
        approach = "Escalate - try more aggressive fixes or ask for help"
    else:
        approach = "Standard LLM fix attempt"

    context.set_variable("strategy_result", chosen_strategy)
    context.set_variable("fix_approach", approach)

    context.set_variable(
        "strategy_rationale",
        f"Error: {error_type}, Attempt: {attempt}, Strategy: {chosen_strategy}, Skills: {relevant_skills[:100] if relevant_skills else 'none'}",
    )
