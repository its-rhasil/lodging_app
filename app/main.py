from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.routes import dashboard, room_type, room
app = FastAPI()

app.include_router(dashboard.router)
app.include_router(room_type.router)
app.include_router(room.router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    return {"status": "connected", "result": result.scalar()}