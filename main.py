import os
import random
import urllib.parse
import psycopg2
import requests 
from fastapi import FastAPI, Form, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please define it in your environment or .env file.")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "") 

def get_db_connection():
    return psycopg2.connect(DATABASE_URL) 

def get_active_protocol():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = 'spam_protocol'")
            row = cur.fetchone()
            mode = row[0].upper() if row else "JOHN"
            
            if mode == "SHUFFLE":
                chosen = random.choice(["JOHN", "TODDLER", "PARROT", "HAMMER"])
                print(f"[SHUFFLE] Dynamically selected protocol: {chosen}")
                return chosen
            return mode
    except Exception as e:
        print(f"Error reading active protocol: {e}")
        return "JOHN"
    finally:
        conn.close() 

# Securely loading your email and phone info
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
CARRIER_GATEWAY = os.getenv("CARRIER_GATEWAY")

# Using your environment variable for the VIP list
VIP_NUMBERS = [
    os.getenv("MY_REAL_PHONE_NUMBER")
]
app = FastAPI(title="Duck the Spam", description="A multi-mode automated call screener.")

@app.get("/")
def read_root():
    return {"status": "Spam trap is armed and active"}

def init_db():
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Create tables if they don't exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS blacklist (
                        phone_number VARCHAR PRIMARY KEY,
                        blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        reason VARCHAR
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vip (
                        phone_number VARCHAR PRIMARY KEY,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        name VARCHAR
                    )
                """)
                cur.execute("ALTER TABLE vip ADD COLUMN IF NOT EXISTS custom_greeting VARCHAR;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS call_logs (
                        id SERIAL PRIMARY KEY,
                        phone_number VARCHAR,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        call_type VARCHAR,
                        details VARCHAR
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key VARCHAR PRIMARY KEY,
                        value VARCHAR
                    )
                """)
                cur.execute("""
                    INSERT INTO app_settings (key, value)
                    VALUES ('spam_protocol', 'JOHN')
                    ON CONFLICT (key) DO NOTHING
                """)
                
                # 2. THE ROLL-OFF: Automatically purge numbers older than 30 days
                try:
                    cur.execute("DELETE FROM blacklist WHERE blocked_at < NOW() - INTERVAL '30 days'")
                except Exception as e:
                    print(f"Database cleanup error: {e}")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
    finally:
        conn.close()

def log_call(phone_number: str, call_type: str, details: str):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO call_logs (phone_number, call_type, details) VALUES (%s, %s, %s)",
                    (phone_number, call_type, details)
                )
    except Exception as e:
        print(f"Failed to log call: {e}")
    finally:
        conn.close()

init_db()

@app.post("/incoming-call")
async def handle_incoming_call(From: str = Form(...)):
    """Step 1: VIP Check, Blacklist Check, and The Henegar Services Menu."""
    response = VoiceResponse()
    
    # 1. VIP Bypass (Family/Friends)
    is_vip = False
    vip_name = None
    custom_greeting = None
    
    if From in VIP_NUMBERS:
        is_vip = True
        vip_name = "Jeffery"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, custom_greeting FROM vip WHERE phone_number = %s", (From,))
            row = cur.fetchone()
            if row:
                is_vip = True
                vip_name = row[0]
                custom_greeting = row[1]
    except Exception as e:
        print(f"Error checking VIP list: {e}")
    finally:
        conn.close()

    if is_vip:
        log_call(From, "VIP Bypass", "Routed straight to voicemail")
        
        # Determine the greeting message dynamically
        if custom_greeting and custom_greeting.strip():
            greeting_text = custom_greeting.strip()
        elif vip_name and vip_name.strip():
            greeting_text = f"Hey {vip_name.strip()}, I am currently tied up or on a ladder. Please leave a message and I will get right back to you."
        else:
            greeting_text = "Hey, I am currently tied up or on a ladder. Please leave a message and I will get right back to you."
            
        response.say(greeting_text)
        response.record(max_length=120, action="/voicemail-complete?dept=vip")
        return Response(content=str(response), media_type="application/xml")

    # 2. Blacklist Check
    result = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM blacklist WHERE phone_number = %s", (From,))
            result = cur.fetchone()
    except Exception as e:
        print(f"Error checking blacklist: {e}")
    finally:
        conn.close()
    
    if result:
        log_call(From, "Blocked Spammer", "Rejected call automatically")
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
        log_call(From, "Legitimate (Paint)", "Pressed 1 - Paint Voicemail")
        response.say("Transferring you to the voicemail for Henegar Painting. Please leave your name, number, and project details.")
        # Notice the ?dept=paint tag added to the action URL
        response.record(max_length=120, action="/voicemail-complete?dept=paint")
        return Response(content=str(response), media_type="application/xml")
        
    elif Digits == "2":
        log_call(From, "Legitimate (Systems)", "Pressed 2 - Systems Voicemail")
        response.say("Transferring you to the voicemail for Henegar Systems. Please leave your name, number, and service request.")
        # Notice the ?dept=systems tag added to the action URL
        response.record(max_length=120, action="/voicemail-complete?dept=systems")
        return Response(content=str(response), media_type="application/xml")

    # --- SPAM SCREENING ---
    if not SpeechResult:
        log_call(From, "No Input / Timeout", "No digits pressed or speech detected")
        response.say("I did not catch that. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
        
    transcript = SpeechResult.lower()
    trigger_words = ["loan", "funding", "business advance", "pre-approved", "capital", "financing"]
    
    if any(word in transcript for word in trigger_words) or "warranty" in transcript:
        # Log the spammer
        conn = get_db_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO blacklist (phone_number, reason) VALUES (%s, %s) ON CONFLICT (phone_number) DO NOTHING",
                        (From, f"Caught: '{SpeechResult}'")
                    )
        except Exception as e:
            print(f"Error blacklisting spammer: {e}")
        finally:
            conn.close()
            
        active_protocol = get_active_protocol()
        log_call(From, f"Spam ({active_protocol})", f"Trigger word matched: '{SpeechResult}'")
        
        if active_protocol == "JOHN":
            encoded_speech = urllib.parse.quote(SpeechResult)
            response.redirect(f"/protocol-john?SpeechResult={encoded_speech}")
        elif active_protocol == "TODDLER":
            response.redirect("/protocol-toddler")
        elif active_protocol == "PARROT":
            encoded_speech = urllib.parse.quote(SpeechResult)
            response.redirect(f"/protocol-parrot?phrase={encoded_speech}")
        else:
            response.redirect("/protocol-hammer")
            
    else:
        # Unknown but potentially legitimate caller who spoke instead of pressing a button
        log_call(From, "Unknown (Speech)", f"Spoke: '{SpeechResult}'")
        response.say("Your call has been cleared, but the person you are trying to reach is unavailable. Please leave a message.")
        response.record(max_length=120, action="/voicemail-complete?dept=cleared")
        
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
    
   # 1. Route to SMS (For Paint Jobs, VIP Bypass, and Cleared Callers)
    if dept in ["paint", "vip", "cleared"]:
        try:
            if dept == "vip":
                subject = "VIP Call Alert"
                content = f"🔴 VIP Caller {From} left a message. Listen: {RecordingUrl}"
            elif dept == "cleared":
                subject = "Cleared Call Alert"
                content = f"🟢 Cleared Caller {From} left a message. Listen: {RecordingUrl}"
            else: # paint
                subject = "Paint Lead"
                content = f"New Paint Lead from {From}. Listen here: {RecordingUrl}"

            msg = EmailMessage()
            msg.set_content(content)
            msg['Subject'] = subject
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
