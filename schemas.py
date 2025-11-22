"""
Hostel Management System Schemas (MongoDB via Pydantic)

Each Pydantic model name corresponds to a collection with the lowercase name
(e.g., class User -> "user"). These models are used for validation on
API inputs and for documentation only; MongoDB stores BSON documents.

Note: Passwords are intentionally stored as plain strings as per requirements
(no bcrypt). Consider using secure hashing in production.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal
from datetime import date, datetime

# ---------------------------------
# AUTH / USERS
# ---------------------------------
class User(BaseModel):
    name: str
    email: EmailStr
    password: str  # plain text or custom hash per requirements
    role: Literal["admin", "warden", "staff", "student"] = "student"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------
# STUDENTS
# ---------------------------------
class GuardianInfo(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    relation: Optional[str] = None

class Student(BaseModel):
    user_id: str
    dob: Optional[date] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    guardian_info: Optional[GuardianInfo] = None
    additional_details: Optional[dict] = None
    documents: Optional[List[dict]] = None  # uploaded doc metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------
# HOSTELS / ROOMS
# ---------------------------------
class Hostel(BaseModel):
    name: str
    location: Optional[str] = None
    warden_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Room(BaseModel):
    hostel_id: str
    room_no: str
    capacity: int = Field(ge=1)
    current_occupancy: int = 0
    type: Optional[str] = None  # single, double, triple, etc.
    floor: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class RoomAllocation(BaseModel):
    student_id: str
    room_id: str
    allocation_date: date
    exit_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------
# FEES / PAYMENTS
# ---------------------------------
class Fee(BaseModel):
    student_id: str
    amount: float
    due_date: date
    status: Literal["paid", "unpaid"] = "unpaid"
    transaction_id: Optional[str] = None
    payment_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------
# ATTENDANCE
# ---------------------------------
class Attendance(BaseModel):
    student_id: str
    date: date
    status: Literal["present", "absent", "leave"]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class LateEntry(BaseModel):
    student_id: str
    date_time: datetime
    reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class LeaveRequest(BaseModel):
    student_id: str
    from_date: date
    to_date: date
    reason: Optional[str] = None
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------
# COMPLAINTS / GRIEVANCES
# ---------------------------------
class Complaint(BaseModel):
    student_id: str
    category: str
    description: str
    status: Literal["open", "in_progress", "resolved", "closed"] = "open"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ComplaintUpdate(BaseModel):
    complaint_id: str
    message: str
    updated_by: str  # user_id of staff/warden
    updated_at: Optional[datetime] = None


# ---------------------------------
# INVENTORY (optional)
# ---------------------------------
class Inventory(BaseModel):
    name: str
    quantity: int = 0
    hostel_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Maintenance(BaseModel):
    item_id: str
    description: Optional[str] = None
    date: date
    cost: Optional[float] = 0.0
    status: Literal["pending", "in_progress", "done"] = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------
# NOTIFICATIONS
# ---------------------------------
class Notification(BaseModel):
    user_id: str
    type: Optional[str] = "info"  # email, sms, in_app, etc.
    message: str
    status: Literal["unread", "read"] = "unread"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
