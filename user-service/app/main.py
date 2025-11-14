from fastapi import FastAPI, HTTPException, Response,status
from pydantic import BaseModel, EmailStr
import redis
import httpx
import os
import uuid
from datetime import datetime
from fastapi.exceptions import RequestValidationError
from fastapi import Request
from fastapi.responses import JSONResponse
import time



app = FastAPI(root_path="/users")
 

# Redis connection
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)



# Endpoints
@app.get("/health")
async def health_check(response: Response):
    start_time = time.perf_counter()

    service="user-service"
    status_indicator="healthy"
    dependencies = {}
    try:
        pong=redis_client.ping()
        if pong:
            dependencies["redis"]={"status":"healthy","response_time_ms":(time.perf_counter()-start_time)*1000}
            status_indicator="healthy"
        if not pong:
            dependencies["redis"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
            status_indicator="unhealthy"
    except Exception as e:
        dependencies["redis"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
        status_indicator="unhealthy"
    if status_indicator=="healthy":
        return {"service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }
    else:
        Response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }

