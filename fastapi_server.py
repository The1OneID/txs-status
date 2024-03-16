import sqlite3
from typing import List

from fastapi import FastAPI
from fastapi import HTTPException, status, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

import settings

app = FastAPI()

origins = settings.COR_ORIGINS

# Add CORSMiddleware to the application
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow all origins
    allow_credentials=True,
    allow_methods=["GET"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

DB_FILE_PATH = settings.DB_FILE_PATH

API_KEY_NAME = "Authorization"
STATIC_TOKEN = settings.API_STATIC_TOKEN  # Replace with your actual static token

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == STATIC_TOKEN:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


class Transaction(BaseModel):
    id: int
    sender: str
    hash: str
    receiver: str
    amount: int
    ledger_version: int
    ledger_timestamp: int


# Database connection function
def get_db_connection():
    conn = sqlite3.connect(DB_FILE_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name: row['column_name']
    return conn


@app.get("/transactions/", response_model=List[Transaction])
async def read_transactions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions ORDER BY ledger_timestamp DESC")
    transactions = cursor.fetchall()
    conn.close()

    return [Transaction(**dict(transaction)) for transaction in transactions]
