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


1. `user-service`
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


2. `availability-service`
- Fetches the availability of each user from user-service
- Computes and returns common intervals across users
- Contains no direct database or Redis access.
- Contains two endpoints:
    - GET endpoint to compute the availabilities between two users
    - get health endpoint returns the status of this service as well as user-service

3. `suggestion-service`
- Uses the common intervals from `availability-service` and factors in whether the users want the first availability, last or a random one
- Meeting duration is currently fixed at an hour duration.

- Has two endpoints:
    - a GET endpoint that takes in the requirements (default is first available) and returns the best interval fitting those requirements.
    - GET health returns the own container status along with the aggregated statuses of `availability-service` and its required dependencies
4. `worker-service` (Async Queue)
- Consumes background jobs from a **RabbitMQ queue**.
- Intended for **non-blocking, post-processing tasks**, such as:
  - Sending meeting confirmations
  - Simulating iCal or email notifications
- Receives and logs the same `Case-Id` for traceability.
- Designed for future extension; **not fully implemented yet**.


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
This will start all the services in a shared docker network

## Usage Instructions

**Health Checks**
for each service name like `user-service`,`availability-service`,`suggestion-service` we can check the health endpoint to check the status of the service endpoint
```
docker compose exec service-name \
curl http://localhost:8000/health
```
Each service would return a response with an example format:

```
{
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
docker-compose exec user-service \curl http://localhost:8000/health
```
**Response Format:**
```
{
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
docker-compose exec availability-service \curl http://localhost:8000/health
```
**Response Format:**
```
{
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
docker-compose exec suggestion-service \curl http://localhost:8000/health
```
**Response Format:**
```
{
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

## Project Structure

```
W2MEET-AS-A-MICROSERVICE/
├── README.md
├── SYSTEM_ARCHITECTURE.md
├── architecture-diagram.png
├── docker-compose.yml
│
├── user-service/
│   ├── app/
│       |____ main.py
│   ├── requirements.txt
│   ├── Dockerfile
│
├── availability-aggregator/
│   ├── app/
│       |_____ main.py
│   ├── requirements.txt
│   ├── Dockerfile
│
└── suggestion-service/
│   ├── app/
│       |_____ main.py
│    ├── requirements.txt
│    ├── Dockerfile
│
└── worker-service/
│   ├── app/
│       |_____ main.py
│    ├── requirements.txt
│    ├── Dockerfile
│
└── gateway-service/
│   ├── nginx.conf
```

