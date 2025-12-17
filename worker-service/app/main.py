from contextlib import asynccontextmanager
import os
import json
import time
import uuid
import logging
from typing import Optional

import httpx
import aio_pika
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError


SERVICE_NAME = "worker-service"
CASE_HEADER = "Case-ID"

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq/")
QUEUE_NAME = os.getenv("QUEUE_NAME", "meeting_jobs")

SUGGESTION_BASE = os.getenv("SUGGESTION_BASE", "http://suggestion-service:8000")

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler("logs/worker_log.txt", mode="a"), logging.StreamHandler()],
)
logger = logging.getLogger(SERVICE_NAME)


rmq_connection: Optional[aio_pika.RobustConnection] = None
rmq_channel: Optional[aio_pika.RobustChannel] = None
rmq_queue: Optional[aio_pika.RobustQueue] = None


def _short_id(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


async def connect_rabbitmq():
    global rmq_connection, rmq_channel, rmq_queue
    rmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
    rmq_channel = await rmq_connection.channel()
    await rmq_channel.set_qos(prefetch_count=1)
    rmq_queue = await rmq_channel.declare_queue(QUEUE_NAME, durable=True)
    logger.info(f"RabbitMQ connected. Queue ready: {QUEUE_NAME}")


async def close_rabbitmq():
    global rmq_connection
    if rmq_connection:
        await rmq_connection.close()
        logger.info("RabbitMQ connection closed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_rabbitmq()
    if rmq_queue is None:
        raise RuntimeError("RabbitMQ queue is None after connect_rabbitmq()")
    await rmq_queue.consume(process_message)
    logger.info("Worker consumer started.")
    yield
    await close_rabbitmq()


app = FastAPI(root_path="/workers", lifespan=lifespan)


def _cid(request: Request) -> str:
    return getattr(request.state, "case_id", "N/A")


@app.middleware("http")
async def add_case_id(request: Request, call_next):
    case_id = request.headers.get(CASE_HEADER) or _short_id(8)
    request.state.case_id = case_id

    start = time.perf_counter()
    logger.info(f"[{case_id}] IN  {request.method} {request.url.path}")

    response: Response = await call_next(request)

    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers[CASE_HEADER] = case_id
    logger.info(f"[{case_id}] OUT {request.method} {request.url.path} status={response.status_code} ms={elapsed_ms:.2f}")

    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    case_id = _cid(request)
    logger.error(f"[{case_id}] ERROR {request.method} {request.url.path} status={exc.status_code} detail={exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "case_id": case_id,
            "detail": [{"loc": ["internal"], "msg": exc.detail, "type": "http_error"}],
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    case_id = _cid(request)
    details = []
    for err in exc.errors():
        details.append({
            "loc": list(err.get("loc", [])),
            "msg": err.get("msg", "Invalid input"),
            "type": err.get("type", "value_error"),
        })
    logger.error(f"[{case_id}] ERROR {request.method} {request.url.path} status=422 validation_error")
    return JSONResponse(status_code=422, content={"case_id": case_id, "detail": details})


class TaskIn(BaseModel):
    userId1: str
    userId2: str
    preference: Optional[str] = None


async def process_message(message: aio_pika.IncomingMessage):
    async with message.process(requeue=True):
        payload = json.loads(message.body.decode("utf-8"))
        case_id = payload.get("case_id", "N/A")
        job_id = payload.get("job_id", "N/A")

        userId1 = payload.get("userId1")
        userId2 = payload.get("userId2")
        preference = payload.get("preference")

        logger.info(f"[{case_id}] JOB_START job_id={job_id} userId1={userId1} userId2={userId2} preference={preference}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {"userId1": userId1, "userId2": userId2}
                if preference:
                    params["preference"] = preference

                resp = await client.get(
                    f"{SUGGESTION_BASE}/suggestions",
                    params=params,
                    headers={CASE_HEADER: case_id},
                )

            if resp.status_code >= 400:
                logger.error(f"[{case_id}] JOB_ERROR job_id={job_id} suggestion_status={resp.status_code} body={resp.text}")
                raise RuntimeError(f"suggestion-service failed: {resp.status_code}")

            suggestion = resp.json()
            logger.info(f"[{case_id}] JOB_DONE job_id={job_id} suggestion={suggestion}")
            print(f"[{case_id}] JOB_DONE job_id={job_id} suggestion={suggestion}")

        except Exception as e:
            logger.error(f"[{case_id}] JOB_ERROR job_id={job_id} err={e}")
            raise


@app.get("/health")
async def health(request: Request, response: Response):
    case_id = _cid(request)
    status_indicator = "healthy"

    try:
        if rmq_channel is None or rmq_channel.is_closed:
            status_indicator = "unhealthy"
    except Exception:
        status_indicator = "unhealthy"

    response.status_code = status.HTTP_200_OK if status_indicator == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "case_id": case_id,
        "service": SERVICE_NAME,
        "status": status_indicator,
        "dependencies": {
            "rabbitmq": {"status": status_indicator}
        }
    }


@app.post("/tasks", status_code=202)
async def enqueue_task(task: TaskIn, request: Request):
    case_id = _cid(request)
    if rmq_channel is None or rmq_channel.is_closed:
        raise HTTPException(status_code=503, detail="RabbitMQ is unavailable")

    job_id = _short_id(12)
    payload = {
        "case_id": case_id,
        "job_id": job_id,
        "userId1": task.userId1,
        "userId2": task.userId2,
        "preference": task.preference,
    }

    message = aio_pika.Message(
        body=json.dumps(payload).encode("utf-8"),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    await rmq_channel.default_exchange.publish(message, routing_key=QUEUE_NAME)
    logger.info(f"[{case_id}] ENQUEUE job_id={job_id} userId1={task.userId1} userId2={task.userId2}")

    return {"case_id": case_id, "status": "enqueued", "job_id": job_id, "queue": QUEUE_NAME}
