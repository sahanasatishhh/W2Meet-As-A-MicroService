# When2Meet-As a Microservice

## Description
This project is inspired from When2Meet with the aim to find the best availabilities among two users, availability in this case is series of one hours slots of a user throughout the week. 

## Architecure Overview
The system consists of five services, each having their own domain and dependencies
1. `gateway-service`
- Acts as the **single public entrypoint** to the system.
- Forwards client requests to appropriate backend services.
- Hides internal service URLs and ports.
- Implements **simple round-robin load balancing** across multiple replicas of compute services.
- Propagates a shared request ID (`Case-Id`) across downstream services.


2. `user-service`
- Stores user information and their availabilities in Redis.
- Uses **Redis** as a cache and **PostgreSQL** as persistent storage.
- Owns all Redis and database interactions.
- Implements a **cache-aside pattern** for user availability.
- Contains three endpoints:

**Endpoints**
- `POST /users` – create a user and store availability
- `GET /users/{email}` – fetch a user's data (cache-first)
- `GET /user-avail/cache_aside/{email}` – cache-aside read path
- `GET /health` – service health including Redis and PostgreSQL dependencies


3. `availability-service`
- Fetches the availability of each user from user-service
- Computes and returns common intervals across users
- Contains no direct database or Redis access.
- Contains two endpoints:
    - GET endpoint to compute the availabilities between two users
    - get health endpoint returns the status of this service as well as user-service

4. `suggestion-service`
- Uses the common intervals from `availability-service` and factors in whether the users want the first availability, last or a random one
- Meeting duration is currently fixed at an hour duration.

- Has two endpoints:
    - a GET endpoint that takes in the requirements (default is first available) and returns the best interval fitting those requirements.
    - GET health returns the own container status along with the aggregated statuses of `availability-service` and its required dependencies

5. `worker-service` (Async Queue)
- Consumes background jobs from a **RabbitMQ queue**.
- Intended for **non-blocking, post-processing tasks**, such as:
  - Sending meeting confirmations
  - Simulating iCal or email notifications
- Receives and logs the same `Case-Id` for traceability.
- Designed for future extension; **not fully implemented features like calendar invites and message sending**.


## Pre-Requisites
```
httpx =0.25.2 
python-dotenv==1.0.0 
Python 3.11
FastAPI 0.104.1
Redis 5.0.1
Pydantic==2.5.0
uvicorn==0.24.0
Docker==28.4.0
Docker version 28.4.0, 
Docker Compose version v2.39.2-desktop.1
nginx
requests
```

## Installation

**Run this Command**
cd into the project folder
```
docker-compose up --build
```
This will start all the services in a shared docker network. NOTE: please wait until the `api-gateway starts running up since it would combine all the services and become the singular point of reference for the microservices`

## Usage Instructions

**Health Checks**
for each service name like `user-service`,`availability-service`,`suggestion-service` we can check the health endpoint to check the status of the service endpoint
```
docker compose exec service-name \
curl http://localhost:8000/health
```
Each service would return a response with an example format:

```
{"case_id": some-case-id,
  "service": "service-name",
  "status": "healthy",
  "dependencies": {
    "dependent-service": {
      "status": "healthy",
      "response_time_ms": 15
    }
  }
}
```
if the service state is unhealthy it would return a 503 response (Service Unavailable)
## API Documentation

1. **For user-service:**
 ```
docker-compose exec user-service \curl http://localhost:8000/users/health
```
**Response Format:**
```
{"case_id": some-case-id,
  "service": "user-service",
  "status": "healthy",
  "dependencies": {
    "redis": {
      "status": "healthy",
      "response_time_ms": 10
    }
  }
}
```

2. **For availability-service:**
 ```
docker-compose exec availability-service \curl http://localhost:8000/availability/health
```
**Response Format:**
```
{"case_id": some-case-id,
  "service": "availability-service",
  "status": "healthy",
  "dependencies": {
    "user-service": {
      "status": "healthy",
      "response_time_ms": 10
    }
  }
}

```
3. **For suggestion-service:**
 ```
docker-compose exec suggestion-service \curl http://localhost:8000/suggestion/health
```
**Response Format:**
```
{"case_id": some-case-id,
  "service": "suggestion-service",
  "status": "healthy",
  "dependencies": {
    "availability-service": {
      "status": "healthy",
      "response_time_ms": 10
    }
  }
}
```
4. **For gateway-service that uses nginx:**
 ```
docker-compose up -d nginx
docker-compose ps
docker-compose logs --no-color --tail=50 nginx
docker-compose exec nginx nginx -t
curl http://localhost:8080/health
```
**Response Format**
``ok``

5. **For worker-service:**
 ```
docker-compose exec user-service \curl http://localhost:8000/worker/health
```
**Response Format:**
```
{"case_id": some-case-id,
  "service": "worker-service",
  "status": "healthy",
  "dependencies": {
    "redis": {
      "status": "healthy",
      "response_time_ms": 10
    }
  }
}
```
**For each service: **
```
curl http://localhost:8080/{user/availability/suggestion/worker}/health
```
would return the appropriate healthcheck response which also verifies routing through the API gateway

**Example external endpoints**
```
- `POST /api/users`: forwards to one `user-service` instance
- `GET /api/users/{email}`: forwards to `user-service`
- `GET  /api/availability/common_availabilities`:  forwards to one of the **availability-service replicas**:
- `GET /api/suggestions`: forwards to one of the **suggestion-service replicas**

In code, the gateway maintains lists such as:

AVAILABILITY_BACKENDS = [
    "http://availability-service-1:8000",
    "http://availability-service-2:8000",
]

SUGGESTION_BACKENDS = [
    "http://suggestion-service-1:8000",
    "http://suggestion-service-2:8000",
]
```

## ENDPOINTS BY SERVICE (THROUGH THE API GATEWAY)
Base Gateway URL: `http://localhost:8080`

| Service                  | Method | Gateway Path                            | Internal Path                     | Purpose                               | Notes                               |
| ------------------------ | ------ | --------------------------------------- | --------------------------------- | ------------------------------------- | ----------------------------------- |
| **User Service**         | GET    | `/users/health`                         | `/health`                         | Health check for user-service         | Checks Redis + Postgres             |
| User Service             | POST   | `/users/users`                          | `/users`                          | Create a user                         | Persists to Postgres + writes Redis |
| User Service             | GET    | `/users/user-avail/cache-aside/{email}` | `/user-avail/cache-aside/{email}` | Fetch user availability (cache-aside) | Redis → Postgres fallback           |
| **Availability Service** | GET    | `/availability/health`                  | `/health`                         | Health check for availability-service | Calls user-service health           |
| Availability Service     | GET    | `/availability/availabilities`          | `/availabilities`                 | Compute common availability           | Requires `userId1`, `userId2`       |
| **Suggestion Service**   | GET    | `/suggestion/health`                    | `/health`                         | Health check for suggestion-service   | Calls availability-service health   |
| Suggestion Service       | GET    | `/suggestion/suggestions`               | `/suggestions`                    | Generate meeting suggestions          | Uses preferences + common slots     |
| **Worker Service**       | GET    | `/worker/health`                        | `/health`                         | Health check for worker-service       | Checks RabbitMQ connectivity        |
| Worker Service           | POST   | `/worker/tasks`                         | `/tasks`                          | Enqueue async suggestion job          | Publishes to RabbitMQ               |
| **RabbitMQ**             | —      | —                                       | `meeting_jobs` queue              | Async job transport                   | Consumed by worker-service          |


## Project Structure

```
W2MEET-AS-A-MICROSERVICE/
├── README.md
├── SYSTEM_ARCHITECTURE.md
├── architecture-diagram.png
├── docker-compose.yml
├── KGD.md
├-- .env
├── initdb/
│   ├── 001_schema.sql
├── user-service/
│   ├── app/
│       |____ main.py
|   |___logs/
|         |_____worker_log.txt
│   ├── requirements.txt
│   ├── Dockerfile
│
├── availability-service/
│   ├── app/
│       |_____ main.py
|   |___logs/
|         |_____worker_log.txt
│   ├── requirements.txt
│   ├── Dockerfile
│
└── suggestion-service/
│   ├── app/
│       |_____ main.py
|   |_____logs/
|           |_____suggest_log.txt
│    ├── requirements.txt
│    ├── Dockerfile
│
└── worker-service/
│   ├── app/
│       |_____ main.py
|   |___logs/
|         |_____worker_log.txt
│    ├── requirements.txt
│    ├── Dockerfile
│
└── gateway-service/
│   ├── nginx.conf
├── tests/
│   ├── _helpers.sh
│   ├── test_user_service.sh
│   ├── test_availability_service.sh
│   ├── test_suggestion_service.sh
│   ├── test_worker_service.sh
│   └── test_error_handling.sh

```

# Testing
1. Start docker compose and all services:
```
docker-compose up --build
```

Manually test the health checks of each service using the commands from the API documentation and checking the formatting conventions.

if a service is unhealthy due to its dependency, it will say so as shown in this example in `user-service`

```
{
  "service": "user-service",
  "status": "unhealthy",
  "dependencies": {
    "redis": {
      "status": "unhealthy",
      "response_time_ms": 30
    }
  }
}
```


## Example Workflow for each service 

1. Create two users, with their availabilities and services

2. Call `suggestions-service`

3. Expected return value:


## Testing files
There is a testing file for each service that tests this workflow -

to run for example `test_worker_service` you would:
```
sed -i '' $'s/\r$//' test_worker_service.sh
chmod +x test_worker_service.sh
./test_worker_service.sh
```
They just check basic functionalities and not edge cases for the entire workflow. For example user-service does not check update and delete cases - only checks insert and get wrt cache_aside.
