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
import logging



app = FastAPI(root_path="/availabilities")

# this is an example that you can use
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/cache_log.txt", mode="a"),  # write to file
        logging.StreamHandler()  # also show in console
    ]
)

logger = logging.getLogger("availability-service")



# External user service base (for validating userId on create/update)
USER_SERVICE_BASE = os.getenv("USER_SERVICE_BASE", "http://user-service:8000")


async def add_case_id(request: Request, call_next):
    case_id = request.headers.get("Case-ID", str(uuid.uuid4()))
    request.state.case_id = case_id

    logger.info(f"[{case_id}] Request started - Method={request.method} Path={request.url.path}")
    #Pass the request forward to the next middleware in the nextservice chain
    response = await call_next(request)
    response.headers["Case-ID"] = case_id
    logger.info(f"[{case_id}] Request completed - Status={response.status_code}")
    return response

#for healthcheck it should be able to check 200? if the user-srvice returns a 200 it should return status "heealtthy" i assume so it would be a similar version of try and execption'
# Endpoints
@app.get("/health")
async def health_check(response: Response, request: Request):
    case_id = getattr(request.state, "case_id", "N/A")
    service="availability-service"
    start_time=time.perf_counter()
    status_indicator="healthy"
    dependencies={}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"Case-ID": case_id}
            resp = await client.get(f"{USER_SERVICE_BASE}/health", headers=headers)
        if resp.status_code==200:
            dependencies["user-service"]={"status":resp.json().get("status"),"response_time_ms":(time.perf_counter()-start_time)*1000}
        else:
            # it is not 200 likely 504
            dependencies["user-service"]={"status":resp.json().get("status"),"response_time_ms":(time.perf_counter()-start_time)*1000}
            status_indicator="unhealthy"
            logging.error(f"[{case_id}] HEALTH CHECK: user-service is unhealthy with status code {resp.status_code}")
    except Exception as e:
        dependencies["user-service"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
        status_indicator="unhealthy"
        logging.error(f"[{case_id}] HEALTH CHECK: user-service is unhealthy with exception {e}")
    
    if status_indicator=="unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logging.error(f"[{case_id}] HEALTH CHECK: availability-service is unhealthy")
    else:
        response.status_code = status.HTTP_200_OK
        logging.info(f"[{case_id}] HEALTH CHECK: availability-service is healthy")
    
    return {"service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }


