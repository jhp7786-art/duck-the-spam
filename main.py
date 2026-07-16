import os
import urllib.parse
import duckdb
from fastapi import FastAPI, Form, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Defaulting to JOHN so it hits your new trap immediately
SPAM_PROTOCOL = os.getenv("SPAM_PROTOCOL", "JOHN").upper() 

app = FastAPI(title="Duck the Spam", description="A multi-mode automated call screener.")

DB_FILE = "duck_the_spam.db"

def init_db():
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
    """Step 1: Database Check & Initial Interrogation."""
    response = VoiceResponse()
    
    conn = duckdb.connect(DB_FILE)
    result = conn.execute("SELECT 1 FROM blacklist WHERE phone_number = ?", [From]).fetchone()
    conn.close()
    
    if result:
        response.reject()
        return Response(content=str(response), media_type="application/xml")
        
    gather = Gather(input="speech", action="/process-speech", method="POST", timeout=3)
    # Tweak the greeting slightly to encourage them to say their name
    gather.say("Hello. You have reached an automated screening service. Please state your name and the purpose of your call.")
    response.append(gather)
    
    response.say("No input detected. Goodbye.")
    response.hangup()
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/process-speech")
async def process_speech(From: str = Form(...), SpeechResult: str = Form(None)):
    """Step 2: Keyword screening and Protocol Routing."""
    response = VoiceResponse()
    
    if not SpeechResult:
        response.say("I did not catch that. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
        
    transcript = SpeechResult.lower()
    
    # Financial Spammer Check
    trigger_words = ["loan", "funding", "business advance", "pre-approved", "capital", "financing"]
    
    if any(word in transcript for word in trigger_words):
        # Log the spammer immediately
        conn = duckdb.connect(DB_FILE)
        try:
            conn.execute("INSERT OR IGNORE INTO blacklist (phone_number, reason) VALUES (?, ?)", 
                         [From, f"Keyword triggered: '{SpeechResult}'"]
            )
        except Exception as e:
            print(f"DB Error: {e}")
        finally:
            conn.close()
            
        # Route to the chosen punishment based on .env
        if SPAM_PROTOCOL == "TODDLER":
            response.redirect("/protocol-toddler")
        elif SPAM_PROTOCOL == "PARROT":
            encoded_speech = urllib.parse.quote(SpeechResult)
            response.redirect(f"/protocol-parrot?phrase={encoded_speech}")
        elif SPAM_PROTOCOL == "JOHN":
            # Pass their speech to John so we can steal their name
            encoded_speech = urllib.parse.quote(SpeechResult)
            response.redirect(f"/protocol-john?SpeechResult={encoded_speech}")
        else:
            response.redirect("/protocol-hammer")
            
    else:
        # Legitimate caller fallback
        response.say("Your call has been cleared, but the person you are trying to reach is unavailable. Please leave a message.")
        response.record(max_length=120, action="/voicemail-complete")
        
    return Response(content=str(response), media_type="application/xml")


# ==========================================
# DEFENSE PROTOCOLS
# ==========================================

@app.post("/protocol-john")
async def protocol_john(SpeechResult: str = None):
    """The John: UNO Reverse card on the car warranty pitch."""
    response = VoiceResponse()
    
    caller_name = ""
    if SpeechResult:
        transcript = urllib.parse.unquote(SpeechResult).lower()
        
        # Quick and dirty name extraction from standard intros
        if "this is " in transcript:
            parts = transcript.split("this is ")
            if len(parts) > 1 and parts[1].strip():
                caller_name = parts[1].split()[0] 
        elif "name is " in transcript:
            parts = transcript.split("name is ")
            if len(parts) > 1 and parts[1].strip():
                caller_name = parts[1].split()[0]
    
    # If we caught a name, use it. Otherwise, drop the name seamlessly.
    greeting_name = f", {caller_name.capitalize()}," if caller_name else ","
    
    # The Trap
    response.say(
        f"Oh thank god{greeting_name} I am so glad we found you! We have been trying to reach you about your extended car warranty!",
        voice="Polly.Matthew-Neural",
        language="en-US"
    )
    
    # The disrespect
    response.say(
        "Wonk, wonk, wonk.",
        voice="Polly.Matthew-Neural",
        language="en-US"
    )
    
    response.hangup()
    return Response(content=str(response), media_type="application/xml")

@app.post("/protocol-hammer")
async def protocol_hammer():
    """The Hammer: Stern warning and immediate disconnect."""
    response = VoiceResponse()
    response.say("You have reached a restricted number. Your solicitation has been recorded. "
                 "Remove this number from your dialer immediately. Goodbye."
                 )
    response.hangup()
    return Response(content=str(response), media_type="application/xml")

@app.post("/protocol-toddler")
async def protocol_toddler(SpeechResult: str = Form(None)):
    """The Toddler: Infinite loop asking 'Why?' until they rage quit."""
    response = VoiceResponse()
    
    if not SpeechResult:
        response.say("That is what I thought. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
        
    gather = Gather(input="speech", action="/protocol-toddler", method="POST", timeout=3)
    gather.say("Why?")
    response.append(gather)
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/protocol-parrot")
async def protocol_parrot(phrase: str = None, SpeechResult: str = Form(None)):
    """The Parrot: Echoes their exact words back at them in an infinite loop."""
    response = VoiceResponse()
    
    # Use the phrase passed from the URL query on the first loop, then their ongoing speech
    text_to_parrot = SpeechResult if SpeechResult else phrase
    
    if not text_to_parrot:
        response.say("Cat got your tongue? Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
        
    gather = Gather(input="speech", action="/protocol-parrot", method="POST", timeout=3)
    gather.say(text_to_parrot)
    response.append(gather)
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/voicemail-complete")
async def voicemail_complete():
    """Ends the call gracefully after a legitimate caller leaves a voicemail."""
    response = VoiceResponse()
    response.say("Thank you. Your message has been saved. Goodbye.")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")
