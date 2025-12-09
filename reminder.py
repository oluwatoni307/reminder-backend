import os
import json
from datetime import datetime, time, timedelta
import pytz
from dotenv import load_dotenv
from supabase import create_client, Client
import firebase_admin
from firebase_admin import credentials, messaging

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
# Changed to read the content string instead of the path
FIREBASE_CREDENTIALS_CONTENT = os.getenv('FIREBASE_CREDENTIALS') 
TIMEZONE = 'Africa/Lagos'  # Nigeria timezone

# --- Initialize Supabase ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase client initialized.")
except Exception as e:
    print(f"❌ Error initializing Supabase: {e}")
    supabase = None # Set to None if initialization fails

# --- Initialize Firebase ---
try:
    if FIREBASE_CREDENTIALS_CONTENT:
        # Load the service account info from the JSON content string
        service_account_info = json.loads(FIREBASE_CREDENTIALS_CONTENT)
        
        # Initialize credentials using the dictionary content
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized from content.")
    else:
        print("❌ ERROR: FIREBASE_CREDENTIALS environment variable is empty.")
except json.JSONDecodeError:
    print("❌ ERROR: FIREBASE_CREDENTIALS content is not valid JSON.")
except Exception as e:
    print(f"❌ ERROR initializing Firebase: {e}")


# --- Utility Functions ---

def get_current_nigeria_time():
    """Get current time in Nigeria timezone"""
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

def time_to_string(t: datetime):
    """Convert time object to HH:MM:SS string"""
    return t.strftime('%H:%M:%S')

def is_within_window(reminder_time_str: str, current_time: datetime, window_minutes=20):
    """Check if reminder time is within the next X minutes from now"""
    # Parse reminder time
    reminder_hour, reminder_minute = map(int, reminder_time_str.split(':')[:2])
    reminder_time = time(reminder_hour, reminder_minute)
    
    # Get current time as time object
    current_time_only = current_time.time()
    
    # Calculate the end of the window (20 minutes from now)
    current_datetime = datetime.combine(current_time.date(), current_time_only)
    window_end = (current_datetime + timedelta(minutes=window_minutes)).time()
    
    # Return True if reminder is between now and 20 minutes from now
    if current_time_only <= reminder_time <= window_end:
        return True
    return False

# --- Supabase Functions ---

def get_reminders_to_send():
    """Query Supabase for reminders that need to be sent"""
    if not supabase:
        print("❌ Supabase client not available.")
        return []
        
    try:
        today = get_current_nigeria_time()
        # Use the time part of the localized datetime object
        now = today.time()
        
        # Calculate one hour later time for the query range
        now_datetime = datetime.combine(today.date(), now)
        one_hour_later_datetime = now_datetime + timedelta(hours=1)
        
        now_str = now.strftime("%H:%M:%S")
        one_hour_str = one_hour_later_datetime.strftime("%H:%M:%S")
        
        
        # Query reminders
        response = supabase.table('reminder').select('*').or_(
            f'last_notified_date.is.null,last_notified_date.lt.{today.date().isoformat()}'
        ).or_(
            f'expires_on.is.null,expires_on.gt.{today.date().isoformat()}'
        ).filter("reminder_time", "gte", now_str).filter("reminder_time", "lte", one_hour_str).execute()
        
        return response.data
    except Exception as e:
        print(f"❌ Error querying Supabase: {e}")
        return []

def update_reminder(reminder_id):
    """Update reminder's last_notified_date"""
    if not supabase:
        print("❌ Supabase client not available.")
        return False

    try:
        # Corrected table name to 'reminder' for consistency
        today = get_current_nigeria_time().date().isoformat()
        supabase.table('reminder').update({
            'last_notified_date': today
        }).eq('id', reminder_id).execute()
        print(f"✅ Updated reminder {reminder_id}")
        return True
    except Exception as e:
        print(f"❌ Error updating reminder: {e}")
        return False

# --- Firebase Functions ---

def send_fcm_notification(fcm_token, title, body):
    """Send FCM notification using Firebase Admin SDK"""
    if not firebase_admin._apps:
        print("❌ Firebase app not initialized.")
        return False
        
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

# --- Main Execution ---

def main():
    """Main function to check and send reminders"""
    if not supabase or not firebase_admin._apps:
        print("\n🛑 Skipping execution due to service initialization failure.")
        return

    print("\n" + "="*60)
    print(f"🕐 Running reminder check at {get_current_nigeria_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")
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
        user_id = reminder.get('user_id', 'Unknown User')
        fcm_token = reminder.get('fcm_token')
        reminder_time = reminder['reminder_time']
        medication_name = reminder.get('name', 'your medication')
        dose = reminder.get('dose', '')
        
        # Skip if no token is available
        if not fcm_token:
            print(f"   ❌ Skipping reminder {reminder_id}: No FCM token available.")
            skip_count += 1
            continue

        print(f"\n👤 Checking reminder for user: {user_id}")
        print(f"   Reminder time: {reminder_time}")
        print(f"   Current time: {current_time.strftime('%H:%M:%S')}")
        
        # Check if within time window
        if is_within_window(reminder_time, current_time):
            print(f"   ✅ Within time window - SENDING")
            
            # Create persuasive notification text
            notification_body = f"Time to take {medication_name} - {dose}"
            
            # Send notification
            success = send_fcm_notification(
                fcm_token=fcm_token,
                title="💊 Medication Reminder",
                body=notification_body
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