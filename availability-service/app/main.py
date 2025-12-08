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
from user_service.app.main import get_user_avail_cache_aside


app = FastAPI(root_path="/availabilities")


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

weekdays = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    ]

def compute_common_availability(request:Request,avails_list: List[dict]) -> dict:
    """
    Computes intersection across ALL users which is inherrently common availabilities
    """
    case_id = getattr(request.state, "case_id", "N/A")

    if not avails_list:
        logging.error(f"[{case_id}] ERROR COMPUTING AVAILABILITIES: No users")
        return {day: [] for day in weekdays}

    common = {day: set(range(24)) for day in weekdays}

    for av in avails_list:
        for day in weekdays:
            user_hours = set(av.get(day, []))
            common[day] = common[day].intersection(user_hours) # if no intersection it would sreturn an empty set

    # Convert sets back to sorted lists
    return {day: sorted(list(hours)) for day, hours in common.items()}


@app.get("/availabilities")
async def get_common_avails(request: Request, userId1: Optional[str] = Query(None, description="User ID to get common availability for"),
                          userId2: Optional[str] = Query(None, description="Second User ID to get common availability for")):
    """
    Essentially first computes a user_Avail list and uses a helper called compute_common_availbilty to return the intersection 
    """
    case_id = getattr(request.state, "case_id", "N/A")
    user1_data= await httpx.AsyncClient().get(f"{USER_SERVICE_BASE}/user-avail/cache_aside/{userId1}")
    user2_data=  await httpx.AsyncClient().get(f"{USER_SERVICE_BASE}/user-avail/cache_aside/{userId2}")
    if not user1_data or not user2_data:
        logging.error(f"[{case_id}] GET AVAILABITLITIES: One or both users not found: userId1={userId1}, userId2={userId2}")
        raise ValidationError(f"One or both users not found: userId1={userId1}, userId2={userId2}")
    avails=[]
    user1_avails = user1_data.get("availabilities", [])
    user2_avails = user2_data.get("availabilities", [])
    if user1_avails is None or user2_avails is None:
        avails_dict = {day: [] for day in weekdays}
        avails.append(avails_dict)
    else:
        avails.append(user1_avails)
        avails.append(user2_avails)
    common=compute_common_availability(avails)
    logging.info(f"[{case_id}] GET AVAILABITLITIES: Found {len(common)} common availabilities for userId1={userId1} and userId2={userId2}")

    return {'common_availabilitiy':common,"user1preference":user1_data.get("preferences"),"user2preference":user2_data.get("preferences")}