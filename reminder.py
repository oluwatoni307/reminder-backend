import os
import json
from datetime import datetime, time, timedelta
import pytz
from dotenv import load_dotenv
from supabase import create_client, Client
import firebase_admin
from firebase_admin import credentials, messaging

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH')
TIMEZONE = 'Africa/Lagos'  # Nigeria timezone

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Firebase
cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)

def get_current_nigeria_time():
    """Get current time in Nigeria timezone"""
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

def time_to_string(t: datetime):
    """Convert time object to HH:MM:SS string"""
    return t.strftime('%H:%M:%S')

def is_within_window(reminder_time_str: str, current_time: datetime, window_minutes=5):
    """Check if current time is within window of reminder time"""
    # Parse reminder time
    reminder_hour, reminder_minute = map(int, reminder_time_str.split(':')[:2])
    reminder_time = time(reminder_hour, reminder_minute)
    
    # Convert current datetime to timea
    current_time_only = current_time.time()
    
    # Create time window
    reminder_datetime = datetime.combine(current_time.date(), reminder_time)
    window_start = (reminder_datetime - timedelta(minutes=0)).time()
    window_end = (reminder_datetime + timedelta(minutes=window_minutes)).time()
    
    # Check if current time is within window
    if window_start <= current_time_only <= window_end:
        return True
    return False

def get_reminders_to_send():
    """Query Supabase for reminders that need to be sent"""
    try:
        today = get_current_nigeria_time()
        now = today.date()
        
        
        one_hour_later = now + timedelta(hours=1)
        
        now_str = now.strftime("%H:%M:%S")
        one_hour_str = one_hour_later.strftime("%H:%M:%S")
        
        
        # Query reminders
        response = supabase.table('reminder').select('*').or_(
            f'last_notified_date.is.null,last_notified_date.lt.{today}'
        ).or_(
            'expires_on.is.null,expires_on.gt.{}'.format(today)
        ).filter("reminder_time", "gte", now_str).filter("reminder_time", "lte", one_hour_str).execute()
        
        return response.data
    except Exception as e:
        print(f"❌ Error querying Supabase: {e}")
        return []

def send_fcm_notification(fcm_token, title, body):
    """Send FCM notification using Firebase Admin SDK"""
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=fcm_token,
        )
        
        response = messaging.send(message)
        print(f"✅ Notification sent successfully: {response}")
        return True
    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return False

def update_reminder(reminder_id):
    """Update reminder's last_notified_date"""
    try:
        today = get_current_nigeria_time().date().isoformat()
        supabase.table('reminders').update({
            'last_notified_date': today
        }).eq('id', reminder_id).execute()
        print(f"✅ Updated reminder {reminder_id}")
        return True
    except Exception as e:
        print(f"❌ Error updating reminder: {e}")
        return False

def main():
    """Main function to check and send reminders"""
    print("\n" + "="*60)
    print(f"🕐 Running reminder check at {get_current_nigeria_time()}")
    print("="*60)
    
    # Get current time
    current_time = get_current_nigeria_time()
    
    # Get all active reminders
    reminders = get_reminders_to_send()
    print(f"\n📋 Found {len(reminders)} active reminders to check")
    
    if not reminders:
        print("ℹ️  No reminders found")
        return
    
    # Check each reminder
    send_count = 0
    skip_count = 0
    
    for reminder in reminders:
        reminder_id = reminder['id']
        user_id = reminder['user_id']
        fcm_token = reminder['fcm_token']
        reminder_time = reminder['reminder_time']
        
        print(f"\n👤 Checking reminder for user: {user_id}")
        print(f"   Reminder time: {reminder_time}")
        print(f"   Current time: {current_time.strftime('%H:%M:%S')}")
        
        # Check if within time window
        if is_within_window(reminder_time, current_time):
            print(f"   ✅ Within time window - SENDING")
            
            # Send notification
            success = send_fcm_notification(
                fcm_token=fcm_token,
                title="Reminder",
                body=f"It's time for your {reminder_time} reminder!"
            )
            
            if success:
                # Update database
                update_reminder(reminder_id)
                send_count += 1
            else:
                print(f"   ❌ Failed to send notification")
        else:
            print(f"   ⏭️  Not within time window - SKIPPING")
            skip_count += 1
    
    # Summary
    print("\n" + "="*60)
    print(f"📊 Summary:")
    print(f"   Total checked: {len(reminders)}")
    print(f"   Sent: {send_count}")
    print(f"   Skipped: {skip_count}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()