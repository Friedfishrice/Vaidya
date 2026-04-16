from qdrant_client import QdrantClient
q = QdrantClient(path="local_qdrant_db")
try:
    print("Guidelines:", q.count(collection_name="guideline_vectors"))
except Exception as e:
    print("Guidelines ERR:", e)
try:
    print("Doctors:", q.count(collection_name="doctor_slots"))
except Exception as e:
    print("Doctors ERR:", e)
