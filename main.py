import os
import urllib.parse
import duckdb
import requests 
from fastapi import FastAPI, Form, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SPAM_PROTOCOL = os.getenv("SPAM_PROTOCOL", "JOHN").upper() 
DB_FILE = "duck_the_spam.db"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "") 

# Securely loading your email and phone info
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
CARRIER_GATEWAY = os.getenv("CARRIER_GATEWAY")

# Using your environment variable for the VIP list
VIP_NUMBERS = [
    os.getenv("MY_REAL_PHONE_NUMBER")
]
app = FastAPI(title="Duck the Spam", description="A multi-mode automated call screener.")

def init_db():
    conn = duckdb.connect(DB_FILE)
    # 1. Create the table if it doesn't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            phone_number VARCHAR PRIMARY KEY,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason VARCHAR
        )
    """)
    
    # 2. THE ROLL-OFF: Automatically purge numbers older than 30 days
    try:
        conn.execute("DELETE FROM blacklist WHERE blocked_at < NOW() - INTERVAL '30 days'")
    except Exception as e:
        print(f"Database cleanup error: {e}")
        
    conn.close()

init_db()

@app.post("/incoming-call")
async def handle_incoming_call(From: str = Form(...)):
    """Step 1: VIP Check, Blacklist Check, and The Henegar Services Menu."""
    response = VoiceResponse()
    
    # 1. VIP Bypass (Family/Friends)
    if From in VIP_NUMBERS:
        response.say("Hey, I am currently tied up or on a ladder. Please leave a message and I will get right back to you.")
        response.record(max_length=120, action="/voicemail-complete")
        return Response(content=str(response), media_type="application/xml")

    # 2. Blacklist Check
    conn = duckdb.connect(DB_FILE)
    result = conn.execute("SELECT 1 FROM blacklist WHERE phone_number = ?", [From]).fetchone()
    conn.close()
    
    if result:
        response.reject()
        return Response(content=str(response), media_type="application/xml")
        
    # 3. The Professional Menu
    gather = Gather(
        input="dtmf speech", 
        action="/process-menu", 
        method="POST", 
        numDigits=1, 
        timeout=4
    )
    
    gather.say(
        "You have reached Henegar Services. "
        "To leave a message for Henegar Painting, press 1. "
        "For Henegar Systems, press 2. "
        "Otherwise, please state your name and the purpose of your call."
    )
    response.append(gather)
    
    response.say("No input detected. Goodbye.")
    response.hangup()
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/process-menu")
async def process_menu(From: str = Form(...), Digits: str = Form(None), SpeechResult: str = Form(None)):
    """Step 2: Route button presses or analyze speech for spam."""
    response = VoiceResponse()
    
   # --- LEGITIMATE CLIENT ROUTING ---
    if Digits == "1":
        response.say("Transferring you to the voicemail for Henegar Painting. Please leave your name, number, and project details.")
        # Notice the ?dept=paint tag added to the action URL
        response.record(max_length=120, action="/voicemail-complete?dept=paint")
        return Response(content=str(response), media_type="application/xml")
        
    elif Digits == "2":
        response.say("Transferring you to the voicemail for Henegar Systems. Please leave your name, number, and service request.")
        # Notice the ?dept=systems tag added to the action URL
        response.record(max_length=120, action="/voicemail-complete?dept=systems")
        return Response(content=str(response), media_type="application/xml")

    # --- SPAM SCREENING ---
    if not SpeechResult:
        response.say("I did not catch that. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
        
    transcript = SpeechResult.lower()
    trigger_words = ["loan", "funding", "business advance", "pre-approved", "capital", "financing"]
    
    if any(word in transcript for word in trigger_words) or "warranty" in transcript:
        # Log the spammer
        conn = duckdb.connect(DB_FILE)
        try:
            conn.execute("INSERT OR IGNORE INTO blacklist (phone_number, reason) VALUES (?, ?)", 
                         [From, f"Caught: '{SpeechResult}'"])
        except Exception as e:
            pass
        finally:
            conn.close()
            
        if SPAM_PROTOCOL == "JOHN":
            encoded_speech = urllib.parse.quote(SpeechResult)
            response.redirect(f"/protocol-john?SpeechResult={encoded_speech}")
        elif SPAM_PROTOCOL == "TODDLER":
            response.redirect("/protocol-toddler")
        elif SPAM_PROTOCOL == "PARROT":
            encoded_speech = urllib.parse.quote(SpeechResult)
            response.redirect(f"/protocol-parrot?phrase={encoded_speech}")
        else:
            response.redirect("/protocol-hammer")
            
    else:
        # Unknown but potentially legitimate caller who spoke instead of pressing a button
        response.say("Your call has been cleared, but the person you are trying to reach is unavailable. Please leave a message.")
        response.record(max_length=120, action="/voicemail-complete")
        
    return Response(content=str(response), media_type="application/xml")


@app.post("/incoming-sms")
async def incoming_sms(From: str = Form(...), Body: str = Form(...)):
    """Phase 1: Catch incoming texts and send a push notification to Slack."""
    
    if SLACK_WEBHOOK_URL:
        slack_payload = {
            "text": f"🚨 *New Henegar Services Lead*\n*Number:* {From}\n*Message:* {Body}"
        }
        try:
            requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
        except Exception as e:
            print(f"Failed to send Slack alert: {e}")
            
    # Return an empty XML response so Twilio doesn't try to send an SMS reply
    return Response(content="<Response></Response>", media_type="application/xml")


# ==========================================
# DEFENSE PROTOCOLS
# ==========================================

@app.post("/protocol-john")
async def protocol_john(SpeechResult: str = None):
    response = VoiceResponse()
    caller_name = ""
    if SpeechResult:
        transcript = urllib.parse.unquote(SpeechResult).lower()
        if "this is " in transcript:
            parts = transcript.split("this is ")
            if len(parts) > 1 and parts[1].strip(): caller_name = parts[1].split()[0] 
        elif "name is " in transcript:
            parts = transcript.split("name is ")
            if len(parts) > 1 and parts[1].strip(): caller_name = parts[1].split()[0]
            
    greeting_name = f", {caller_name.capitalize()}," if caller_name else ","
    response.say(f"Oh thank god{greeting_name} I am so glad we found you! We have been trying to reach you about your extended car warranty!", voice="Polly.Matthew-Neural", language="en-US")
    response.say("Wonk, wonk, wonk.", voice="Polly.Matthew-Neural", language="en-US")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")

@app.post("/protocol-hammer")
async def protocol_hammer():
    response = VoiceResponse()
    response.say("You have reached a restricted number. Remove this number from your dialer immediately. Goodbye.")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")

@app.post("/protocol-toddler")
async def protocol_toddler(SpeechResult: str = Form(None)):
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
    response = VoiceResponse()
    text_to_parrot = SpeechResult if SpeechResult else phrase
    if not text_to_parrot:
        response.say("Cat got your tongue? Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
    gather = Gather(input="speech", action="/protocol-parrot", method="POST", timeout=3)
    gather.say(text_to_parrot)
    response.append(gather)
    return Response(content=str(response), media_type="application/xml")

import smtplib
from email.message import EmailMessage

@app.post("/voicemail-complete")
async def voicemail_complete(
    dept: str = None, 
    From: str = Form(None), 
    RecordingUrl: str = Form(None)
):
    """Catches the finished voicemail and routes the alert based on the department."""
    
   # 1. Route to SMS (For Paint Jobs)
    if dept == "paint":
        try:
            msg = EmailMessage()
            msg.set_content(f"New Paint Lead from {From}. Listen here: {RecordingUrl}")
            msg['Subject'] = 'Paint Lead'
            msg['From'] = GMAIL_ADDRESS
            msg['To'] = CARRIER_GATEWAY
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            print(f"Failed to send SMS Alert: {e}")

    # 2. Route to Slack (For IT/Systems Jobs)
    elif dept == "systems":
        if SLACK_WEBHOOK_URL:
            slack_payload = {
                "text": f"💻 *New IT/Systems Lead*\n*Number:* {From}\n*Voicemail:* {RecordingUrl}"
            }
            try:
                requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
            except Exception as e:
                print(f"Failed to send Slack alert: {e}")

    # 3. Always hang up gracefully
    response = VoiceResponse()
    response.say("Thank you. Your message has been saved. Goodbye.")
    response.hangup()
    
    return Response(content=str(response), media_type="application/xml")
