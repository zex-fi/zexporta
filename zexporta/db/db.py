import os
from functools import lru_cache

import pymongo

# FIXME: due to circular import, we must do this. We must move this config to configs in future
MONGO_HOST = os.getenv("MONGO_HOST")
MONGO_PORT = os.getenv("MONGO_PORT")
MONGO_DBNAME = os.environ.get("MONGO_DBNAME", "transaction_database")


@lru_cache()
def get_db_connection():
    client = pymongo.AsyncMongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}/")
    return client[MONGO_DBNAME]
