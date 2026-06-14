import os
import duckdb
from fastapi import FastAPI, Form, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

app = FastAPI(title="Duck the Spam", description="An automated call screener and blacklister.")

DB_FILE = "duck_the_spam.db"

def init_db():
    """Initializes the DuckDB database and creates the blacklist table."""
    conn = duckdb.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            phone_number VARCHAR PRIMARY KEY,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason VARCHAR
        )
    """)
    conn.close()

init_db()

@app.post("/incoming-call")
async def handle_incoming_call(From: str = Form(...)):
    """
    Step 1: Check the blacklist. If clean, prompt the caller for their purpose.
    """
    response = VoiceResponse()
    
    # Check if the number is already in DuckDB
    conn = duckdb.connect(DB_FILE)
    result = conn.execute("SELECT 1 FROM blacklist WHERE phone_number = ?", [From]).fetchone()
    conn.close()
    
    if result:
        # Spammer detected: Drop the call at the carrier level
        response.reject()
        return Response(content=str(response), media_type="application/xml")

    # Caller is unknown: Interrogate them
    gather = Gather(input="speech", action="/process-speech", method="POST", timeout=3)
    gather.say("Hello. You have reached an automated screening service. Please state the purpose of your call after the tone.")
    response.append(gather)
    
    response.say("No input detected. Goodbye.")
    response.hangup()
    
    return Response(content=str(response), media_type="application/xml")


@app.post("/process-speech")
async def process_speech(From: str = Form(...), SpeechResult: str = Form(None)):
    """
    Step 2: Process the transcript. Hang up and blacklist on spam, or take a voicemail.
    """
    response = VoiceResponse()
    
    if not SpeechResult:
        response.say("I did not catch that. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
    
    transcript = SpeechResult.lower()
    trigger_words = ["loan", "funding", "business advance", "pre-approved", "capital", "financing"]
    
    # Check for spam keywords
    if any(word in transcript for word in trigger_words):
        # Drop the Hammer
        response.say(
            "You have reached a restricted number. Your solicitation for a loan or financial service "
            "has been recorded. This number is now permanently closed to your organization. "
            "Remove this number from your dialer immediately. Goodbye."
        )
        response.hangup()
        
        # Blacklist the number in DuckDB
        conn = duckdb.connect(DB_FILE)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO blacklist (phone_number, reason) VALUES (?, ?)", 
                [From, f"Keyword triggered: '{SpeechResult}'"]
            )
        except Exception as e:
            print(f"DB Error: {e}")
        finally:
            conn.close()
            
    else:
        # Legitimate caller fallback (Method 2: Conditional Call Forwarding)
        response.say("Your call has been cleared, but the person you are trying to reach is unavailable. Please leave a message.")
        response.record(max_length=120, action="/voicemail-complete")
        
    return Response(content=str(response), media_type="application/xml")


@app.post("/voicemail-complete")
async def voicemail_complete():
    """Step 3: End the call gracefully after a voicemail is recorded."""
    response = VoiceResponse()
    response.say("Thank you. Your message has been saved. Goodbye.")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")
