import random
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
from fastapi.exceptions import HTTPException
from availability_service.app.main import get_common_avails

app = FastAPI(root_path="/tasks")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": [
                {
                    "loc": ["internal"],
                    "msg": exc.detail,
                    "type": "http_error"
                }
            ]
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = list(err.get("loc", []))
        typ = err.get("type", "value_error")
        msg = err.get("msg", "Invalid input")
        details.append({'loc': loc, "msg": msg, "type": typ})

    return JSONResponse(status_code=400, content={"detail": details})
    # 400 response


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
    
    availabitilies_and_preferences=get_common_avails(userId1,userId2)

    if not availabitilies_and_preferences:
        raise HTTPException(status_code=404, detail="One or both users not found")
    

    user2_preference = availabitilies_and_preferences.get("user2preference","first")
    user1_preference = availabitilies_and_preferences.get("user1preference","first")
    
    if user1_preference==user2_preference:
        preferred_avails = availabitilies_and_preferences.get("common_availabilities",[])
        if len(preferred_avails)>0:
            if user1_preference=="first":
                return [preferred_avails[0], preferred_avails[0]+1] 
            elif user1_preference=="last":
                return [preferred_avails[-1],preferred_avails[-1]+1]
            else:
                #has to be random
                rand_avail=random.choice(preferred_avails)
                return [rand_avail, rand_avail+1]
        else:
            return []
    else:
        #different preferences
        


