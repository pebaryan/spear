# Service Task Topics API Endpoints
# REST API for managing service task topic handlers

from fastapi import APIRouter, HTTPException
from typing import Any, Dict
from pydantic import BaseModel, Field
from src.api.storage import RDFStorageService, get_storage

router = APIRouter(prefix="/topics", tags=["Service Tasks"])

# Use shared storage service
storage = get_storage()


class TopicHandlerRegistration(BaseModel):
    """Request model for registering a topic handler"""
    topic: str = Field(..., description="Topic name (e.g., 'send_email', 'calculate_tax')")
    handler_type: str = Field(..., description="Type of handler (http, script, function)")
    config: Dict[str, Any] = Field(..., description="Handler configuration")


class TopicHandlerResponse(BaseModel):
    """Response model for topic handler info"""
    topic: str
    description: str
    async_execution: bool
    registered_at: str


class TopicListResponse(BaseModel):
    """Response for list of topics"""
    topics: Dict[str, TopicHandlerResponse]
    total: int


@router.get("", response_model=TopicListResponse)
async def list_topics():
    """
    List all registered service task topics.
    
    Returns all topics that have registered handlers.
    """
    topics = storage.get_registered_topics()
    
    return TopicListResponse(
        topics=topics,
        total=len(topics)
    )


@router.get("/{topic}")
async def get_topic(topic: str):
    """
    Get information about a specific topic handler.
    
    Returns details about the registered handler for a topic.
    """
    topics = storage.get_registered_topics()
    
    if topic not in topics:
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    info = topics[topic]
    return {
        "topic": topic,
        **info
    }


@router.post("/register")
async def register_handler(request: TopicHandlerRegistration):
    """
    Register a service task handler.
    
    Note: In this implementation, handlers are registered programmatically.
    This endpoint is for documentation and future extensibility.
    
    Example handler registration in Python:
    
    ```python
    from src.api.storage import get_storage
    
    storage = get_storage()
    
    def calculate_tax_handler(instance_id, variables):
        order_total = float(variables.get("orderTotal", 0))
        tax = order_total * 0.10
        variables["taxAmount"] = tax
        return variables
    
    storage.register_topic_handler(
        topic="calculate_tax",
        handler_function=calculate_tax_handler,
        description="Calculate 10% tax on order total"
    )
    ```
    """
    # For now, just return info about how to register handlers
    return {
        "message": "Handlers must be registered programmatically",
        "example": {
            "topic": "calculate_tax",
            "how_to_register": "Use storage.register_topic_handler() in Python code",
            "example_code": """
from src.api.storage import get_storage

storage = get_storage()

def calculate_tax(instance_id, variables):
    order_total = float(variables.get("orderTotal", 0))
    tax = order_total * 0.10
    variables["taxAmount"] = tax
    return variables

storage.register_topic_handler(
    topic="calculate_tax",
    handler_function=calculate_tax,
    description="Calculate 10% tax on order"
)
            """.strip()
        },
        "received_request": request.dict()
    }


@router.delete("/{topic}")
async def unregister_handler(topic: str):
    """
    Unregister a service task handler.
    
    Removes the handler for the specified topic.
    """
    success = storage.unregister_topic_handler(topic)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    return {
        "message": f"Handler for topic {topic} unregistered successfully"
    }


@router.post("/{topic}/test")
async def test_topic_handler(topic: str, variables: Dict[str, Any] = None):
    """
    Test a service task handler with sample variables.
    
    Executes the handler for a topic with the provided variables
    and returns the result. Useful for testing handlers.
    """
    topics = storage.get_registered_topics()
    
    if topic not in topics:
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    test_variables = variables or {"test": "value"}
    
    try:
        result = storage.execute_service_task(
            instance_id="test-instance",
            topic=topic,
            variables=test_variables
        )
        
        return {
            "topic": topic,
            "input_variables": test_variables,
            "output_variables": result,
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
