from fastapi import FastAPI, HTTPException, Query, Request, Response,status
from fastapi.exceptions import RequestValidationError
from typing import Optional, List
import httpx
import os
import uuid
from fastapi.responses import JSONResponse
import time
import logging


app = FastAPI(root_path="/availabilities")
USER_SERVICE_BASE = os.getenv("USER_SERVICE_BASE", "http://user-service:8000")
WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/availability_log.txt", mode="a"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("availability-service")

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
    case_id = getattr(request.state, "case_id", "N/A")
    logger.error(
        f"[{case_id}] ERROR {request.method} {request.url.path} "
        f"status={exc.status_code} detail={exc.detail}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "case_id": case_id,
            "detail": [{"loc": ["internal"], "msg": exc.detail, "type": "http_error"}],
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    case_id = getattr(request.state, "case_id", "N/A")

    details = []
    for err in exc.errors():
        loc = list(err.get("loc", []))
        typ = err.get("type", "value_error")
        msg = err.get("msg", "Invalid input")
        details.append({'loc': loc, "msg": msg, "type": typ})
    logger.error(
    f"[{case_id}] ERROR {request.method} {request.url.path} "
       f"status=422 validation_error"
    )


    return JSONResponse(status_code=400, content={"case_id": case_id,"detail": details})
    # 400 response



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
            logger.error(f"[{case_id}] ERROR CALL user-service endpoint=/health status={resp.status_code}")
    except Exception as e:
        status_indicator = "unhealthy"
        dependencies["user-service"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"[{case_id}] ERROR CALL user-service endpoint=/health status=unreachable error={e}")
    
    if status_indicator=="unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response.status_code = status.HTTP_200_OK
        logging.info(f"[{case_id}] HEALTH CHECK: availability-service is healthy")
    
    return {"case_id": case_id,
            "service":service,
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
async def get_common_avails(
    request: Request,
    userId1: Optional[str] = Query(None),
    userId2: Optional[str] = Query(None),
):
    case_id = getattr(request.state, "case_id", "N/A")
    logger.info(f"[{case_id}] Computing common availability for userId1={userId1}, userId2={userId2}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            user1_resp = await client.get(
                f"{USER_SERVICE_BASE}/user-avail/cache-aside",
                params={"user1email": userId1},
                headers={"Case-ID": case_id},
            )
            user2_resp = await client.get(
                f"{USER_SERVICE_BASE}/user-avail/cache-aside",
                params={"user1email": userId2},
                headers={"Case-ID": case_id},
            )
    except Exception as e:
        logger.error(f"[{case_id}] ERROR CALL user-service status=unreachable error={e}")
        raise HTTPException(status_code=503, detail="User service is unavailable")

    if user1_resp.status_code == 404 or user2_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="One or both users not found")
    if user1_resp.status_code >= 400 or user2_resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="User service error")

    u1 = user1_resp.json()
    u2 = user2_resp.json()

    user1_avails = u1.get("availabilities", {})
    user2_avails = u2.get("availabilities", {})

    common = compute_common_availability(request, [user1_avails, user2_avails])

    return {
        "common_availabilities": common,
        "user1preference": u1.get("preferences", "first"),
        "user2preference": u2.get("preferences", "first"),
    }
