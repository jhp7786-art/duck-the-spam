import os
import json
import psycopg2
import requests
import hmac
import hashlib
import time
import logging
import asyncio
from fastapi import FastAPI, Form, Response, Header, HTTPException, Request, Depends, BackgroundTasks
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# Module-level logger — available to all functions below
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please define it in your environment or .env file.")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
API_SECRET_KEY = os.getenv("API_SECRET_KEY")
COMPANY_NAME = os.getenv("COMPANY_NAME", "New Life Appliance Repair")
# WEB_FORM_URL: client-specific URL sent via SMS when caller presses 2
WEB_FORM_URL = os.getenv("WEB_FORM_URL", "")
# MAKE_WEBHOOK_URL: central Make.com scenario endpoint that receives all forwarded payloads
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "")

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
SCHEDULING_LINK = os.getenv("SCHEDULING_LINK", "")
twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")

async def validate_twilio_request(request: Request):
    if not TWILIO_AUTH_TOKEN:
        return
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    if request.headers.get("x-forwarded-proto") == "https" and url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
        
    form_data = await request.form()
    params = dict(form_data)
    
    if not twilio_validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

async def validate_slack_request(request: Request):
    if not SLACK_SIGNING_SECRET:
        return
    
    slack_signature = request.headers.get("X-Slack-Signature", "")
    slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    
    if not slack_signature or not slack_timestamp:
        raise HTTPException(status_code=403, detail="Missing Slack headers")
        
    if abs(time.time() - int(slack_timestamp)) > 60 * 5:
        raise HTTPException(status_code=403, detail="Replay attack detected")
        
    body = await request.body()
    sig_basestring = f"v0:{slack_timestamp}:{body.decode('utf-8')}"
    
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(my_signature, slack_signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL) 

# get_active_protocol() removed — spam defense protocols deprecated.

# Securely loading email and phone info
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
CARRIER_GATEWAY = os.getenv("CARRIER_GATEWAY")

# Using environment variable for VIP list
VIP_NUMBERS = [
    os.getenv("MY_REAL_PHONE_NUMBER")
]
app = FastAPI(title=f"{COMPANY_NAME} Dispatch System", description="Automated client dispatch and call screening service.")

class LeadPayload(BaseModel):
    phone: str
    appliance: str
    issue: str
    name: str = "Unknown"
    address: str = "Unknown"

@app.post("/log-lead")
async def log_lead(payload: LeadPayload, x_api_key: str = Header(None)):
    """Logs incoming leads into PostgreSQL and returns the lead_id."""
    if not API_SECRET_KEY or x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO leads (phone, appliance, issue, status)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                """, (payload.phone, payload.appliance, payload.issue, "Awaiting Booking"))
                lead_id = cur.fetchone()[0]
                
        return {"status": "success", "lead_id": lead_id}
    except Exception as e:
        print(f"Failed to log lead: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}

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
                
                # Create leads table with the requested schema
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS leads (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR,
                        phone VARCHAR,
                        address VARCHAR,
                        appliance VARCHAR,
                        issue VARCHAR,
                        status VARCHAR DEFAULT 'new',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Migrations to support preexisting database structures
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS name VARCHAR;")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS address VARCHAR;")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'new';")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
                
                # Create availability table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS availability (
                        id SERIAL PRIMARY KEY,
                        time_slot VARCHAR UNIQUE,
                        is_open BOOLEAN DEFAULT TRUE
                    )
                """)
                # Seed default availability slots
                cur.execute("""
                    INSERT INTO availability (time_slot, is_open)
                    VALUES ('Today', TRUE), ('Tomorrow AM', TRUE), ('Tomorrow PM', TRUE)
                    ON CONFLICT (time_slot) DO NOTHING
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



@app.post("/incoming-call", dependencies=[Depends(validate_twilio_request)])
async def handle_incoming_call(From: str = Form(...)):
    """
    Inbound call handler.
    Checks VIP whitelist → Blacklist → presents a clean DTMF Gather menu.
    Replaces all previous speech-analysis spam screening logic.
    """
    response = VoiceResponse()

    # ── 1. VIP Whitelist Check (preserved) ──────────────────────────────────
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
        logger.error(f"Error checking VIP list: {e}")
    finally:
        conn.close()

    if is_vip:
        log_call(From, "VIP Bypass", "Routed straight to voicemail")
        if custom_greeting and custom_greeting.strip():
            greeting_text = custom_greeting.strip()
        elif vip_name and vip_name.strip():
            greeting_text = (
                f"Hey {vip_name.strip()}, thanks for calling {COMPANY_NAME}. "
                "I am currently unavailable. Please leave a message and I will get right back to you."
            )
        else:
            greeting_text = (
                f"Hey, thanks for calling {COMPANY_NAME}. "
                "I am currently unavailable. Please leave a message and I will get right back to you."
            )
        response.say(greeting_text)
        response.record(max_length=120, action="/voicemail-complete?dept=vip", transcribe=True,
                        transcribeCallback="/voicemail-complete?dept=vip")
        return Response(content=str(response), media_type="application/xml")

    # ── 2. Blacklist Check (preserved) ──────────────────────────────────────
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM blacklist WHERE phone_number = %s", (From,))
            result = cur.fetchone()
    except Exception as e:
        logger.error(f"Error checking blacklist: {e}")
        result = None
    finally:
        conn.close()

    if result:
        log_call(From, "Blocked", "Rejected — number is blacklisted")
        response.reject()
        return Response(content=str(response), media_type="application/xml")

    # ── 3. DTMF Gather Menu ──────────────────────────────────────────────────
    # This Gather replaces ALL previous speech-analysis/spam-trap logic.
    # numDigits=1 captures a single keypress; timeout=5 gives the caller
    # time to respond before Twilio falls through to the hangup below.
    log_call(From, "Inbound", "Presented DTMF menu")
    gather = Gather(
        input="dtmf",
        action="/gather-result",
        method="POST",
        numDigits=1,
        timeout=5,
    )
    gather.say(
        f"Thank you for calling {COMPANY_NAME}. "
        "Press 1 to leave a voicemail. "
        "Press 2 to receive a text message with a link to our website form."
    )
    response.append(gather)

    # Fallback if the caller does not press anything
    response.say("We did not receive any input. Goodbye.")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


@app.post("/gather-result", dependencies=[Depends(validate_twilio_request)])
async def gather_result(
    From: str = Form(...),
    Digits: str = Form(None),
) -> Response:
    """
    Handles the DTMF keypress from /incoming-call's Gather block.
      1 → record a transcribed voicemail (forwarded to Make on completion)
      2 → send an SMS containing WEB_FORM_URL and hang up
    """
    response = VoiceResponse()

    if Digits == "1":
        # ── Option 1: Voicemail ──────────────────────────────────────────────
        log_call(From, "Voicemail", "Caller chose to leave a voicemail")
        response.say(
            "Please leave your message after the tone. "
            "Press the pound key or hang up when you are finished."
        )
        # transcribeCallback fires when Twilio finishes transcribing;
        # that webhook hit is handled by /voicemail-complete and forwarded to Make.
        response.record(
            max_length=120,
            finish_on_key="#",
            action="/voicemail-complete?dept=caller",
            transcribe=True,
            transcribeCallback="/voicemail-complete?dept=caller",
        )

    elif Digits == "2":
        # ── Option 2: SMS web-form link ──────────────────────────────────────
        # SMS body driven entirely by env vars so it is safe to clone per client.
        log_call(From, "SMS Link", "Caller requested web form link via SMS")
        sms_body = (
            f"Hi, this is {COMPANY_NAME}. "
            f"Please fill out our request form here: {WEB_FORM_URL}. "
            "Reply STOP to unsubscribe."
        )
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
            try:
                twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                twilio_client.messages.create(
                    body=sms_body,
                    from_=TWILIO_PHONE_NUMBER,
                    to=From,
                )
                logger.info(f"Web-form SMS sent to {From}")
            except Exception as e:
                logger.error(f"Failed to send web-form SMS to {From}: {e}")
        else:
            logger.warning("Twilio credentials not fully configured — SMS skipped")

        # ── Make.com Handoff: SMS event ──────────────────────────────────────
        # Package the interaction as a clean JSON dict and fire it at Make.
        # The 5-second timeout prevents this thread from hanging if Make is down.
        _forward_to_make({
            "event": "sms_link_sent",
            "phone": From,
            "company": COMPANY_NAME,
            "web_form_url": WEB_FORM_URL,
        })

        response.say(
            "Perfect. We are sending a text message to your number now. Goodbye."
        )
        response.hangup()

    else:
        # Unrecognised keypress
        log_call(From, "Invalid Input", f"Caller pressed: {Digits}")
        response.say("That was not a valid option. Please call back and try again. Goodbye.")
        response.hangup()

    return Response(content=str(response), media_type="application/xml")


def _forward_to_make(payload: dict) -> None:
    """
    Shared helper that POSTs a JSON payload to MAKE_WEBHOOK_URL.
    Wrapped in try/except with a hard 5-second timeout so a Make.com
    outage never blocks or crashes the FastAPI response thread.
    """
    if not MAKE_WEBHOOK_URL:
        logger.warning("MAKE_WEBHOOK_URL not configured — skipping Make forward")
        return
    try:
        # ── Make.com Webhook Handoff ─────────────────────────────────────────
        r = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=5)
        logger.info(f"Make webhook forwarded. Status: {r.status_code} | Payload keys: {list(payload.keys())}")
    except requests.exceptions.Timeout:
        logger.error("Make webhook timed out after 5 seconds — payload dropped")
    except Exception as e:
        logger.error(f"Make webhook forward failed: {e}")


import smtplib
from email.message import EmailMessage


@app.post("/voicemail-complete", dependencies=[Depends(validate_twilio_request)])
async def voicemail_complete(
    dept: str = None,
    From: str = Form(None),
    RecordingUrl: str = Form(None),
    TranscriptionText: str = Form(None),
    TranscriptionStatus: str = Form(None),
) -> Response:
    """
    Fires when Twilio finishes recording (and optionally transcribing) a voicemail.
    Packages all available data into a clean dict and forwards it to Make.com.
    The Gmail/SMTP carrier-gateway alert is preserved for VIP callers.
    """
    logger.info(f"voicemail-complete: dept={dept}, from={From}, transcription_status={TranscriptionStatus}")

    # ── VIP/cleared email alert (preserved) ─────────────────────────────────
    if dept in ["vip", "cleared"]:
        try:
            if dept == "vip":
                subject = f"{COMPANY_NAME} - VIP Call Alert"
                content = f"\U0001f534 VIP Caller {From} left a message. Listen: {RecordingUrl}"
            else:
                subject = f"{COMPANY_NAME} - Cleared Call Alert"
                content = f"\U0001f7e2 Cleared Caller {From} left a message. Listen: {RecordingUrl}"

            msg = EmailMessage()
            msg.set_content(content)
            msg["Subject"] = subject
            msg["From"] = GMAIL_ADDRESS
            msg["To"] = CARRIER_GATEWAY

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            logger.error(f"Failed to send VIP/cleared SMS alert: {e}")

    # ── Make.com Handoff: voicemail payload ─────────────────────────────────
    # This is the primary handoff point for all completed voicemails.
    # Every field Twilio sends is packaged here; Make can route/filter downstream.
    _forward_to_make({
        "event": "voicemail_complete",
        "dept": dept,
        "phone": From,
        "recording_url": RecordingUrl,
        "transcription_text": TranscriptionText,
        "transcription_status": TranscriptionStatus,
        "company": COMPANY_NAME,
    })

    # Graceful TwiML close — only needed when Twilio calls the action URL,
    # not the transcribeCallback URL (which expects a 200 with empty body).
    response = VoiceResponse()
    response.say("Thank you. Your message has been saved. Goodbye.")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")



class NewLeadPayload(BaseModel):
    name: str
    phone: str
    address: str
    appliance: str
    issue: str

@app.post("/new-lead")
async def receive_new_lead(payload: NewLeadPayload):
    """
    Endpoint 1: Receive New Lead
    - Inserts lead data into the leads table in PostgreSQL.
    - Queries active availability from the availability table.
    - Sends a dynamic Slack Block Kit message with interactive buttons.
    """
    conn = get_db_connection()
    lead_id = None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO leads (name, phone, address, appliance, issue, status)
                    VALUES (%s, %s, %s, %s, %s, 'new')
                    RETURNING id;
                """, (payload.name, payload.phone, payload.address, payload.appliance, payload.issue))
                lead_id = cur.fetchone()[0]
    except Exception as e:
        logger.error(f"Failed to log new lead in database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

    # Query availability
    available_slots = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT time_slot FROM availability WHERE is_open = TRUE;")
            rows = cur.fetchall()
            available_slots = [r[0] for r in rows]
    except Exception as e:
        logger.error(f"Failed to query availability: {e}")
    finally:
        conn.close()

    # Dynamic action buttons mapping
    slot_mapping = {
        "Today": {"action_id": "offer_today", "text": "Offer Today"},
        "Tomorrow AM": {"action_id": "offer_am", "text": "Offer Tomorrow AM"},
        "Tomorrow PM": {"action_id": "offer_pm", "text": "Offer Tomorrow PM"},
    }

    action_elements = []
    
    # Add buttons for open slots
    for slot in available_slots:
        if slot in slot_mapping:
            action_elements.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": slot_mapping[slot]["text"]
                },
                "action_id": slot_mapping[slot]["action_id"],
                "value": str(lead_id)
            })

    # Add static buttons
    action_elements.append({
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": "Send Scheduling Link"
        },
        "action_id": "send_link",
        "value": str(lead_id)
    })
    action_elements.append({
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": "Decline Lead"
        },
        "style": "danger",
        "action_id": "decline_lead",
        "value": str(lead_id)
    })

    slack_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🚨 New Appliance Repair Lead"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Name:*\n{payload.name}"},
                {"type": "mrkdwn", "text": f"*Phone:*\n{payload.phone}"},
                {"type": "mrkdwn", "text": f"*Address:*\n{payload.address}"},
                {"type": "mrkdwn", "text": f"*Appliance:*\n{payload.appliance}"}
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Issue:*\n{payload.issue}"
            }
        },
        {
            "type": "actions",
            "elements": action_elements
        }
    ]

    # Post message to Slack webhook
    if SLACK_WEBHOOK_URL:
        try:
            r = requests.post(SLACK_WEBHOOK_URL, json={"blocks": slack_blocks}, timeout=10)
            logger.info(f"Posted lead {lead_id} message to Slack. Status: {r.status_code}")
        except Exception as e:
            logger.error(f"Failed to post lead message to Slack: {e}")
    else:
        logger.warning("SLACK_WEBHOOK_URL not configured. Skipped posting to Slack.")

    return {"status": "success", "lead_id": lead_id}


async def process_slack_interaction(action_id: str, lead_id: int, response_url: str):
    """
    Processes the interactive Slack action asynchronously to handle database status mapping,
    fail-safe outbound Twilio messaging, and Slack UI feedback updates.
    """
    logger.info(f"Background task: Action '{action_id}' processing for Lead {lead_id}")

    # Action to Status mapping
    status_map = {
        "offer_today": ("offered_today", "Offered Today"),
        "offer_am": ("offered_am", "Offered Tomorrow AM"),
        "offer_pm": ("offered_pm", "Offered Tomorrow PM"),
        "send_link": ("link_sent", "Scheduling Link Sent"),
        "decline_lead": ("declined", "Declined"),
        "schedule_lead": ("Scheduled", "Scheduled"),  # backward compatibility
        "cancel_lead": ("Canceled", "Canceled")        # backward compatibility
    }

    if action_id not in status_map:
        logger.warning(f"Unknown action_id '{action_id}' received.")
        return

    new_status, status_desc = status_map[action_id]

    # 1. Fetch Lead info from database
    conn = None
    lead_phone = None
    lead_appliance = "Appliance"
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT phone, appliance FROM leads WHERE id = %s", (lead_id,))
            row = cur.fetchone()
            if row:
                lead_phone, lead_appliance = row
    except Exception as e:
        logger.error(f"Failed to fetch lead {lead_id} from database: {e}")
    finally:
        if conn:
            conn.close()

    # 2. Twilio SMS Outbound Handling (Fail-Safe)
    sms_sent = False
    sms_body = None

    if action_id == "offer_today":
        sms_body = f"Hi, this is {COMPANY_NAME}. We have an arrival window open today for your {lead_appliance} repair. Would you like to schedule today's arrival window? Reply YES to confirm."
    elif action_id == "offer_am":
        sms_body = f"Hi, this is {COMPANY_NAME}. We have an arrival window open tomorrow morning for your {lead_appliance} repair. Would you like us to schedule you then? Reply YES to confirm."
    elif action_id == "offer_pm":
        sms_body = f"Hi, this is {COMPANY_NAME}. We have an arrival window open tomorrow afternoon for your {lead_appliance} repair. Would you like us to schedule you then? Reply YES to confirm."
    elif action_id == "send_link":
        sms_body = f"Hi, this is {COMPANY_NAME}. Please use this link to schedule your {lead_appliance} repair: {SCHEDULING_LINK}"

    if sms_body and lead_phone:
        if not TWILIO_PHONE_NUMBER:
            logger.warning("Twilio skipped: No phone number configured")
        else:
            try:
                # Initialize Twilio Client dynamically inside try/except block
                if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
                    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                else:
                    twilio_client = Client()

                twilio_client.messages.create(
                    body=sms_body,
                    from_=TWILIO_PHONE_NUMBER,
                    to=lead_phone
                )
                sms_sent = True
                logger.info(f"Successfully sent Twilio SMS to {lead_phone} for lead {lead_id}.")
            except Exception as e:
                logger.warning(f"Twilio SMS sending failed: {e}. Proceeding with database status updates.")

    # 3. Database Update
    db_updated = False
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE leads SET status = %s, updated_at = NOW() WHERE id = %s",
                    (new_status, lead_id)
                )
                db_updated = True
                logger.info(f"Database leads status successfully updated to '{new_status}' for ID {lead_id}.")
    except Exception as e:
        logger.error(f"Failed to update lead {lead_id} status in database: {e}")
    finally:
        if conn:
            conn.close()

    # 4. Slack Feedback Update via response_url
    if response_url:
        emoji = "❌" if action_id == "decline_lead" else "✅"
        feedback_text = f"{emoji} Status updated to {status_desc}"
        if sms_sent:
            feedback_text += f" (outbound SMS sent to {lead_phone})"
        elif sms_body and not sms_sent:
            feedback_text += " (outbound SMS skipped/failed)"

        if not db_updated:
            feedback_text = f"⚠️ DB status update failed. Action attempted: {status_desc}"

        slack_payload = {
            "replace_original": True,
            "text": feedback_text
        }
        try:
            r = requests.post(response_url, json=slack_payload, timeout=10)
            logger.info(f"Posted interactive confirmation back to Slack: Status {r.status_code}")
        except Exception as e:
            logger.error(f"Failed to send confirmation feedback back to Slack: {e}")


@app.post("/slack-interactivity", dependencies=[Depends(validate_slack_request)])
@app.post("/slack/interactivity", dependencies=[Depends(validate_slack_request)])
async def slack_interactivity(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint 2: Slack Interactivity
    - Receives incoming form-encoded payloads from Slack interactive buttons.
    - Responds immediately with HTTP 200 OK to avoid timeout warnings.
    - Launches background tasks to run database updates, Twilio SMS routing, and Slack UI refreshes.
    """
    form_data = await request.form()
    payload = form_data.get("payload")
    if not payload:
        return Response(content="Missing payload field", status_code=400)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return Response(content="Invalid JSON format in payload", status_code=400)

    actions = data.get("actions", [])
    if not actions:
        return Response(content="Missing actions array", status_code=400)

    action = actions[0]
    action_id = action.get("action_id")
    value = action.get("value")
    response_url = data.get("response_url")

    if not action_id or not value:
        return Response(content="Missing interactive action elements", status_code=400)

    try:
        lead_id = int(value)
    except ValueError:
        return Response(content="Invalid lead_id structure", status_code=400)

    # Dispatch to background task execution
    background_tasks.add_task(
        process_slack_interaction,
        action_id,
        lead_id,
        response_url
    )

    # Return HTTP 200 immediately
    return Response(status_code=200)


async def check_stale_leads():
    """
    Queries Neon DB for any leads where status = 'new' and created_at is older than 30 minutes.
    Sends a Slack alert for every stale lead found.
    """
    logger.info("Executing stale lead check...")
    conn = None
    stale_leads = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, phone FROM leads
                WHERE status = 'new' AND created_at < NOW() - INTERVAL '30 minutes';
            """)
            rows = cur.fetchall()
            stale_leads = [{"name": r[0] or "Unknown", "phone": r[1] or "Unknown"} for r in rows]
    except Exception as e:
        logger.error(f"Error querying stale leads from PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()

    if not stale_leads:
        logger.info("No stale leads found.")
        return

    logger.info(f"Found {len(stale_leads)} stale leads. Sending notifications...")
    for lead in stale_leads:
        name = lead["name"]
        phone = lead["phone"]
        alert_text = f"⚠️ *Stale Lead Alert!* Lead *{name}* ({phone}) has been waiting for over 30 minutes!"
        
        if SLACK_WEBHOOK_URL:
            try:
                r = requests.post(SLACK_WEBHOOK_URL, json={"text": alert_text}, timeout=10)
                logger.info(f"Stale lead alert sent for {name}. Status: {r.status_code}")
            except Exception as e:
                logger.error(f"Failed to post stale lead alert to Slack for {name}: {e}")
        else:
            logger.warning(f"SLACK_WEBHOOK_URL not configured. Alert skipped for {name}.")


async def check_stale_leads_loop():
    """
    Continuous background loop that runs the stale check logic every 15 minutes.
    """
    logger.info("Starting stale lead check background loop (every 15 minutes)...")
    while True:
        try:
            await check_stale_leads()
        except Exception as e:
            logger.error(f"Exception in check_stale_leads_loop: {e}")
        await asyncio.sleep(15 * 60)


@app.on_event("startup")
async def startup_event():
    """
    FastAPI startup event that launches the background task loop.
    """
    asyncio.create_task(check_stale_leads_loop())
