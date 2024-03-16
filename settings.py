import os

from dotenv import load_dotenv

load_dotenv()

DB_FILE_PATH = os.getenv("DB_FILE_PATH", "transactions.db")
FETCHING_INTERVAL_IN_SEC = int(os.getenv("FETCHING_INTERVAL_IN_SEC", 180))
API_STATIC_TOKEN = os.getenv("API_STATIC_TOKEN", "")
COR_ORIGINS = os.getenv("COR_ORIGINS", [])
if COR_ORIGINS:
    COR_ORIGINS = [item.strip() for item in COR_ORIGINS.split(',')]

TXS_LIMIT_PER_PAGE = int(os.getenv("TXS_LIMIT_PER_PAGE", 200))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 5))
RETRY_BACKOFF = int(os.getenv("RETRY_BACKOFF", 2))
MAX_THREADS = int(os.getenv("MAX_THREADS", 12))
MAX_TXS_AGE_IN_DAYS = int(os.getenv("MAX_TXS_AGE_IN_DAYS", 7))
MIN_TX_AMOUNT = int(os.getenv("MIN_TX_AMOUNT", 1_000 * 10 ** 6))
CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE", 20))
GRAPHQL_ENDPOINT = os.getenv("GRAPHQL_ENDPOINT", "https://api.0l.fyi/graphql")
RPC_TXS_BY_LEDGER_ENDPOINT = os.getenv("RPC_TXS_BY_LEDGER_ENDPOINT", "https://rpc.0l.fyi/v1/transactions/by_version/")
