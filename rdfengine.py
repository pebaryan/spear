import operator
from rdflib import Graph, Namespace, RDF, Literal, XSD

BPMN = Namespace("http://example.org/bpmn/")

class RDFEngine:
    def __init__(self, graph):
        self.g = graph

    def get_next_step(self, current_node_uri):
        # SPARQL query to find the next node
        query = f"""
        SELECT ?next WHERE {{
            <{current_node_uri}> <http://example.org/bpmn/next> ?next .
        }}
        """
        results = self.g.query(query)
        for row in results:
            return row.next
        return None

    def execute_instance(self, start_node):
        current = start_node
        while current:
            print(f"Executing: {current}")
            
            # Logic: If it's a service task, run code...
            # If it's a user task, break and save state...
            
            current = self.get_next_step(current)
            if current == PROC.EndNode:
                print("Process Finished.")
                break

class ProcessContext:
    def __init__(self, graph, instance_uri):
        self.g = graph
        self.inst = instance_uri
        self.VAR = Namespace("http://example.org/variables/")

    def set_variable(self, name, value, datatype=None):
        # Remove old value first (Variables can change)
        self.g.remove((self.inst, self.VAR[name], None))
        # Add new value
        self.g.add((self.inst, self.VAR[name], Literal(value, datatype=datatype)))

    def get_variable(self, name):
        return self.g.value(self.inst, self.VAR[name])

# Map string operators to Python functions
OPERATORS = {
    ">": operator.gt,
    "<=": operator.le,
    "==": operator.eq
}

def evaluate_condition(graph, flow_uri, instance_data):
    # Find the condition blank node for this flow
    condition = graph.value(flow_uri, BPMN.condition)
    
    if condition is None:
        return True # Default flow if no condition exists

    var_name = str(graph.value(condition, BPMN.variable))
    op_str = str(graph.value(condition, BPMN.operator))
    threshold = graph.value(condition, BPMN.value).toPython()

    # Get the actual value from our process instance data
    actual_value = instance_data.get(var_name)
    
    # Perform the logic: e.g., actual_value > 1000
    return OPERATORS[op_str](actual_value, threshold)

def resolve_gateway(graph, gateway_uri, instance_data):
    query = """
    SELECT ?flow ?target WHERE {
        ?flow <http://example.org/bpmn/source> ?gateway ;
              <http://example.org/bpmn/target> ?target .
    }
    """
    results = graph.query(query, initBindings={'gateway': gateway_uri})
    
    for row in results:
        if evaluate_condition(graph, row.flow, instance_data):
            return row.target
            
    raise Exception("No valid path found (Dead end)")

from rdflib import URIRef

def evaluate_sparql_condition(engine_graph, flow_uri, instance_uri):
    # 1. Fetch the query string from the process definition
    query_string = engine_graph.value(flow_uri, BPMN.conditionQuery)
    
    if not query_string:
        return True  # Default flow if no query is defined

    # 2. Execute the ASK query
    # We use 'initBindings' to inject the specific instance ID into the query
    result = engine_graph.query(
        str(query_string), 
        initBindings={'instance': URIRef(instance_uri)}
    )
    
    return bool(result.askAnswer)

from rdflib import XSD

# 1. Define the actual business logic
def tax_calculator(context):
    """Logic to calculate 10% tax"""
    # Pull variable from RDF
    total = float(context.get_variable("orderTotal"))
    
    tax = total * 0.10
    
    # Push result back to RDF
    context.set_variable("taxAmount", tax, datatype=XSD.decimal)
    print(f"Computed tax: {tax} for Instance: {context.inst}")

# 2. The Registry
TOPIC_REGISTRY = {
    "calculate_tax": tax_calculator
}

def execute_step(engine_graph, instance_uri):
    # Get current node for this instance
    current_node = get_current_node(instance_uri) 
    
    # Check node type
    node_type = engine_graph.value(current_node, RDF.type)
    
    if node_type == BPMN.ServiceTask:
        # Get the topic string
        topic = str(engine_graph.value(current_node, BPMN.topic))
        
        # Initialize context for this instance
        context = ProcessContext(engine_graph, instance_uri)
        
        # Execute the registered function
        if topic in TOPIC_REGISTRY:
            TOPIC_REGISTRY[topic](context)
            
        # Move to next node
        next_node = engine_graph.value(current_node, BPMN.next)
        update_instance_state(instance_uri, next_node)


def check_inventory_worker(context):
    # Query the graph to see if we have enough stock for the product linked to this instance
    query = """
    SELECT ?stock WHERE {
        ?instance var:orderedProduct ?product .
        ?product var:quantityInStock ?stock .
    }
    """
    res = context.g.query(query, initBindings={'instance': context.inst})
    # ... logic to update state based on result

def handle_token_arrival(engine_graph, token_uri, gateway_uri, instance_uri):
    # 1. Update this token's position to the gateway
    engine_graph.set((token_uri, BPMN.atNode, gateway_uri))
    
    # 2. Run the Synchronization Query
    is_joined = engine_graph.query(JOIN_QUERY, initBindings={
        'gateway': gateway_uri,
        'instance': instance_uri
    }).askAnswer

    if is_joined:
        print("All branches complete. Merging tokens and moving forward.")
        # 3. Consolidate: Delete the multiple branch tokens
        # 4. Create one new token for the next node after the gateway
        merge_tokens(engine_graph, instance_uri, gateway_uri)
    else:
        print("Waiting for other parallel branches...")