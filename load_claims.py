"""Load claims.json into MongoDB using pymongo (alternative to mongoimport).
Usage: python mongodb/load_claims.py            (needs: pip install pymongo)
"""
import os
from bson import json_util
from pymongo import MongoClient

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claims.json")
with open(path) as f:
    docs = json_util.loads(f.read())          # converts {"$date": ...} to datetime

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
col = client["claimsure"]["claims"]
col.drop()
res = col.insert_many(docs)
print("Inserted", len(res.inserted_ids), "documents into claimsure.claims")
