import csv
from config import QUERY_ENDPOINT
from rdflib.plugins.stores.sparqlstore import SPARQLStore

def export_to_xes_csv(output_file="process_logs.csv"):
    store = SPARQLStore(QUERY_ENDPOINT)
    
    # This query joins the Audit Log with the Activity Labels
    query = """
    PREFIX log: <http://example.org/audit/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT ?caseId ?activityLabel ?timestamp ?eventType ?user
    WHERE {
        GRAPH <http://example.org/audit/graph> {
            ?event log:instance ?caseId ;
                   log:activity ?activity ;
                   log:timestamp ?timestamp ;
                   log:eventType ?eventType .
            OPTIONAL { ?event log:executedBy ?user }
        }
        GRAPH <http://example.org/defs/graph> {
            ?activity rdfs:label ?activityLabel .
        }
    }
    ORDER BY ?caseId ?timestamp
    """
    
    results = store.query(query)
    
    with open(output_file, mode='w', newline='') as f:
        writer = csv.writer(f)
        # Standard Process Mining Headers
        writer.writerow(["Case ID", "Activity", "Timestamp", "Lifecycle:Transition", "Resource"])
        
        for row in results:
            writer.writerow([
                str(row.caseId).split('/')[-1], # Shorten URI to ID
                str(row.activityLabel),
                row.timestamp.toPython().isoformat(),
                str(row.eventType),
                str(row.user) if row.user else "System"
            ])
            
    print(f"Exported {len(results)} events to {output_file}")