import os
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
import jwt
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import (
    User, Student, Hostel, Room, RoomAllocation,
    Fee, Attendance, LateEntry, LeaveRequest,
    Complaint, ComplaintUpdate, Inventory, Maintenance, Notification
)

# ---------------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------------
app = FastAPI(title="Hostel Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------------
# Auth & JWT helpers (no bcrypt; plain password compare)
# ---------------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "60"))
security = HTTPBearer()

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class AuthUser(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str


def encode_token(user: dict) -> str:
    payload = {
        "sub": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role", "student"),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MIN)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> AuthUser:
    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    user = db.user.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return AuthUser(id=str(user["_id"]), name=user.get("name"), email=user.get("email"), role=user.get("role", "student"))


def require_roles(roles: List[str]):
    def checker(user: AuthUser = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden: insufficient role")
        return user
    return checker

# ---------------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------------

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


# ---------------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Hostel Management API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# ---------------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------------
@app.post("/api/auth/login", response_model=TokenResponse)
def login(data: LoginRequest):
    user = db.user.find_one({"email": data.email})
    if not user or user.get("password") != data.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = encode_token(user)
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRES_MIN * 60)

@app.get("/api/auth/me", response_model=AuthUser)
def me(user: AuthUser = Depends(get_current_user)):
    return user

# ---------------------------------------------------------------------------------
# Students CRUD (protected; warden/staff/admin can manage; students can view self)
# ---------------------------------------------------------------------------------
@app.post("/api/students")
def create_student(student: Student, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    sid = create_document("student", student)
    return {"id": sid}

@app.get("/api/students/{student_id}")
def get_student(student_id: str, user: AuthUser = Depends(get_current_user)):
    doc = db.student.find_one({"_id": to_object_id(student_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Student not found")
    # If student role, ensure they can only view their own profile
    if user.role == "student" and doc.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    doc["id"] = str(doc.pop("_id"))
    return doc

@app.put("/api/students/{student_id}")
def update_student(student_id: str, payload: dict, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    res = db.student.update_one({"_id": to_object_id(student_id)}, {"$set": {**payload, "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"updated": True}

@app.delete("/api/students/{student_id}")
def delete_student(student_id: str, _: AuthUser = Depends(require_roles(["admin", "warden"]))):
    res = db.student.delete_one({"_id": to_object_id(student_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"deleted": True}

# ---------------------------------------------------------------------------------
# Hostels, Rooms, Availability
# ---------------------------------------------------------------------------------
@app.post("/api/hostels")
def create_hostel(hostel: Hostel, _: AuthUser = Depends(require_roles(["admin", "warden"]))):
    hid = create_document("hostel", hostel)
    return {"id": hid}

@app.post("/api/rooms")
def create_room(room: Room, _: AuthUser = Depends(require_roles(["admin", "warden"]))):
    rid = create_document("room", room)
    return {"id": rid}

@app.get("/api/rooms/available")
def get_available_rooms():
    rooms = list(db.room.find({"$expr": {"$lt": ["$current_occupancy", "$capacity"]}}))
    for r in rooms:
        r["id"] = str(r.pop("_id"))
    return rooms

@app.post("/api/rooms/allocate")
def allocate_room(alloc: RoomAllocation, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    # Create allocation
    aid = create_document("roomallocation", alloc)
    # Increment occupancy
    db.room.update_one({"_id": to_object_id(alloc.room_id)}, {"$inc": {"current_occupancy": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    return {"id": aid}

# ---------------------------------------------------------------------------------
# Fees & Payments
# ---------------------------------------------------------------------------------
@app.post("/api/fees")
def create_fee(fee: Fee, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    fid = create_document("fee", fee)
    return {"id": fid}

class PayRequest(BaseModel):
    transaction_id: Optional[str] = None

@app.post("/api/fees/{fee_id}/pay")
def pay_fee(fee_id: str, body: PayRequest, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    res = db.fee.update_one({"_id": to_object_id(fee_id)}, {"$set": {"status": "paid", "transaction_id": body.transaction_id, "payment_date": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fee not found")
    return {"paid": True}

# ---------------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------------
@app.post("/api/attendance")
def mark_attendance(a: Attendance, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    aid = create_document("attendance", a)
    return {"id": aid}

@app.post("/api/attendance/late")
def late_entry(entry: LateEntry, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    lid = create_document("lateentry", entry)
    return {"id": lid}

@app.post("/api/attendance/leave")
def leave_request(req: LeaveRequest, user: AuthUser = Depends(get_current_user)):
    # Students can create their own; staff can create for others
    if user.role == "student" and req.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    lid = create_document("leaverequest", req)
    return {"id": lid}

class LeaveStatusBody(BaseModel):
    status: str  # pending, approved, rejected

@app.post("/api/attendance/leave/{leave_id}/status")
def update_leave_status(leave_id: str, body: LeaveStatusBody, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    res = db.leaverequest.update_one({"_id": to_object_id(leave_id)}, {"$set": {"status": body.status, "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return {"updated": True}

# ---------------------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------------------
@app.post("/api/complaints")
def create_complaint(c: Complaint, user: AuthUser = Depends(get_current_user)):
    # Students can create only for themselves
    if user.role == "student" and c.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    cid = create_document("complaint", c)
    return {"id": cid}

@app.post("/api/complaints/{complaint_id}/updates")
def add_complaint_update(complaint_id: str, upd: ComplaintUpdate, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    # Ensure complaint exists
    doc = db.complaint.find_one({"_id": to_object_id(complaint_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Complaint not found")
    uid = create_document("complaintupdate", upd)
    # Optionally set complaint status to in_progress if currently open
    db.complaint.update_one({"_id": to_object_id(complaint_id)}, {"$set": {"status": "in_progress", "updated_at": datetime.now(timezone.utc)}})
    return {"id": uid}

# ---------------------------------------------------------------------------------
# Notifications (simple create)
# ---------------------------------------------------------------------------------
@app.post("/api/notifications")
def create_notification_api(n: Notification, _: AuthUser = Depends(require_roles(["admin", "warden", "staff"]))):
    nid = create_document("notification", n)
    return {"id": nid}


# ---------------------------------------------------------------------------------
# Sample endpoints for frontend
# ---------------------------------------------------------------------------------
@app.get("/api/rooms/seed")
def seed_rooms():
    """Seed a couple of rooms for demo purposes."""
    if db.room.count_documents({}) == 0:
        db.room.insert_many([
            {"hostel_id": "demo1", "room_no": "A101", "capacity": 2, "current_occupancy": 0, "type": "double", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
            {"hostel_id": "demo1", "room_no": "A102", "capacity": 3, "current_occupancy": 1, "type": "triple", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        ])
    return {"seeded": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
