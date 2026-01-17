from rdflib import Graph, Literal, RDF, URIRef, Namespace

# Define Namespaces
PROC = Namespace("http://example.org/process/")
BPMN = Namespace("http://example.org/bpmn/")

g = Graph()

# Define a simple flow: Start -> Task1 -> End
process = PROC.OrderProcess
task1 = PROC.VerifyPayment

g.add((process, RDF.type, BPMN.Process))
g.add((task1, RDF.type, BPMN.ServiceTask))
g.add((task1, BPMN.action, Literal("verify_payment_function")))

# Define the flow (The "Edges")
g.add((PROC.StartNode, BPMN.next, task1))
g.add((task1, BPMN.next, PROC.EndNode))
