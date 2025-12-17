from pydantic import field_validator
from sqlmodel import SQLModel, Field, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, DateTime, String
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Literal, List, Dict

load_dotenv()

# Load the Postgres DSN (connection string) from environment variables
PG_DSN = os.getenv("PG_DSN")

# Create the SQLAlchemy engine that connects to your database
engine = create_engine(PG_DSN)

Weekday = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

class UserAvail(SQLModel, table=True):
    __tablename__ = "useravail"  # matches our table name in SQL
    email: str= Field(sa_column=Column(String,unique=True,primary_key=True))
    # stored as [0,11,12,16,23] representing start times of free hours in a day in 24-hour format
    

    availabilities: Dict[Weekday, List[int]] = Field(sa_column=Column(JSONB) )
    #Validation constraint for availabilities 
    @field_validator("availabilities")
    def validate_hours(cls, v: Dict[str, List[int]]):
        required_days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]

        if not isinstance(v, dict):
            raise ValueError("Availabilities must be a dictionary of day -> list of hours.")
        check_days: Dict[str, List[int]] = {}
        for day, hours in v.items():
            day_lc = day.lower()
            if day_lc not in required_days:
                raise ValueError(f"Invalid day in availabilities: '{day}'.")
            if not isinstance(hours, list):
                raise ValueError(f"Availabilities for '{day_lc}' must be a list of start int times.")
            if not all(isinstance(h, int) for h in hours):
                raise ValueError(f"element start intervals for '{day_lc}' must be integers.")
            if not all(0 <= h <= 23 for h in hours):
                raise ValueError(f"Hours for '{day_lc}' must be between 0 and 23 (24 hour format).")
            check_days[day_lc] = sorted(set(hours))

        for day in required_days:
            check_days.setdefault(day, [])

        return check_days
            
    preferences: str=  Field(sa_column=Column(String),default='first')
    created_at: datetime = Field(sa_column=Column(DateTime, onupdate=datetime.now(), default=datetime.now()))

# create tables if they don't exist
def init_db():
    SQLModel.metadata.create_all(engine)
    print("Database initialized and tables created (if not exist).")

# close the database connection cleanly
def close_db_connection():
    engine.dispose()
    print("Database connection closed.")