import os
from functools import lru_cache

import pymongo
from dotenv import load_dotenv

load_dotenv()

# FIXME: due to circular import, we must do this. We must move this config to configs in future
MONGO_HOST = os.environ["MONGO_HOST"]
MONGO_PORT = os.environ["MONGO_PORT"]
MONGO_DBNAME = os.environ.get("MONGO_DBNAME", "transaction_database")


@lru_cache()
def get_db_connection():
    client = pymongo.AsyncMongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}/")
    return client[MONGO_DBNAME]
