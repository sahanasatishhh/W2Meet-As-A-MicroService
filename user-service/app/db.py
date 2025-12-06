from sqlmodel import SQLModel, Field, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, DateTime, String
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Load the Postgres DSN (connection string) from environment variables
PG_DSN = os.getenv("PG_DSN")

# Create the SQLAlchemy engine that connects to your database
engine = create_engine(PG_DSN)

class UserAvail(SQLModel, table=True):
    __tablename__ = "exchange_rate"  # matches our table name in SQL
    email: str= Field(sa_column=Column(String,unique=True,primary_key=True))
    availabilities: dict = Field(sa_column=Column(JSONB), required=True)
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