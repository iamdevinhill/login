from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import asyncpg
import os
from typing import Optional

# create middleware
app = FastAPI()

# establish connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgresdb")


class UserCreate(BaseModel):
    username: str
    email: EmailStr


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


async def create_users_table(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            );
        """)


@app.on_event("startup")
async def startup():
    pool = await asyncpg.create_pool(DATABASE_URL)
    await create_users_table(pool)
    app.state.db_pool = pool


@app.on_event("shutdown")
async def shutdown():
    pool = app.state.db_pool
    if pool:
        await pool.close()


@app.get("/")
async def read_root():
    return {"message": "FastAPI with PostgreSQL"}


@app.get("/users")
async def get_users():
    pool = app.state.db_pool
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users")
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users", status_code=201)
async def create_user(user: UserCreate):
    pool = app.state.db_pool
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO users (username, email)
                VALUES ($1, $2)
                RETURNING id, username, email
            """, user.username, user.email)
        return dict(result)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")


@app.put("/users/{user_id}")
async def update_user(user_id: int, user: UserUpdate):
    pool = app.state.db_pool
    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            if not existing:
                raise HTTPException(status_code=404, detail="User not found")

            new_username = user.username or existing["username"]
            new_email = user.email or existing["email"]

            result = await conn.fetchrow("""
                UPDATE users
                SET username = $1, email = $2
                WHERE id = $3
                RETURNING id, username, email
            """, new_username, new_email, user_id)

        return dict(result)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int):
    pool = app.state.db_pool
    try:
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")