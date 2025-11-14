# W2Meet-As-A-MicroService

System Purpose:
Think When2Meet but more backend focused that allows the users to create and store accounts, their availabilities and computing common meeting times across users (free intervals). In this case, the time intervals and availabilities are in **one-hour slots**

Goal:
Maintain architecture that can be scaled to calendar APIs and OAuth if possible

## Service Boundaries

`user-service`
1. Stores the record of unique identifiers for each user alongside their availabilities for the list (2D arrays)
2. Stores and accesses this data in Redis
3. Has GET and POST functionality to create and retrieve users and if it exists, their availabilities using `GET users/{emailid}/availability`.


**Reason for this Service**
This way of storing users would ensure that all data and redis related interactions are done through this service.

`availability-service`
1. Fetches availability for multiple users from `user-service`
2. Computes and returns the common availability across the listed users
3. Health endpoint would return the health of itself and the user-service due to its dependency (dependency should imply health checks of the other service)
4. There would be a GET endpoint to get the availabilities of the two users and find common intervals between the availabilities.


**Reason**
Just to be able to perform computation separate from the service endpoints so that I can make sure the algorithm works aside from potential service endpoint issues


`suggestion-service`
1. Calls the `availability-service` to get common intervals between two users
2. Sort them based on requirement: whether we want the first available slot, the last one, or any random one.
3. Health endpoint would return the health of itself and the health of `availability-service` 
4. There would be a GET endpoint to suggest the intervals based on these parameters and return the best slot that fits the requirements


**Reason**
This logic is independent of returning common interval slots and this way filtering can be testing independently


## Data Flow
**Add User Availability:**
1. Two users would create and store their unique identifiers (email) and availabilities via a POST endpoint for user-service.
2. The necessary requirements for the user are name and email, (since a user could be unavailable for an entire week, thats the default)
3. Availability is stored in redis

**Compute Common Availability (user calls the get endpoint for common availabilities):**
1. Use the unique identifiers of the users ( email) to get their availabilities using the GET user-availabilities endpoint from user service.
2. This endpoint would be called for each user.
3. Find the  and return common intersection between the two slots else return None

**Give Suggestions**
1. User would ideally call this GET endpoint of this service with their options (like duration in minutes, do they want the first available one or the last one or a random one) (default is the first available interval)
2. This service calls availability-service to get the availabilities
3. Returns the interval that matches the requirement

Only user-service interacts with Redis; other services rely entirely on HTTP communication as required in Notion documentation (If the service depends on other services, makes HTTP requests to check their health)

## Communication Patterns


- `user-service/health`
    - Pings and returns Redis latency/status
- `availability-service/health`
    - Calls `user-service\health` and returns its status along with its own service status
- `suggestion-service/health`
    - Calls and returns `suggestion-service/health` and returns its status along with `availability-service/health` endpoint status (meaning that service's status along with its dependencies' statuses)

## Technology Stack

**Backend:**
- httpx==0.25.2 (service to service communications via httpx put get)
- python-dotenv==1.0.0 (for secure Port numbers, etc)
- Python 3.11 (Main Preferred Choice because of compatibility with httpx)
- FastAPI 0.104.1 - has support for python GET POST frameworks (previous project contributions as well)
- Data Store: Redis 5.0.1 (in-memory key–value store leading to a faster response time)
- Pydantic==2.5.0 - for request response definition using base models
- uvicorn==0.24.0- fastapi integration and has a low memory footprint



**Containerization & Orchestration:**
- Docker version 28.4.0 - Each service would have its own container
- Docker Compose version v2.39.2-desktop.1 - Each services are connected through a network 


