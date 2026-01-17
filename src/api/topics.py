# Service Task Topics API Endpoints
# REST API for managing service task topic handlers

from fastapi import APIRouter, HTTPException
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from src.api.storage import RDFStorageService, get_storage
from src.api.handlers.http_handlers import HTTPHandlers

router = APIRouter(prefix="/topics", tags=["Service Tasks"])

storage = get_storage()
http_handlers = HTTPHandlers()


# ==================== Request/Response Models ====================

class HTTPHandlerConfig(BaseModel):
    """HTTP handler configuration"""
    url: str = Field(..., description="Request URL with ${variable} substitution")
    method: str = Field(default="GET", description="HTTP method (GET, POST, PUT, DELETE)")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Request headers")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Query parameters")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Request body data")
    auth: Optional[Dict[str, Any]] = Field(default=None, description="Authentication config")
    timeout: Optional[int] = Field(default=30, description="Request timeout in seconds")
    response_extract: Optional[Dict[str, str]] = Field(default=None, description="JSONPath extraction map")
    description: str = Field(default="", description="Handler description")


class TopicHandlerRegistration(BaseModel):
    """Request model for registering a topic handler"""
    topic: str = Field(..., description="Topic name (e.g., 'get_weather', 'send_notification')")
    handler_type: str = Field(..., description="Type of handler (http, script, function)")
    description: str = Field(default="", description="Handler description")
    http_config: Optional[HTTPHandlerConfig] = Field(default=None, description="HTTP handler configuration")
    async_execution: bool = Field(default=False, description="Execute asynchronously")


class TopicHandlerUpdate(BaseModel):
    """Request model for updating a topic handler"""
    description: Optional[str] = Field(default=None, description="Handler description")
    http_config: Optional[HTTPHandlerConfig] = Field(default=None, description="HTTP handler configuration")
    async_execution: Optional[bool] = Field(default=None, description="Execute asynchronously")


class TopicHandlerResponse(BaseModel):
    """Response model for topic handler info"""
    topic: str = ""
    description: str = ""
    async_execution: bool = False
    handler_type: str = "function"
    registered_at: str = ""
    http_config: Optional[Dict[str, Any]] = None


class TopicListResponse(BaseModel):
    """Response for list of topics"""
    topics: Dict[str, Any]
    total: int


class TestHandlerRequest(BaseModel):
    """Request for testing a handler"""
    variables: Optional[Dict[str, Any]] = Field(default=None, description="Input variables for test")


class TestHandlerResponse(BaseModel):
    """Response from testing a handler"""
    topic: str
    input_variables: Dict[str, Any]
    output_variables: Dict[str, Any]
    execution_time_ms: float
    status: str


# ==================== Built-in Handlers ====================

BUILTIN_HANDLERS = {
    "get_user": {
        "handler_type": "http",
        "description": "Fetch user details from JSONPlaceholder API",
        "http_config": {
            "url": "https://jsonplaceholder.typicode.com/users/${userId}",
            "method": "GET",
            "response_extract": {
                "userName": "$.name",
                "userEmail": "$.email",
                "userCity": "$.address.city"
            }
        }
    },
    "create_post": {
        "handler_type": "http",
        "description": "Create a post via JSONPlaceholder API",
        "http_config": {
            "url": "https://jsonplaceholder.typicode.com/posts",
            "method": "POST",
            "data": {
                "title": "${postTitle}",
                "body": "${postBody}",
                "userId": "${userId}"
            },
            "response_extract": {
                "postId": "$.id",
                "postTitle": "$.title"
            }
        }
    },
    "get_weather": {
        "handler_type": "http",
        "description": "Get weather for a location (requires API key)",
        "http_config": {
            "url": "https://api.openweathermap.org/data/2.5/weather?q=${city},${country}&appid=${weatherApiKey}",
            "method": "GET",
            "response_extract": {
                "weather_temp": "$.main.temp",
                "weather_humidity": "$.main.humidity",
                "weather_description": "$.weather[0].description",
                "weather_city": "$.name"
            }
        }
    },
    "send_slack_notification": {
        "handler_type": "webhook",
        "description": "Send Slack notification via webhook",
        "http_config": {
            "url": "${slackWebhookUrl}",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "data": {
                "text": "${notificationMessage}",
                "channel": "${slackChannel}"
            },
            "description": "Send Slack webhook notification"
        }
    },
    "calculate_tax": {
        "handler_type": "script",
        "description": "Calculate tax (10% rate)",
        "script": """
def calculate_tax(instance_id, variables):
    order_total = float(variables.get('orderTotal', 0))
    tax = order_total * 0.10
    variables['taxAmount'] = round(tax, 2)
    variables['taxRate'] = 0.10
    return variables
"""
    }
}


# ==================== CRUD Endpoints ====================

@router.get("", response_model=TopicListResponse)
async def list_topics():
    """
    List all registered service task topics.
    
    Returns all topics that have registered handlers.
    """
    topics = storage.get_registered_topics()
    
    return {
        "topics": topics,
        "total": len(topics)
    }


@router.get("/builtin")
async def list_builtin_handlers():
    """
    List available built-in handler templates.
    
    Returns pre-built handler templates that can be registered.
    """
    return {
        "builtin_handlers": BUILTIN_HANDLERS,
        "total": len(BUILTIN_HANDLERS)
    }


@router.post("/builtin/{handler_name}")
async def register_builtin_handler(handler_name: str):
    """
    Register a built-in handler template.
    
    Creates a new handler instance from the built-in templates.
    
    Available handlers:
    - get_weather: Fetch weather data from OpenWeatherMap
    - get_user: Fetch user details from JSONPlaceholder
    - create_post: Create a post via JSONPlaceholder
    - send_slack_notification: Send Slack webhook notification
    - calculate_tax: Calculate 10% tax on order total
    """
    if handler_name not in BUILTIN_HANDLERS:
        available = list(BUILTIN_HANDLERS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Built-in handler '{handler_name}' not found. Available: {available}"
        )
    
    builtin = BUILTIN_HANDLERS[handler_name]
    handler_type = builtin["handler_type"]
    
    if handler_type == "http":
        config = builtin["http_config"]
        handler = http_handlers.create_http_handler(
            url=config["url"],
            method=config.get("method", "GET"),
            headers=config.get("headers"),
            params=config.get("params"),
            data=config.get("data"),
            auth=config.get("auth"),
            timeout=config.get("timeout", 30),
            response_extract=config.get("response_extract"),
            description=builtin["description"]
        )
        
        storage.register_topic_handler(
            topic=handler_name,
            handler_function=handler,
            description=builtin["description"],
            handler_type=handler_type,
            http_config=config
        )
        
    elif handler_type == "webhook":
        config = builtin["http_config"]
        handler = http_handlers.webhook(
            url=config["url"],
            method=config.get("method", "POST"),
            headers=config.get("headers"),
            data_template=config.get("data"),
            description=builtin["description"]
        )
        
        storage.register_topic_handler(
            topic=handler_name,
            handler_function=handler,
            description=builtin["description"],
            handler_type=handler_type,
            http_config=config
        )
    
    return {
        "message": f"Built-in handler '{handler_name}' registered successfully",
        "topic": handler_name,
        "description": builtin["description"]
    }


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


@router.post("")
async def create_topic_handler(request: TopicHandlerRegistration):
    """
    Create a new service task handler.
    
    Registers a new handler for a topic. Supports HTTP handlers for calling external APIs.
    
    Example - Create an HTTP handler:
    
    ```json
    {
        "topic": "get_weather",
        "handler_type": "http",
        "description": "Fetch weather data",
        "http_config": {
            "url": "https://api.weather.com/data/2.5/weather?q=${city}",
            "method": "GET",
            "response_extract": {
                "temperature": "$.main.temp",
                "humidity": "$.main.humidity"
            }
        }
    }
    ```
    """
    topic = request.topic.lower().strip()
    
    topics = storage.get_registered_topics()
    if topic in topics:
        raise HTTPException(
            status_code=409, 
            detail=f"Topic '{topic}' already exists. Use PUT to update."
        )
    
    if request.handler_type not in ["http", "script", "function", "webhook"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid handler_type: {request.handler_type}. Must be: http, script, function, or webhook"
        )
    
    if request.handler_type in ["http", "webhook"]:
        if not request.http_config:
            raise HTTPException(
                status_code=400,
                detail="http_config is required for http/webhook handlers"
            )
        
        config = request.http_config
        config_dict = config.model_dump() if hasattr(config, 'model_dump') else dict(config)
        method = config_dict.get("method", "GET")
        
        handler = http_handlers.create_http_handler(
            url=config_dict["url"],
            method=method,
            headers=config_dict.get("headers"),
            params=config_dict.get("params"),
            data=config_dict.get("data"),
            auth=config_dict.get("auth"),
            timeout=config_dict.get("timeout", 30),
            response_extract=config_dict.get("response_extract"),
            description=request.description
        )
        
        storage.register_topic_handler(
            topic=topic,
            handler_function=handler,
            description=request.description,
            async_execution=request.async_execution,
            handler_type=request.handler_type,
            http_config=config_dict
        )
        
    elif request.handler_type == "script":
        raise HTTPException(
            status_code=400,
            detail="Script handlers must be registered programmatically. Use Python functions."
        )
    
    elif request.handler_type == "function":
        raise HTTPException(
            status_code=400,
            detail="Function handlers must be registered programmatically. Pass a Python callable."
        )
    
    return {
        "message": f"Handler for topic '{topic}' created successfully",
        "topic": topic,
        "handler_type": request.handler_type,
        "description": request.description
    }


@router.put("/{topic}")
async def update_topic_handler(topic: str, request: TopicHandlerUpdate):
    """
    Update an existing service task handler.
    
    Updates the configuration of an existing handler. To change the handler
    implementation, you need to unregister and re-register.
    
    Note: Only description and async_execution can be updated. To change
    the actual handler, delete and recreate the topic.
    """
    topics = storage.get_registered_topics()
    
    if topic not in topics:
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    if request.description is not None:
        storage.update_topic_description(topic, request.description)
    
    if request.async_execution is not None:
        storage.update_topic_async(topic, request.async_execution)
    
    if request.http_config is not None:
        storage.unregister_topic_handler(topic)
        
        config_dict = request.http_config.model_dump() if hasattr(request.http_config, 'model_dump') else dict(request.http_config)
        
        handler = http_handlers.create_http_handler(
            url=config_dict["url"],
            method=config_dict.get("method", "GET"),
            headers=config_dict.get("headers"),
            params=config_dict.get("params"),
            data=config_dict.get("data"),
            auth=config_dict.get("auth"),
            timeout=config_dict.get("timeout", 30),
            response_extract=config_dict.get("response_extract"),
            description=request.description or topics[topic].get("description", "")
        )
        
        storage.register_topic_handler(
            topic=topic,
            handler_function=handler,
            description=request.description or topics[topic].get("description", ""),
            async_execution=request.async_execution if request.async_execution is not None 
                else topics[topic].get("async_execution", False),
            handler_type="http",
            http_config=config_dict
        )
    
    return {
        "message": f"Handler for topic '{topic}' updated successfully",
        "topic": topic
    }


@router.delete("/{topic}")
async def delete_topic_handler(topic: str):
    """
    Delete a service task handler.
    
    Removes the handler for the specified topic.
    """
    success = storage.unregister_topic_handler(topic)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    return {
        "message": f"Handler for topic '{topic}' deleted successfully"
    }


@router.post("/{topic}/test")
async def test_topic_handler(topic: str, request: TestHandlerRequest = None):
    """
    Test a service task handler.
    
    Executes the handler for a topic with the provided variables
    and returns the result. Useful for testing handlers before
    using them in production processes.
    """
    topics = storage.get_registered_topics()
    
    if topic not in topics:
        if topic in BUILTIN_HANDLERS:
            raise HTTPException(
                status_code=404,
                detail=f"Topic '{topic}' is a built-in template. POST /api/v1/topics/builtin/{topic} to register first."
            )
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    test_variables = request.variables if request else {"test": "value"}
    
    import time
    start_time = time.time()
    
    try:
        result = storage.execute_service_task(
            instance_id="test-instance",
            topic=topic,
            variables=test_variables
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        return TestHandlerResponse(
            topic=topic,
            input_variables=test_variables,
            output_variables=result,
            execution_time_ms=round(execution_time, 2),
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{topic}/docs")
async def get_handler_docs(topic: str):
    """
    Get documentation for a topic handler.
    
    Returns usage examples and configuration options.
    """
    topics = storage.get_registered_topics()
    
    if topic not in topics and topic not in BUILTIN_HANDLERS:
        raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
    
    if topic in BUILTIN_HANDLERS:
        builtin = BUILTIN_HANDLERS[topic]
        return {
            "topic": topic,
            "type": builtin["handler_type"],
            "description": builtin["description"],
            "example_variables": {
                "test": "example_value"
            },
            "documentation": "See JSONPlaceholder API docs at https://jsonplaceholder.typicode.com/"
        }
    
    info = topics[topic]
    return {
        "topic": topic,
        "type": info.get("handler_type", "unknown"),
        "description": info.get("description", ""),
        "example_variables": {
            "test": "example_value"
        }
    }
