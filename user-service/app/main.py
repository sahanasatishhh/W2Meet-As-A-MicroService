from fastapi import FastAPI, HTTPException, Query, Response,status
from pydantic import BaseModel, EmailStr
import redis
import os
import uuid
from datetime import datetime
from fastapi.exceptions import RequestValidationError
from fastapi import Request
from fastapi.responses import JSONResponse
import time
from db import init_db,close_db_connection,engine
from contextlib import asynccontextmanager
import logging
import json
from sqlalchemy import text

os.makedirs("logs", exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    close_db_connection()
    

app = FastAPI(root_path="/users", lifespan=lifespan)

# this is an example that you can use
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/user_log.txt", mode="a"),  # write to file
        logging.StreamHandler()  # also show in console
    ]
)

logger = logging.getLogger("user-service")



@app.middleware("http")
async def add_case_id(request: Request, call_next):
    case_id = request.headers.get("Case-ID", str(uuid.uuid4()))
    request.state.case_id = case_id
    perf=time.perf_counter()
    logger.info(
        f"[{case_id}] Request started - "
        f"Method={request.method} Path={request.url.path}"
    )

    # Let FastAPI process the request
    response = await call_next(request)

    # Add the correlation ID back to response headers
    response.headers["Case-ID"] = case_id

    logger.info(
        f"[{case_id}] Request completed - "
        f"Status={response.status_code}, Time taken={(time.perf_counter()-perf)*1000:.2f} ms"
    )

    return response

 
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    case_id = getattr(request.state, "case_id", "N/A")

    details = []
    for err in exc.errors():
        loc = list(err.get("loc", []))
        typ = err.get("type", "value_error")
        msg = err.get("msg", "Invalid input")
        details.append({'loc': loc, "msg": msg, "type": typ})

    return JSONResponse(status_code=400, content={"case_id": case_id,"detail": details})
    # 400 response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    case_id = getattr(request.state, "case_id", "N/A")
    return JSONResponse(
        status_code=exc.status_code,
        content={ "case_id": case_id,
            "detail": [
                {
                    "loc": ["internal"],
                    "msg": exc.detail,
                    "type": "http_error"
                }
            ]
        }
    )

# Redis connection
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

class UserAvail(BaseModel):
    id: int
    email: EmailStr
    availabilities: dict
    preferences: str = 'first'
    created_at: datetime = datetime.now()


# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    availabilities: dict
    preferences: str = 'first'

# Endpoints
@app.get("/health")
async def health_check(response: Response, request: Request):
    case_id = getattr(request.state, "case_id", "N/A")
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
        logging.error(f"[{case_id}] Redis health check failed: {e}")
        status_indicator="unhealthy"

    try:
        with engine.connect() as conn:
            postgres_check= conn.execute(text("SELECT 1"))
            if postgres_check:
                dependencies["postgresql"]={"status":"healthy","response_time_ms":(time.perf_counter()-start_time)*1000}
                status_indicator="healthy"
            else:
                dependencies["postgresql"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
                status_indicator="unhealthy"
    except Exception as e:
        dependencies["postgresql"]={"status":"unhealthy","response_time_ms":(time.perf_counter()-start_time)*1000}
        logging.error(f"[{case_id}] PostgreSQL health check failed: {e}")
        status_indicator="unhealthy"

    if status_indicator=="healthy":
        logging.info(f"[{case_id}] HEALTH Service healthy: {dependencies}")
        return {"service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logging.error(f"[{case_id}] HEALTH Service unhealthy: {dependencies}")
        return {"service":service,
            "status": status_indicator,
            "dependencies": dependencies
            }
# Configure logging



@app.post("/users", status_code=201)
async def create_user(user: UserCreate, request: Request):
    # Implementation here
    case_id = getattr(request.state, "case_id", "N/A")

    created_at=datetime.now()
    user_data={"email":user.email,"availabilities":user.availabilities,"preferences":user.preferences,"created_at":created_at}
    try:
        #set iaof not exist
        #if it was already there, created will be false
        #setnx does not overwrite

        redis_client.hset(f"user:{user.email}",mapping=user_data)
        with engine.connect() as conn:
            txt=text(
                f"INSERT INTO USERAVAIL (email, availabilities, preferences, created_at) "
                f"VALUES ('{user.email}', '{json.dumps(user.availabilities)}', "
                f"'{user.preferences}', '{created_at}') "
                f"ON CONFLICT (email) DO NOTHING"
            )
            conn.execute(txt)
        logging.info(f" [{case_id}] USER CREATE: User created with email: {user.email}")
        return user_data
    except Exception:
        logging.error(f" [{case_id}] USER CREATE: Failed to create user with email: {user.email}")
        raise HTTPException(status_code=500, detail="Failed to create user")

@app.get("/users/{email_id}")
async def get_user(email_id: str, request: Request):
    # Implementation here
    case_id = getattr(request.state, "case_id", "N/A")
    data = redis_client.hgetall(f"user:{email_id}")
    if not data:
        
        with engine.connect() as conn:
            txt=text(f"SELECT * FROM USERAVAIL WHERE email='{email_id}'")
            res=conn.execute(txt)
            rows=res.fetchall()
            if len(rows)==0:
                raise HTTPException(status_code=404, detail="User Not Found")
            user_record=rows[0]
            data={"email":user_record.email,"availabilities":json.loads(user_record.availabilities),"preferences":user_record.preferences,"created_at":user_record.created_at}
            #populate redis cache
            redis_client.hset(f"user:{email_id}",mapping=data)
            logging.info(f"[{case_id}] USER GET: User with email: {email_id} fetched from database and cached in Redis")
            return data
        logging.info(f"[{case_id}] USER GET: User with email: {email_id} not found in Redis cache or Database ")
        raise HTTPException(status_code=404, detail="User Not Found")
    
    logging.info(f"[{case_id}] USER GET: User with email: {email_id} fetched from Redis cache")
    return data


@app.put("/users/{email_id}")
async def update_user(email_id: str, user: UserCreate, request: Request):
    # Implementation here
    case_id = getattr(request.state, "case_id", "N/A")
    existing_user = await get_user(email_id, request)

    if not existing_user:
        logging.info(f"[{case_id}] USER UPDATE: User with email: {email_id} not found for update")
        raise HTTPException(status_code=404, detail="User Not Found")
    updated_user = {
        "email": user.email,
        "availabilities": user.availabilities,
        "preferences": user.preferences,
        "created_at": existing_user["created_at"]
    }
    redis_client.hset(f"user:{email_id}", mapping=updated_user)
    logging.info(f"[{case_id}] USER UPDATE: User with email: {email_id} updated in Redis")

    with engine.connect() as conn:
        txt = text(
            "UPDATE USERAVAIL "
            "SET availabilities = :availabilities, preferences = :preferences "
            "WHERE email = :email"
        )
        conn.execute(txt, {
            "email": email_id,
            "availabilities": json.dumps(user.availabilities),
            "preferences": user.preferences,
        })

        logging.info(f"[{case_id}] USER UPDATE: User with email: {email_id} updated")
    logging.info(f"[{case_id}] USER UPDATE: User with email: {email_id} updated in Database")

    return await get_user(email_id,request)

@app.delete("/users/{email_id}", status_code=204)
async def delete_user(email_id: str, request: Request):
    # Implementation here
    case_id = getattr(request.state, "case_id", "N/A")
    existing_user = await get_user(email_id, request)
    if not existing_user:
        logging.info(f"[{case_id}] USER DELETE: User with email: {email_id} not found for deletion")
        raise HTTPException(status_code=404, detail="User Not Found")
    redis_client.delete(f"user:{email_id}")
    logging.info(f"[{case_id}] USER DELETE: User with email:{email_id} deleted from Redis")

    with engine.connect() as conn:
        txt=text(f"DELETE FROM USERAVAIL where email='{email_id}'")
        conn.execute(txt)
        logging.info(f"[{case_id}] USER DELETE: User with email:{email_id} deleted from Database")
    return Response(status_code=204)

@app.get("/user-avail/cache-aside")
async def get_user_avail_cache_aside(request: Request, user1email:str= Query()):
    case_id = getattr(request.state, "case_id", "N/A")
    logging.info("CACHE ASIDE: request received for symbols %s", user1email)
    #  check redis for the kv pair

    try:
        cached_data = redis_client.get(f"cache_aside_{user1email.upper()}")
        if cached_data:
            logging.info(f"[{case_id}] CACHE ASIDE: CACHE HIT with key cache_aside_{user1email.upper()} served from Redis {cached_data}")
            return json.loads(cached_data)
        else:
            logging.info(f"[{case_id}] CACHE ASIDE: CACHE MISS with key cache_aside_{user1email.upper()} fetching from provider")
            #default base is USD
            try:
                with engine.connect() as conn:
                    txt=text(f"SELECT * FROM USERAVAIL WHERE email='{user1email}'")
                    res=conn.execute(txt)
                    rows=res.fetchall()
                    if not rows:
                        logger.info(f"[{case_id}] CACHE_ASIDE 404 email={user1email}")
                        raise HTTPException(status_code=404, detail=f"User {user1email} not found in database")
                    data = {
                    "email": rows.email,
                    "preferences": rows.preferences,
                    "availabilities": json.loads(rows.availabilities),  # IMPORTANT
                    "created_at": rows.created_at.isoformat() if rows.created_at else None,
                    }
                    logging.info(f"[{case_id}] CACHE ASIDE: successfully fetched fresh data from database for cache_aside_{user1email.upper()}")
                    ttl_seconds = int(os.getenv("TTL_SECONDS", 3300))
                    redis_client.setex(f"cache_aside_{user1email.upper()}", ttl_seconds, json.dumps(data))
                    logging.info(f"[{case_id}] CACHE ASIDE: WRITE CACHE with cache_aside_{user1email.upper()} stored with TTL={ttl_seconds}s")
                    return data
            except HTTPException:
                raise
                #no loggin metnioned?
    except Exception as e:
        logger.error(f"[{case_id}] CACHE_ASIDE ERROR email={user1email} err={e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
