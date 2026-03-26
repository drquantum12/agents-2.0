import os
from pymongo import MongoClient
from bson import Decimal128


def _d128_to_float(value):
    """Convert a bson.Decimal128 to float; pass through other types unchanged."""
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    return value

DB_URI = os.getenv("DB_URI", "mongodb+srv://arjuntomar:4mzs8E9gdeLAfw8r@cluster0.w6pyfx8.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

mongo_db = MongoClient(DB_URI).get_database("neurosattva")
    
if __name__ == "__main__":
    devices = list(
        mongo_db["devices"]
        .find({"owner_user_id": "ptLFqq0N9JTyYL7lkAqhB1YSFj32", "ownership_status": "active"})
        .limit(50)
    )
    for d in devices:
        d["device_id"] = d.get("_id", d.get("device_id"))
    print({"devices": devices})

#    firmware = mongo_db["firmware"].find_one(
#             sort=[("version", -1)],
#             projection={"version": 1},
#         )
   
#    print(_d128_to_float(firmware["version"]))