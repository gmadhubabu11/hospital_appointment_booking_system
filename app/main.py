import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import appointments, auth, consultations, departments, doctors, queue, reports, schedules
from app.websockets import endpoints as ws_endpoints
from app.websockets.manager import manager

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.loop = asyncio.get_running_loop()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Hospital Appointment Booking System", version="1.0.0", lifespan=lifespan)

for r in (auth.router, departments.router, doctors.router, schedules.router, appointments.router, queue.router,
          consultations.router, reports.router, ws_endpoints.router):
    app.include_router(r)


@app.get("/", tags=["Health"])
def root():
    return {"message": "Hospital Appointment Booking System API", "docs": "/docs"}
