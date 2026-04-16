import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# Setup Local Qdrant
client = QdrantClient(path="local_qdrant_db")
model = SentenceTransformer('all-MiniLM-L6-v2')

# Define Guidelines (Dummy Corpus)
guidelines = [
    {
        "id": 1,
        "category": "symptom_triage",
        "condition": "fever",
        "language": "hi",
        "text": "Agar bukhar 102 se upar hai ya 3 din se zyada hai, toh turant doctor ko dikhayein. Tab tak aaram karein aur khoob paani piyein."
    },
    {
        "id": 2,
        "category": "symptom_triage",
        "condition": "fever",
        "language": "en",
        "text": "If fever exceeds 102F or lasts more than 3 days, consult a doctor immediately. Rest and hydrate."
    },
    {
        "id": 3,
        "category": "prescription_explanation",
        "condition": "paracetamol",
        "language": "hi",
        "text": "Yeh dawai dard aur bukhar kam karne ke liye hai. Ise khana khane ke baad hi lein. Khali pet bilkul na lein."
    },
    {
        "id": 4,
        "category": "prescription_explanation",
        "condition": "metformin",
        "language": "hi",
        "text": "Yeh sugar (diabetes) ki dawai hai. Ise hamesha bhojan ke beech ya turant baad lein, taaki pet kharab na ho. Dawai chhodne se sugar badh sakti hai."
    },
    {
        "id": 5,
        "category": "prescription_explanation",
        "condition": "telmisartan",
        "language": "hi",
        "text": "Yeh BP kam karne ki dawai hai. Roz ek hi samay par lein. Ek dum se isko band karne par BP badh sakta hai."
    },
    {
        "id": 6,
        "category": "symptom_triage",
        "condition": "cough chest pain",
        "language": "hi",
        "text": "Seene mein dard aur saans lene mein takleef hona khatarnak ho sakta hai. Kripya turant aspatal jayein ya emergency number 108 par call karein."
    }
]

# Create Collection
COLLECTION_NAME = "guideline_vectors"
try:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )
    print(f"Collection {COLLECTION_NAME} created.")
except Exception as e:
    print(f"Collection likely exists. Error: {e}")

# Insert Vectors
points = []
for item in guidelines:
    # Use condition + category as searchable text
    searchable_text = f"{item['condition']} {item['category']} {item['language']}"
    vector = model.encode(searchable_text).tolist()
    
    points.append(PointStruct(
        id=item["id"],
        vector=vector,
        payload=item
    ))

client.upsert(
    collection_name=COLLECTION_NAME,
    points=points
)
print("Guidelines seeded successfully into local Qdrant database.")

# -----------------
# Doctor Slots Seeding
# -----------------
doctors = [
    {
        "id": 101,
        "doctor_name": "Dr. Vivek Sharma",
        "specialty": "General Physician",
        "color_theme": "green",
        "status_label": "Active Duty",
        "avatar": "https://ui-avatars.com/api/?name=Dr+Sharma&background=c7d2fe&color=3730a3&size=128",
        "slot_time": "10:30 AM",
        "status": "available",
        "search_text": "General Physician Doctor Vivek Sharma fever cold cough daily 10:30 AM morning"
    },
    {
        "id": 102,
        "doctor_name": "Dr. Vivek Sharma",
        "specialty": "General Physician",
        "color_theme": "green",
        "status_label": "Active Duty",
        "avatar": "https://ui-avatars.com/api/?name=Dr+Sharma&background=c7d2fe&color=3730a3&size=128",
        "slot_time": "1:00 PM",
        "status": "booked",
        "search_text": "General Physician Doctor Vivek Sharma fever cold cough daily 1:00 PM afternoon"
    },
    {
        "id": 201,
        "doctor_name": "Dr. Anjali Iyer",
        "specialty": "Cardiologist",
        "color_theme": "yellow",
        "status_label": "In Surgery (Till 4PM)",
        "avatar": "https://ui-avatars.com/api/?name=Dr+Iyer&background=fde68a&color=92400e&size=128",
        "slot_time": "4:30 PM",
        "status": "available",
        "search_text": "Cardiologist Doctor Anjali Iyer heart chest pain bp hypertension 4:30 PM evening late"
    },
    {
        "id": 301,
        "doctor_name": "Dr. Manoj Kumar",
        "specialty": "Pediatrician",
        "color_theme": "gray",
        "status_label": "Off Duty",
        "avatar": "https://ui-avatars.com/api/?name=Dr+Manoj&background=e5e7eb&color=4b5563&size=128",
        "slot_time": "Tomorrow 9:00 AM",
        "status": "available",
        "search_text": "Pediatrician Doctor Manoj Kumar child kid baby fever tomorrow 9:00 AM morning"
    }
]

DOC_COLLECTION = "doctor_slots"
try:
    client.create_collection(
        collection_name=DOC_COLLECTION,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )
    print(f"Collection {DOC_COLLECTION} created.")
except Exception as e:
    print(f"Collection {DOC_COLLECTION} likely exists.")

doc_points = []
for doc in doctors:
    vector = model.encode(doc["search_text"]).tolist()
    doc_points.append(PointStruct(
        id=doc["id"],
        vector=vector,
        payload=doc
    ))

client.upsert(
    collection_name=DOC_COLLECTION,
    points=doc_points
)
print("Doctor slots seeded successfully into Qdrant.")
