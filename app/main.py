from contextlib import asynccontextmanager
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.config import VAPI_TOOL_SECRET
from app.database import initialize_facilities
from app.tools.information import get_rate, check_availability
from app.tools.booking import create_booking


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_facilities()
    yield


app = FastAPI(lifespan=lifespan)


class RateRequest(BaseModel):
    facility: str


class AvailabilityRequest(BaseModel):
    facility: str
    date: str
    start_time: str
    end_time: str


class BookingRequest(BaseModel):
    facility: str
    date: str
    start_time: str
    end_time: str
    customer_name: str
    customer_phone: str
    customer_email: str


def require_vapi_auth(authorization: str | None = Header(default=None)):
    if not VAPI_TOOL_SECRET:
        raise HTTPException(
            status_code=503,
            detail="VAPI tool authentication is not configured.",
        )

    scheme, separator, supplied_secret = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(supplied_secret, VAPI_TOOL_SECRET)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/")
def home():
    return {"status": "Sports Voice Agent API is running"}


@app.post("/tools/rate", dependencies=[Depends(require_vapi_auth)])
def rate(request: RateRequest):
    return get_rate(request.facility)


@app.post("/tools/availability", dependencies=[Depends(require_vapi_auth)])
def availability(request: AvailabilityRequest):
    return check_availability(
        request.facility,
        request.date,
        request.start_time,
        request.end_time,
    )


@app.post("/tools/book", dependencies=[Depends(require_vapi_auth)])
def book(request: BookingRequest):
    return create_booking(
        request.facility,
        request.date,
        request.start_time,
        request.end_time,
        request.customer_name,
        request.customer_phone,
        request.customer_email,
    )