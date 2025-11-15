# When2Meet-As a Microservice

## Description
This project is inspired from When2Meet with the aim to find the best availabilities among two users, availability in this case is series of one hours slots of a user throughout the week. 

## Architecure Overview
The system consists of three services, each having thier own domain and dependencies

1. `user-service`
- Stores user information and thier availabilities in Redis.
- Contains three endpoints:
    - one GET endpoint for fetching a valid user's availabilities
    - one POST endpoint that creates users and their availabilities
    - GET health returns the container/service status along with Redis dependency
2. `availability-service`
- Fetches the availability of each user from user-service
- Computes and returns common intervals across users
- Contains two endpoints:
    - GET endpoint to compute the availabilities between two users
    - get health endpoint returns the status of this service as well as user-service

3. `suggestion-service`
- Uses the common intervals from `availability-service` and factors in whether the users want the first availability, last or a random one
- Meeting duration is currently fixed at an hour duration (will consider adding time duration variability if time persists)
- Has two endpoints:
    - a GET endpoint that takes in the requirements (default is first available) and returns the best interval fitting those requirements.
    - GET health returns the own container status along with the aggregated statuses of `availability-service` and its required dependencies

## Pre-Requisites
```
httpx =0.25.2 
python-dotenv==1.0.0 
Python 3.11
FastAPI 0.104.1
Redis 5.0.1
Pydantic==2.5.0
uvicorn==0.24.0
Docker version 28.4.0, 
Docker Compose version v2.39.2-desktop.1
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
# Testing
1. Start docker compose and all services:
```
docker-compose up --build
```

Manually test the health checks of each service using the commands from the API documentation and checking the formatting conventions.

if a service is unhealthy due to its depedency, it will say so as shown in this example in `user-service`

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
├── CODE_PROVENANCE.md
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
```

