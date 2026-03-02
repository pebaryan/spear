"""Handler that increments the retry counter for BPMN loop control."""

from rdflib import XSD


def handle(context) -> None:
    current = context.get_variable("retry_count")
    if current is None:
        current = 0
    else:
        try:
            current = int(current)
        except (ValueError, TypeError):
            current = 0

    new_count = current + 1
    context.set_variable("retry_count", str(new_count), datatype=XSD.integer)
