from fastapi import FastAPI, HTTPException, Query, Request, Response,status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from typing import Optional, List, Literal
import redis
import httpx
import os
import uuid
from datetime import datetime
from fastapi.responses import JSONResponse
import time
from user_service.app.main import get_user_avail_cache_aside
app = FastAPI(root_path="/tasks")



# External user service base (for validating userId on create/update)
AVAIL_BASE = os.getenv("AVAIL_BASE", "http://availability-service:8000")

# Endpoints
@app.get("/health")
async def health_check(response: Response):
    service="suggestion-service"
    start_time=time.perf_counter()
    status_indicator="healthy"
    dependencies={}
    try:
        resp=httpx.get(f"{AVAIL_BASE}/health", timeout=5.0)
        if resp.status_code==200:
            dependencies["availability-service"]={"status":resp.json().get("status"),"response_time_ms":(time.perf_counter()-start_time)*1000}
        else:
            # it is not 200 likely 504
            dependencies["availability-service"]={"status":resp.json().get("status"),"response_time_ms":(time.perf_counter()-start_time)*1000}
            status_indicator="unhealthy"
    except Exception as e:
        dependencies["availability-service"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
        status_indicator="unhealthy"
    
    if status_indicator=="unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response.status_code = status.HTTP_200_OK
    
    return {"service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }
@app.get("/suggestions")
async def get_suggestions(userId1: Optional[str] = Query(None, description="User ID to get suggestions for"),
                          userId2: Optional[str] = Query(None, description="Second User ID to get suggestions for")):
    
    user1_data= get_user_avail_cache_aside(userId1)
    user2_data= get_user_avail_cache_aside(userId2)
    if not user1_data or not user2_data:
        raise HTTPException(status_code=404, detail="One or both users not found")
    
    


