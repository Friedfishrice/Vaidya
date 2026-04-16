import sqlite3
import datetime
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# Initialize Databases
DB_FILE = "prototype.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS patients (
                 phone TEXT PRIMARY KEY, 
                 name TEXT,
                 risk_level TEXT,
                 adherence_score INTEGER,
                 upcoming_appointment TEXT DEFAULT 'None'
                 )''')
    try:
        c.execute("ALTER TABLE patients ADD COLUMN upcoming_appointment TEXT DEFAULT 'None'")
    except sqlite3.OperationalError:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS call_logs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 call_id TEXT,
                 phone TEXT,
                 risk_level TEXT,
                 escalate BOOLEAN,
                 response_text TEXT,
                 timestamp TEXT
                 )''')
    conn.commit()
    conn.close()

init_db()

# Initialize Local Qdrant
q_client = QdrantClient(path="local_qdrant_db")
model = SentenceTransformer('all-MiniLM-L6-v2')

class PatientReq(BaseModel):
    phone: str

class ReminderReq(BaseModel):
    phone: str
    drugName: str
    language: str
    callId: str

class LogReq(BaseModel):
    callId: str
    patientPhone: str
    riskLevel: str
    escalate: bool
    responseText: str
    timestamp: str

@app.post("/patients/get-or-create")
async def get_patient(req: PatientReq):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE phone=?", (req.phone,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO patients (phone, name, risk_level, adherence_score) VALUES (?, ?, ?, ?)", 
                  (req.phone, "Patient_" + req.phone[-4:], "low", 100))
        conn.commit()
    conn.close()
    return {"status": "success", "phone": req.phone}

@app.post("/reminders/schedule")
async def schedule_reminder(req: ReminderReq):
    print(f"Scheduled Reminder for {req.phone}: {req.drugName}")
    return {"status": "scheduled"}

@app.post("/logs/call")
async def log_call(req: LogReq):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO call_logs (call_id, phone, risk_level, escalate, response_text, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?)''', 
              (req.callId, req.patientPhone, req.riskLevel, req.escalate, req.responseText, req.timestamp))
    # Update Patient Adherence/Risk
    c.execute("UPDATE patients SET risk_level=? WHERE phone=?", (req.riskLevel, req.patientPhone))
    conn.commit()
    conn.close()
    return {"status": "logged"}


@app.post("/collections/{collection_name}/points/search")
async def qdrant_search_mock(collection_name: str, request: Request):
    data = await request.json()
    
    query_text = ""
    # n8n query extracts filter 'must' matching
    if "filter" in data and "must" in data["filter"]:
        for m in data["filter"]["must"]:
            if "match" in m and "value" in m["match"]:
                query_text += " " + m["match"]["value"]
    
    if not query_text.strip():
        query_text = "general medical advice"

    vector = model.encode(query_text).tolist()
    
    try:
        search_result = q_client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=data.get("limit", 3)
        )
        
        results = [
            {"id": hit.id, "score": hit.score, "payload": hit.payload}
            for hit in search_result
        ]
        return {"result": results}
    except Exception as e:
        print("Qdrant Search Error:", e)
        return {"result": [{"payload": {"text": "Dawai samay par lein. Zaroorat padne par doctor se milein."}}]}

@app.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    # This completely bypasses n8n and handles the Vapi logic directly!
    body = await request.json()
    message = body.get("message", {})
    
    # --- Safe Vapi Tool Call Parser ---
    tool_args = {}
    tool_call_id = "mock-id"
    
    if message.get("type") == "tool-calls":
        tool_list = message.get("toolWithToolCallList", [])
        if tool_list:
            tc = tool_list[0].get("toolCall", {})
            tool_call_id = tc.get("id", tool_call_id)
            func = tc.get("function", {})
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except Exception:
                pass
                
    intent = tool_args.get("intent", body.get("intent", "symptom_triage"))
    call_id = message.get("call", {}).get("id", "test-call")
    caller_phone = message.get("call", {}).get("customer", {}).get("number", "+1234567890")
    
    symptoms = str(tool_args.get("symptoms", tool_args.get("prescription_raw", "fever")))
    preferred_time = str(tool_args.get("preferred_time", "morning"))
    language = str(tool_args.get("language", "hi"))
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE phone=?", (caller_phone,))
    if not c.fetchone():
        c.execute("INSERT INTO patients (phone, name, risk_level, adherence_score) VALUES (?, ?, ?, ?)", 
                  (caller_phone, "Patient_" + caller_phone[-4:], "low", 100))
        conn.commit()
    
    response_text = "Mujhe is sawaal ka sahi jawab nahi pata. Kripya doctor se baat karein."
    risk_level = "low"
    escalate = False
    needs_reminder = False
    
    if intent == "explain_prescription" or "prescription" in intent:
        drug_name = "paracetamol" if "paracetamol" in symptoms.lower() else "metformin"
        
        # Qdrant mock query
        vector = model.encode(f"{drug_name} prescription_explanation {language}").tolist()
        try:
            hits = q_client.search(collection_name="guideline_vectors", query_vector=vector, limit=1)
            guideline = hits[0].payload["text"] if hits else "Dawai doctor ke bataye anusaar lein."
        except:
            guideline = "Dawai doctor ke bataye anusaar lein."
            
        response_text = f"{drug_name} ki goli lene ki salah:\\n{guideline}\\nYaad rakhen: dawai samay par lein."
        needs_reminder = True
        
    elif intent == "symptom_triage" or "symptom" in intent:
        vector = model.encode(f"{symptoms} symptom_triage {language}").tolist()
        try:
            hits = q_client.search(collection_name="guideline_vectors", query_vector=vector, limit=1)
            guideline = hits[0].payload["text"] if hits else "Aaram karein aur paani piyein."
        except:
            guideline = "Aaram karein aur paani piyein."
            
        red_flags = ['breathlessness', 'chest pain', 'confusion', 'bleeding']
        if any(rf in symptoms.lower() for rf in red_flags):
            risk_level = "high"
            escalate = True
            response_text = f"CHETAVNI: Turant 108 call karein ya aspatal jayein.\\n{guideline}"
        else:
            risk_level = "medium" if "fever" in symptoms.lower() else "low"
            response_text = f"Salah.\\n{guideline}. Agar aap chahein toh main aspatal mein appointment book kar sakti hoon."

    elif intent == "book_appointment" or "appointment" in intent or "book" in str(body).lower():
        # Search Qdrant for a doctor matching the symptom string and time
        vector = model.encode(f"{symptoms} {preferred_time} {language} doctor").tolist()
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # Use Qdrant's payload filtering to ONLY fetch "available" slots
            hits = q_client.search(
                collection_name="doctor_slots", 
                query_vector=vector, 
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="status",
                            match=MatchValue(value="available")
                        )
                    ]
                ),
                limit=1
            )
            
            if hits:
                slot = hits[0].payload
                doctor_name = slot["doctor_name"]
                slot_time = slot["slot_time"]
                
                # Mark as booked in Qdrant and track patient
                slot["status"] = "booked"
                slot["booked_by"] = caller_phone
                q_client.upsert(
                    collection_name="doctor_slots",
                    points=[{"id": hits[0].id, "vector": vector, "payload": slot}]
                )
                
                c.execute("UPDATE patients SET upcoming_appointment=? WHERE phone=?", (f"{doctor_name}|{slot.get('specialty', 'Specialist')}|{slot_time}", caller_phone))
                
                response_text = f"Reservation granted! Aapki appointment {doctor_name} ke saath {slot_time} baje fix ho gayi hai."
                needs_reminder = True
            else:
                response_text = "Maaf kijiye, koi slot nahi mil paaya. Baad mein prayas karein."
        except Exception as e:
            print("Scheduling error:", e)
            response_text = "Booking mein dikkat aayi. Kripya bad mein call karein."
            
    c.execute('''INSERT INTO call_logs (call_id, phone, risk_level, escalate, response_text, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?)''', 
              (call_id, caller_phone, risk_level, escalate, response_text, str(datetime.datetime.now())))
    if risk_level != "low":
        c.execute("UPDATE patients SET risk_level=? WHERE phone=?", (risk_level, caller_phone))
    conn.commit()
    conn.close()
    
    return JSONResponse(content={
        "results": [{
            "toolCallId": tool_call_id,
            "result": {
                "response_text": response_text,
                "risk_level": risk_level,
                "escalate": escalate,
                "reminder_set": needs_reminder
            }
        }]
    })

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM patients ORDER BY risk_level DESC, adherence_score ASC")
    patients = [dict(row) for row in c.fetchall()]
    
    try:
        c.execute("SELECT * FROM call_logs ORDER BY timestamp DESC LIMIT 20")
        logs = [dict(row) for row in c.fetchall()]
    except:
        logs = []
        
    conn.close()
    
    # Fetch all doctors dynamically from Qdrant Vector database using scroll
    try:
        doctors_raw, _ = q_client.scroll(
            collection_name="doctor_slots",
            limit=20,
            with_payload=True
        )
        
        # Group by doctor so the UI can render them correctly
        # Qdrant returns a list of points
        doctors = {}
        for doc in doctors_raw:
            p = doc.payload
            doc_name = p["doctor_name"]
            if doc_name not in doctors:
                doctors[doc_name] = {
                    "doctor_name": doc_name,
                    "specialty": p["specialty"],
                    "avatar": p["avatar"],
                    "color_theme": p.get("color_theme", "blue"),
                    "status_label": p.get("status_label", "Active"),
                    "slots": [],
                    "available_count": 0,
                    "booked_count": 0
                }
            
            if p["status"] == "available":
                doctors[doc_name]["available_count"] += 1
            else:
                doctors[doc_name]["booked_count"] += 1
                
            doctors[doc_name]["slots"].append({
                "time": p["slot_time"],
                "status": p["status"],
                "booked_by": p.get("booked_by", "Unknown Patient")
            })
        
        doctors_list = list(doctors.values())
        
        # Sort slots natively alphabetically
        for d in doctors_list:
            d["slots"].sort(key=lambda x: x["time"])
            
    except Exception as e:
        print("Failed to fetch slots from Qdrant:", e)
        doctors_list = []
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "patients": patients,
        "logs": logs,
        "doctors": doctors_list
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
