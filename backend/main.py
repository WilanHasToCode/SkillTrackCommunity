from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db
import models

app = FastAPI(title="[SkillTrack Community Website] Backend API")

origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins= origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

@app.get("/")
async def root_health_check():
    return {
        "status": "healthy",
        "system": "Food Pantry & Inventory Manager",
        "documentation": "/docs"
    }

@app.get("/users")
async def get_all_users(db: AsyncSession = Depends(get_db)):
    try:
        # Construct an async SELECT query for the User table
        query = select(models.User)
        result = await db.execute(query)
        
        users = result.scalars().all()
        return {"status": "success", "data": users}
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to read users from database. Error: {str(e)}"
        )