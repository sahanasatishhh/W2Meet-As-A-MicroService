import random
from fastapi import FastAPI, HTTPException, Query, Request, Response,status
from fastapi.exceptions import RequestValidationError
from typing import Optional, List
import httpx
import os
import uuid
from fastapi.responses import JSONResponse
import time
from fastapi.exceptions import HTTPException
import requests
import logging

app = FastAPI(root_path="/tasks")

# External user service base (for validating userId on create/update)
AVAIL_BASE = os.getenv("AVAIL_BASE", "http://availability-service:8000")

os.makedirs("logs", exist_ok=True)

# this is an example that you can use
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/suggest_log.txt", mode="a"),  # write to file
        logging.StreamHandler()  # also show in console
    ]
)



logger = logging.getLogger("suggestion-service")


@app.middleware("http")
async def add_case_id(request: Request, call_next):
    case_id = request.headers.get("Case-ID", str(uuid.uuid4()))
    request.state.case_id = case_id
    perf=time.perf_counter()
    logger.info(f"[{case_id}] Request started - Method={request.method} Path={request.url.path}")
    #Pass the request forward to the next middleware in the nextservice chain
    response = await call_next(request)
    response.headers["Case-ID"] = case_id
    logger.info(f"[{case_id}] Request completed - Status={response.status_code}, , Time taken={(time.perf_counter()-perf)*1000:.2f} ms")
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    case_id = getattr(request)
    logger.error(
            f"[{case_id}] ERROR {request.method} {request.url.path} "
            f"status={exc.status_code} detail={exc.detail}"
        )    
    return JSONResponse(
            status_code=exc.status_code,
            content={
                "case_id": case_id,
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
    case_id = getattr(request.state, "case_id", "N/A")
    logger.error(
        f"[{case_id}] ERROR {request.method} {request.url.path} "
        f"status=422 validation_error"
    )
    details = []
    for err in exc.errors():
        loc = list(err.get("loc", []))
        typ = err.get("type", "value_error")
        msg = err.get("msg", "Invalid input")
        details.append({'loc': loc, "msg": msg, "type": typ})

    return JSONResponse(status_code=400, content={"case_id":case_id,"detail": details})
    # 400 response

# Endpoints
@app.get("/health")
async def health_check(request:Request,response: Response):
    cid=getattr(request.state, "case_id", "N/A")
    service="suggestion-service"
    start_time=time.perf_counter()
    status_indicator="healthy"
    dependencies={}
    try:
        resp= await httpx.AsyncClient(timeout=5.0).get(f"{AVAIL_BASE}/health",headers={"Case-ID":cid})
        if resp.status_code==200:
            dependencies["availability-service"]={"status":resp.json().get("status","unknown"),"response_time_ms":(time.perf_counter()-start_time)*1000}
        else:
            # it is not 200 likely 504
            dependencies["availability-service"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
            status_indicator="unhealthy"
    except Exception as e:
        dependencies["availability-service"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
        status_indicator="unhealthy"
    
    if status_indicator=="unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response.status_code = status.HTTP_200_OK
    
    return {"case_id":cid,
        "service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }
def pick_slot(common_hours: List[int], pref: str) -> Optional[List[int]]:
    if not common_hours:
        return None
    if pref == "first":
        h = common_hours[0]
    elif pref == "last":
        h = common_hours[-1]
    else:
        h = random.choice(common_hours)
    return [h, h + 1]

@app.get("/suggestions")
async def get_suggestions(request:Request,userId1: Optional[str] = Query(None, description="User ID to get suggestions for"),
                          userId2: Optional[str] = Query(None, description="Second User ID to get suggestions for")):
    case_id = getattr(request.state, "case_id", "N/A")
    logger.info(f"[{case_id}] Computing suggestions for userId1={userId1}, userId2={userId2}")
    try:
        get_common_avails=await httpx.AsyncClient(timeout=10.0).get(f"{AVAIL_BASE}/common_availabilities", params={"userId1":userId1,"userId2":userId2}, headers={"CASE-ID":case_id})
    except Exception as e:
        logger.error(f"[{case_id}] availability-service unreachable: {e}")
        raise HTTPException(status_code=503, detail="Availability service is unavailable")

    if get_common_avails.status_code == 404:
        raise HTTPException(status_code=404, detail="One or both users not found")
    if get_common_avails.status_code >= 400:
        raise HTTPException(status_code=502, detail="Availability service error")


    availabitilies_and_preferences=get_common_avails.json()
    user2_preference = availabitilies_and_preferences.get("user2preference","first")
    user1_preference = availabitilies_and_preferences.get("user1preference","first")

    if not availabitilies_and_preferences:
        return {"case_id": case_id, "suggestions": []}
    
    if user1_preference==user2_preference:
        slot=pick_slot(availabitilies_and_preferences.get("common_availabilities",[]),user1_preference)
        return {"case_id": case_id, "suggestions": [slot] if slot else []}
    else:
        #if its unequal preferences we return one from each preference if possible
        #different preferences

        suggestions=[]
        common_avails = availabitilies_and_preferences.get("common_availabilities",[])
        s1 = pick_slot(common_avails, user1_preference)
        s2 = pick_slot(common_avails, user2_preference)

        suggestions = []
        if s1:
            suggestions.append(s1)
        if s2 and s2 != s1:
            suggestions.append(s2)

        return {"case_id": case_id, "suggestions": suggestions}