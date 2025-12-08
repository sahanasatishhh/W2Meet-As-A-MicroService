# W2Meet-As-A-MicroService

**System Purpose:**
Think When2Meet but more backend focused that allows the users to create and store accounts, their availabilities and computing common meeting times across users (free intervals). In this case, the time intervals and availabilities are in **one-hour slots**

Goal:
Maintain architecture that can be scaled to calendar APIs and OAuth if possible

## Service Boundaries

`gateway-service`
1.  Acts as the **single public entrypoint** to the system.
2. Forwards client requests to appropriate backend services, hiding internal URLs and ports.
3. Implements **simple round-robin load balancing** across multiple replicas of compute services (e.g., `availability-service` and/or `suggestion-service`).

**Reason**
Provides a single external entrypoint while handling routing, load balancing, and hiding internal service topology.

`user-service`
1. Stores the record of unique identifiers for each user alongside their availabilities for the list (2D arrays)
2. Stores and accesses this data in Redis and SQl as the fall back with caching.
3. Has GET and POST functionality to create and retrieve users and if it exists, their availabilities and preferences using `GET users/{emailid}/`.


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

`worker-service` (Async Queue Consumer + Notifications)

1. Consumes meeting suggestion jobs from a **RabbitMQ queue**.
2. For each job:
   - Calls `availability-service` to compute common free slots.
   - Calls `suggestion-service` to pick the best slot (first/last/random).
   - Sends the final suggestion to a callback endpoint ( potentially `gateway-service`) via HTTP.

**Reason**
Processes meeting-suggestion jobs asynchronously via RabbitMQ to avoid blocking API requests and improve system responsiveness.

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

## Technical Specifications for Maintainability, Reliability and Scalability:

## Topic 1: Cache-Aside Caching with Redis (with SQLModel as the back-up)

For my project, I will be using a cache-aside pattern from our previous assignment: Redis stores frequently accessed user availability, while SQLModel/PostgreSQL is the backup. Whenever availability-service needs a user's availability, it will first look into Redis. If a cache miss occurs, it will query the database via SQLModel and then send that to Redis so that future reads are fast. When a user does not exist in both Redis and the database, user-service will create that user and their availability in PostgreSQL and immediately send that to the cache, reducing pressure on Postgres during repeated availability lookups, which is expensive. For maintainability, the cache logic is divided into small helper functions in the user-service instead of being scattered across the codebase for better modification.

 
**Scenario:**

```A new user signs up and posts their availability to the user-service. The POST point writes the user row into PostgreSQL and stores it in Redis, so that subsequent reads go straight to the cache. Later, when the availability service needs to request the user's slots to find an overlap, it accesses user-service, which accesses Redis first; if the entry exists, it returns in a few milliseconds, a cache hit. If the cache is missed or fails, it falls back to Postgres, sends it to Redis, and returns the data, ensuring both new and existing users are handled efficiently.```

 

## Topic 2: Structured Logging and Having a Case/Request ID

Because my architecture has three services, namely suggestion-service → availability-service → user-service, I will add structured logging and have a common request/case ID to trace a single request across all the services. This will, in turn, trace a single user's request across services and save them from getting jumbled up.

 

A middleware in each FastAPI service could store a request/case ID header shared among every service and include it in every log entry. When suggestion-service calls availability-service, and that service calls user-service, they all pass the same ID on to store it in the logs. This technique can be very useful for maintainability: if a suggestion looks wrong or fails, I can check logs by request ID and check things like who called whom, how long each service request took, and where errors occurred, and avoids it being jumbled with other user requests.

 

**Scenario:**

```
User calls suggestion-service

suggestion-service logs [CID=123] "checking for best availabilities…"

calls availability-service with header CID: 123

availability-service calls user-service with the same header

all three services log their work with CID=123
```
 

## Topic 3: Task Queues with RabbitMQ and Background Workers

I'll use a RabbitMQ task queue and a worker service to offload non-critical work from the main HTTP path. In such a case, after a suggestion service selects the best 1-hour meeting slot that fits the requirements, it would immediately return the suggestion to the client, but also enqueue a task-e.g., send iCal invite/message with the chosen slot and user IDs-into a RabbitMQ queue. A separate worker process would then consume messages from that queue and simulate sending confirmations.

The API is the producer, the worker is the consumer, and RabbitMQ provides durability and acknowledgements task-queue pattern from class. This improves the scalability by keeping HTTP responses fast under heavy load and lets me scale the number of workers independently from the API responses.

This is also helpful for future directions of this project; once abilities like sending invites via email come in, for instance, the task queue allows those slower, external operations to be handled asynchronously without degrading API responsiveness.

 

**Scenario:**
```A group of users submit their availabilities at once. The suggestion-service keeps returning in milliseconds because it just computes the slot and enqueues a send message task.

The tasks are held in RabbitMQ, while one or more workers process the queue in the background. If a worker crashes in the middle of processing, it will assign the unfinished task to another worker, improving reliability without slowing down the main API process.

Also includes the fair task distribution from class that we talked about.
```




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


