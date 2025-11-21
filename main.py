import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
app = FastAPI()

class ReminderCreate(BaseModel):
    user_id: str
    fcm_token: str
    reminder_time: str  # HH:MM or HH:MM:SS
    expires_on: Optional[str] = None  # YYYY-MM-DD

@app.post("/reminders")
async def create_reminder(reminder: ReminderCreate):
    try:
        response = supabase.table('reminder').insert({
            "user_id": reminder.user_id,
            "fcm_token": reminder.fcm_token,
            "reminder_time": reminder.reminder_time,
            "expires_on": reminder.expires_on
        }).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reminders/{user_id}")
async def get_reminders(user_id: str):
    response = supabase.table('reminder').select('*').eq('user_id', user_id).execute()
    return response.data

@app.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    supabase.table('reminder').delete().eq('id', reminder_id).execute()
    return {"message": "Deleted"}