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
2. Add Availability for 2 or more users using:
```
docker-compose exec user-service curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john.doe@example.com",
    "slots": [
          {"day": "monday", "start": "10:00", "end": "11:00"},
          {"day": "tuesday", "start": "14:00", "end": "15:00"}
          {"day": "thursday", "start": "11:00", "end": "12:00"}
        ]
  }'
  ```

  ```
docker-compose exec user-service curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Smith",
    "email": "asmith@example.com",
    "slots": [
          {"day": "monday", "start": "1:00", "end": "2:00"},
          {"day": "tuesday", "start": "14:00", "end": "15:00"}
          {"day": "thursday", "start": "9:00", "end": "10:00"}
        ]
  }'
  ```

If the email IDs are unique*, then the response would be returned with the status code 201 with the required body:
```
{
  "name": "John Doe",
  "email": "john.doe@example.com",
  "slots": [
          {"day": "monday", "start": "10:00", "end": "11:00"},
          {"day": "tuesday", "start": "14:00", "end": "15:00"}
          {"day": "thursday", "start": "11:00", "end": "12:00"}
        ]
  "created_at": "2025-10-27T13:26:00.000000"
}
```


Example with invalid email:
```
docker-compose exec user-service curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Smith",
    "email": "invalid-email"
  }'
  ```

This should return a `400 Bad Request` withe the follwing keys:
```
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "type details"
    }
  ]
}
```
If something went wrong with the server it should return a `500 Internal Server Error`

We can verify that the availabilities exist using the endpoint `GET /users/{user_email}/availability` which returns 200 response with the user availabilities if the user exists

3. For the common availability between two users we can use:
```
docker compose exec availability-service
  curl "http://availability-service:8000/availabilities?users=asmith@example.com&users=john.doe@example.com"
```
If availabilities are present it will return a Status 200 with the common availabilities 
```
{
  "users": [
    "asmith@example.com",
    "john.doe@example.com"
  ],
  "common_slots": [
    {
      "day": "tuesday",
      "start": "14:00",
      "end": "15:00"
    }
  ]
}

```
If no common availabilities are present, it should still return a 200 with an empty set
```
{
  "users": [
    "asmith@example.com",
    "john.doe@example.com"
  ],
  "common_slots": []
}
```

If the users are not present it should return a `400 Bad Request` stating that the user does not exist

4. To get the final availability meeting time suggestion that also uses all services; we can use `suggestion-service`
```
docker compose exec suggestion-service
  curl "http://suggestion-service:8000/suggest?users=asmith@example.com&users=john.doe@example.com&filter=first"

```
If availability exists:(assume filter option defaulted to first)
```
{
  "users": [
    "asmith@example.com",
    "john.doe@example.com"
  ],
  "filter_by": first
  "common_slots": [{
      "day": "tuesday",
      "start": "14:00",
      "end": "15:00"
    }]
}
```

```
{
  "users": [
    "asmith@example.com",
    "john.doe@example.com"
  ],
  "filter_by": "first"
  "common_slots": []
}
```


If no availability exists return 200 with 

```
{
  "users": [
    "asmith@example.com",
    "john.doe@example.com"
  ],
  "filter_by": "first"
  "common_slots": []
}
```


Similar Conventions of status codes will be followed for suggestion-service as availability-service if user does not exist




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

