#!/usr/bin/env python3
"""
HTTP Service Task Handlers for SPEAR BPMN Engine

This module provides pre-built HTTP/REST API handlers for service tasks.
Use these to register handlers for common API calls.

Example:
    from src.api.handlers.http_handlers import HTTPHandlers

    handlers = HTTPHandlers()
    
    # Register a handler that calls a payment API
    storage.register_topic_handler(
        topic="process_payment",
        handler_function=handlers.create_payment_handler(
            url="https://api.paymentgateway.com/charge",
            method="POST",
            auth={"type": "bearer", "token": "your-api-key"},
            request_template={"amount": "${orderTotal}", "currency": "USD"},
            response_extract={"transactionId": "$.transaction.id", "status": "$.transaction.status"}
        )
    )

HTTP Methods:
    - GET: Retrieve data from a URL
    - POST: Create new resources
    - PUT: Update existing resources
    - DELETE: Remove resources

Authentication:
    - api_key: Add X-API-Key header
    - bearer: Add Authorization: Bearer token header
    - basic: Add Authorization: Basic base64(user:pass) header
    - none: No authentication

Variable Substitution:
    Use ${variableName} in URLs, headers, or body to substitute process variables.
    
    Example:
        url: "https://api.example.com/users/${userId}/orders"
        body: {"amount": ${orderTotal}, "currency": "USD"}

Response Extraction:
    Use JSONPath-like syntax to extract values from responses.
    
    Example:
        {"transactionId": "$.transaction.id", "total": "$.amount"}
        
    This will extract transaction.id and amount from the JSON response.
"""

import json
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class HTTPHandlers:
    """
    Collection of HTTP request handlers for service tasks.
    """
    
    def __init__(self, default_timeout: int = 30, max_retries: int = 3):
        """
        Initialize HTTP handlers.
        
        Args:
            default_timeout: Default request timeout in seconds
            max_retries: Maximum number of retries on failure
        """
        self.default_timeout = default_timeout
        self.max_retries = max_retries
    
    def _substitute_variables(self, text: str, variables: Dict[str, Any]) -> str:
        """
        Substitute process variables in text.
        
        Args:
            text: Text with ${variableName} placeholders
            variables: Dictionary of variable values
            
        Returns:
            Text with variables substituted
        """
        if not text:
            return text
        
        result = text
        for key, value in variables.items():
            placeholder = f"${{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        
        return result
    
    def _extract_response_data(self, response_data: Dict, 
                               extraction_map: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract values from response using extraction map.
        
        Args:
            response_data: JSON response as dictionary
            extraction_map: {"variableName": "$.json.path.syntax"}
            
        Returns:
            Dictionary of extracted values
        """
        extracted = {}
        
        for var_name, json_path in extraction_map.items():
            try:
                # Simple JSON path-like extraction
                # Support: $.field.nestedField or just field
                # Strip leading $ and any leading dots
                if json_path.startswith('$'):
                    path = json_path[1:].lstrip('.')
                else:
                    path = json_path
                parts = path.split('.') if path else []
                value = response_data
                
                for part in parts:
                    if part and value and isinstance(value, dict):
                        value = value.get(part)
                    elif part and value and isinstance(value, list) and part.isdigit():
                        idx = int(part)
                        value = value[idx] if idx < len(value) else None
                    else:
                        value = None
                        break
                
                if value is not None:
                    # Convert to string for storage
                    extracted[var_name] = str(value) if not isinstance(value, (dict, list)) else value
                    
            except Exception as e:
                logger.warning(f"Failed to extract {json_path}: {e}")
                continue
        
        return extracted
    
    def _make_request(self, method: str, url: str, headers: Dict = None, 
                     params: Dict = None, data: Any = None, 
                     auth: Dict = None, timeout: int = None) -> Dict:
        """
        Make an HTTP request with authentication.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Request URL
            headers: Request headers
            params: Query parameters
            data: Request body
            auth: Authentication config
            timeout: Request timeout
            
        Returns:
            Response data dictionary
            
        Raises:
            Exception: If request fails
        """
        # Set up authentication
        auth_obj = None
        if auth:
            auth_type = auth.get("type", "none")
            if auth_type == "bearer":
                auth_obj = requests.auth.HTTPBearerAuth(auth.get("token", ""))
            elif auth_type == "basic":
                import base64
                credentials = f"{auth.get('username', '')}:{auth.get('password', '')}"
                auth_obj = requests.auth.HTTPBasicAuth(*credentials.split(":", 1))
            elif auth_type == "api_key":
                header_name = auth.get("header", "X-API-Key")
                if headers is None:
                    headers = {}
                headers[header_name] = auth.get("key", "")
        
        # Set default timeout
        if timeout is None:
            timeout = self.default_timeout
        
        # Make request with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    json=data if method.upper() in ["POST", "PUT"] else None,
                    data=data if method.upper() not in ["POST", "PUT"] else None,
                    auth=auth_obj,
                    timeout=timeout
                )
                
                # Raise for status
                response.raise_for_status()
                
                # Parse response
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {"text": response.text, "status_code": response.status_code}
                    
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue
        
        raise last_error
    
    def create_http_handler(self, url: str, method: str = "GET",
                           headers: Optional[Dict] = None,
                           params: Optional[Dict] = None,
                           data: Optional[Dict] = None,
                           auth: Optional[Dict] = None,
                           timeout: Optional[int] = None,
                           response_extract: Optional[Dict[str, str]] = None,
                           description: str = "") -> callable:
        """
        Create an HTTP request handler for a service task.
        
        Args:
            url: Request URL (can use ${variable} substitution)
            method: HTTP method (GET, POST, PUT, DELETE)
            headers: Request headers (can use ${variable} substitution)
            params: Query parameters (can use ${variable} substitution)
            data: Request body (can use ${variable} substitution)
            auth: Authentication config
            timeout: Request timeout in seconds
            response_extract: Dict to extract values from response {"var": "$.json.path"}
            description: Handler description
            
        Returns:
            Handler function suitable for register_topic_handler()
            
        Example:
            handler = handlers.create_http_handler(
                url="https://api.example.com/users/${userId}",
                method="GET",
                auth={"type": "bearer", "token": "your-api-key"},
                response_extract={"userName": "$.name", "userEmail": "$.email"}
            )
            
            storage.register_topic_handler(
                topic="get_user_details",
                handler_function=handler,
                description="Fetch user details from API"
            )
        """
        def handler(instance_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
            """
            Execute HTTP request and update variables.
            
            Args:
                instance_id: Process instance ID
                variables: Current process variables
                
            Returns:
                Updated variables with response data
            """
            # Substitute variables
            final_url = self._substitute_variables(url, variables)
            final_headers = {}
            if headers:
                for key, value in headers.items():
                    final_headers[key] = self._substitute_variables(value, variables)
            
            final_params = {}
            if params:
                for key, value in params.items():
                    final_params[key] = self._substitute_variables(str(value), variables)
            
            final_data = None
            if data:
                if isinstance(data, dict):
                    final_data = {}
                    for key, value in data.items():
                        if isinstance(value, str):
                            final_data[key] = self._substitute_variables(value, variables)
                        else:
                            final_data[key] = value
                else:
                    final_data = self._substitute_variables(str(data), variables)
            
            logger.info(f"Making {method} request to {final_url} for instance {instance_id}")
            
            # Make request
            response_data = self._make_request(
                method=method,
                url=final_url,
                headers=final_headers,
                params=final_params,
                data=final_data,
                auth=auth,
                timeout=timeout
            )
            
            # Extract response data
            if response_extract and isinstance(response_data, dict):
                extracted = self._extract_response_data(response_data, response_extract)
                variables.update(extracted)
                logger.info(f"Extracted {len(extracted)} values from response")
            
            # Always add raw response
            variables["_http_response"] = response_data
            
            return variables
        
        # Attach metadata for documentation
        handler.__doc__ = f"""HTTP {method} request to {url}
        
{description}
        
Variables are substituted in URL, headers, params, and body using ${{variableName}} syntax.
Response data is extracted using JSONPath-like syntax.
"""
        
        return handler
    
    def get(self, url: str, 
            response_extract: Optional[Dict[str, str]] = None,
            auth: Optional[Dict] = None,
            timeout: Optional[int] = None,
            description: str = "") -> callable:
        """
        Create a GET request handler.
        
        Example:
            handler = handlers.get(
                url="https://api.example.com/users/${userId}",
                response_extract={"userName": "$.name", "email": "$.email"},
                auth={"type": "bearer", "token": "api-key"}
            )
        """
        return self.create_http_handler(
            url=url,
            method="GET",
            auth=auth,
            timeout=timeout,
            response_extract=response_extract,
            description=description or f"GET {url}"
        )
    
    def post(self, url: str,
             data: Optional[Dict] = None,
             response_extract: Optional[Dict[str, str]] = None,
             auth: Optional[Dict] = None,
             timeout: Optional[int] = None,
             description: str = "") -> callable:
        """
        Create a POST request handler.
        
        Example:
            handler = handlers.post(
                url="https://api.example.com/orders",
                data={"customerId": "${customerId}", "amount": "${orderTotal}"},
                response_extract={"orderId": "$.id", "status": "$.status"}
            )
        """
        return self.create_http_handler(
            url=url,
            method="POST",
            data=data,
            auth=auth,
            timeout=timeout,
            response_extract=response_extract,
            description=description or f"POST {url}"
        )
    
    def put(self, url: str,
            data: Optional[Dict] = None,
            response_extract: Optional[Dict[str, str]] = None,
            auth: Optional[Dict] = None,
            timeout: Optional[int] = None,
            description: str = "") -> callable:
        """
        Create a PUT request handler.
        """
        return self.create_http_handler(
            url=url,
            method="PUT",
            data=data,
            auth=auth,
            timeout=timeout,
            response_extract=response_extract,
            description=description or f"PUT {url}"
        )
    
    def delete(self, url: str,
               response_extract: Optional[Dict[str, str]] = None,
               auth: Optional[Dict] = None,
               timeout: Optional[int] = None,
               description: str = "") -> callable:
        """
        Create a DELETE request handler.
        """
        return self.create_http_handler(
            url=url,
            method="DELETE",
            auth=auth,
            timeout=timeout,
            response_extract=response_extract,
            description=description or f"DELETE {url}"
        )
    
    def webhook(self, url: str,
                method: str = "POST",
                headers: Optional[Dict] = None,
                data_template: Optional[Dict] = None,
                response_extract: Optional[Dict[str, str]] = None,
                auth: Optional[Dict] = None,
                timeout: Optional[int] = None,
                description: str = "") -> callable:
        """
        Create a webhook handler (sends data to a URL).
        
        Example:
            handler = handlers.webhook(
                url="https://hooks.example.com/orders",
                method="POST",
                data_template={
                    "event": "order_completed",
                    "orderId": "${orderId}",
                    "total": "${orderTotal}",
                    "customer": "${customerEmail}"
                },
                headers={"X-Webhook-Secret": "your-secret"}
            )
        """
        return self.create_http_handler(
            url=url,
            method=method,
            headers=headers,
            data=data_template,
            auth=auth,
            timeout=timeout,
            response_extract=response_extract,
            description=description or f"Webhook to {url}"
        )


# Convenience function for quick handler creation
def create_http_handler(**kwargs) -> callable:
    """
    Create an HTTP request handler.
    
    Shorthand for HTTPHandlers().create_http_handler(**kwargs)
    
    Example:
        handler = create_http_handler(
            url="https://api.example.com/data",
            method="GET",
            response_extract={"result": "$.data"}
        )
    """
    return HTTPHandlers().create_http_handler(**kwargs)


# Pre-built handlers for common use cases
class PreBuiltHandlers:
    """Pre-built handlers for common integrations."""
    
    @staticmethod
    def send_slack_webhook(webhook_url: str, channel: str = None) -> callable:
        """
        Send a Slack notification.
        
        Variables: message, channel (optional), severity (optional)
        """
        def handler(instance_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
            import requests
            
            payload = {
                "text": variables.get("message", "Process notification"),
                "channel": variables.get("channel", channel),
            }
            
            # Add color for severity
            severity = variables.get("severity", "info")
            if severity == "error":
                payload["attachments"] = [{"color": "danger", "text": payload["text"]}]
            elif severity == "success":
                payload["attachments"] = [{"color": "good", "text": payload["text"]}]
            
            try:
                response = requests.post(webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                variables["slack_notified"] = True
                variables["slack_status"] = "success"
            except Exception as e:
                variables["slack_notified"] = False
                variables["slack_error"] = str(e)
            
            return variables
        
        return handler
    
    @staticmethod
    def send_email(smtp_config: Dict) -> callable:
        """
        Send an email notification.
        
        Requires smtp_config with: host, port, username, password, from_email
        
        Variables: to_email, subject, body
        """
        def handler(instance_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            try:
                msg = MIMEMultipart()
                msg["From"] = smtp_config["from_email"]
                msg["To"] = variables.get("to_email", smtp_config.get("default_to", ""))
                msg["Subject"] = variables.get("subject", "Process Notification")
                msg.attach(MIMEText(variables.get("body", ""), "plain"))
                
                with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
                    server.starttls()
                    server.login(smtp_config["username"], smtp_config["password"])
                    server.send_message(msg)
                
                variables["email_sent"] = True
                variables["email_status"] = "success"
                
            except Exception as e:
                variables["email_sent"] = False
                variables["email_error"] = str(e)
            
            return variables
        
        return handler
    
    @staticmethod
    def call_weather_api(api_key: str) -> callable:
        """
        Get weather data for a location.
        
        Variables: city, country (optional)
        """
        def handler(instance_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
            import requests
            
            city = variables.get("city", "New York")
            country = variables.get("country", "US")
            
            try:
                response = requests.get(
                    f"http://api.openweathermap.org/data/2.5/weather",
                    params={"q": f"{city},{country}", "appid": api_key},
                    timeout=10
                )
                data = response.json()
                
                if data.get("cod") == 200:
                    variables["weather_temp"] = data["main"]["temp"]
                    variables["weather_humidity"] = data["main"]["humidity"]
                    variables["weather_description"] = data["weather"][0]["description"]
                    variables["weather_city"] = data["name"]
                    variables["weather_status"] = "success"
                else:
                    variables["weather_status"] = "error"
                    variables["weather_error"] = data.get("message", "Unknown error")
                    
            except Exception as e:
                variables["weather_status"] = "error"
                variables["weather_error"] = str(e)
            
            return variables
        
        return handler


# Example usage and testing
if __name__ == "__main__":
    from src.api.storage import get_storage
    
    storage = get_storage()
    handlers = HTTPHandlers()
    
    # Example 1: GET request
    storage.register_topic_handler(
        topic="get_user",
        handler_function=handlers.get(
            url="https://jsonplaceholder.typicode.com/users/${userId}",
            response_extract={"name": "$.name", "email": "$.email", "city": "$.address.city"},
            description="Fetch user details from placeholder API"
        ),
        description="Get user details"
    )
    
    # Example 2: POST request with authentication
    storage.register_topic_handler(
        topic="create_order",
        handler_function=handlers.post(
            url="https://api.example.com/orders",
            data={
                "customerId": "${customerId}",
                "items": "${cartItems}",
                "total": "${orderTotal}"
            },
            auth={"type": "bearer", "token": "your-api-token"},
            response_extract={"orderId": "$.id", "status": "$.status", "estimatedDelivery": "$.deliveryDate"}
        )
    )
    
    # Example 3: Webhook notification
    storage.register_topic_handler(
        topic="notify_slack",
        handler_function=PreBuiltHandlers.send_slack_webhook(
            webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
        )
    )
    
    # Test the handlers
    print("Testing HTTP handlers...")
    
    # Test get_user
    result = storage.execute_service_task(
        instance_id="test-1",
        topic="get_user",
        variables={"userId": "1"}
    )
    print(f"\\nget_user result: {result}")
    
    print("\\nAll handlers registered successfully!")
