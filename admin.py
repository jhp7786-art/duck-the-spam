import streamlit as st
import psycopg2
import pandas as pd
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    st.error("DATABASE_URL environment variable is not set. Please define it in your .env file or environment.")
    st.stop()

COMPANY_NAME = os.getenv("COMPANY_NAME", "New Life Appliance Repair")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def db_execute(query, params=None):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
    finally:
        conn.close()

def fetch_dataframe(query, params=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            return pd.DataFrame(data, columns=columns)
    finally:
        conn.close()

# Initialize DB structure
def ensure_db():
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
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
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS leads (
                        id SERIAL PRIMARY KEY,
                        phone VARCHAR,
                        appliance VARCHAR,
                        issue VARCHAR,
                        status VARCHAR DEFAULT 'Awaiting Booking',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
    finally:
        conn.close()

ensure_db()

st.set_page_config(page_title="New Life Dispatch", page_icon="https://raw.githubusercontent.com/jhp7786-art/jhp7786-art/main/collab-logo.svg", layout="wide")

st.title(f"📞 {COMPANY_NAME} Dispatch Command Center")
st.markdown("---")

# ==========================================
# 1. MODE SELECTOR (SPAM DEFENSE PROTOCOL)
# ==========================================
st.header("🛡️ Active Spam Defense Protocol")

# Read current mode from database, default to JOHN
current_mode = "JOHN"
try:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = 'spam_protocol'")
        row = cur.fetchone()
        if row:
            current_mode = row[0].upper()
except Exception as e:
    st.error(f"Error loading active protocol from database: {e}")
finally:
    if 'conn' in locals() and conn:
        conn.close()

modes = {
    "JOHN": {
        "title": "🎭 The 'John' (UNO Reverse)",
        "desc": "Stalls spammers by pretending to be their long-lost friend 'John' asking about extended car warranty, ending with a sarcastic sound effect."
    },
    "TODDLER": {
        "title": "👶 The Toddler",
        "desc": "Traps callers in an endless loop interrupting their pitch by asking 'Why?' every time they stop speaking."
    },
    "PARROT": {
        "title": "🦜 The Parrot",
        "desc": "Echoes the spammer's exact words back in a robotic voice loop until they hang up."
    },
    "HAMMER": {
        "title": "🔨 The Hammer",
        "desc": "Warns the caller that their number is logged and blacklisted, then immediately disconnects."
    },
    "SHUFFLE": {
        "title": "🔀 The Shuffle (Random)",
        "desc": "Randomly selects a different defense protocol (John, Toddler, Parrot, or Hammer) for each screened spam call."
    }
}

mode_keys = list(modes.keys())
default_index = mode_keys.index(current_mode) if current_mode in mode_keys else 0

selected_key = st.selectbox(
    "Select Active Trap Mode:", 
    options=mode_keys, 
    format_func=lambda x: modes[x]["title"],
    index=default_index
)

st.info(modes[selected_key]["desc"])

if st.button("Apply Selected Protocol"):
    try:
        db_execute(
            "INSERT INTO app_settings (key, value) VALUES ('spam_protocol', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (selected_key,)
        )
        st.success(f"Successfully switched to {modes[selected_key]['title']}!")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to apply protocol: {e}")

st.markdown("---")

# ==========================================
# 2. CLIENT LEADS & MANAGEMENT TABS
# ==========================================
tab_leads, tab_logs, tab_vip, tab_blacklist = st.tabs([
    "📋 Client Leads",
    "📊 Call Logs",
    f"🔑 {COMPANY_NAME} VIP Whitelist",
    f"🚫 {COMPANY_NAME} Blacklisted Spammers"
])

# --- TAB 1: CLIENT LEADS ---
with tab_leads:
    st.header(f"📋 {COMPANY_NAME} Client Leads")
    st.write("Incoming leads logged via Twilio Studio webhooks.")
    
    try:
        leads_df = fetch_dataframe(
            "SELECT id, phone AS \"Phone\", appliance AS \"Appliance\", issue AS \"Issue\", status AS \"Status\", created_at AS \"Created At\" FROM leads ORDER BY created_at DESC"
        )
        
        if not leads_df.empty:
            edited_df = st.data_editor(
                leads_df,
                hide_index=True,
                disabled=["id", "Phone", "Appliance", "Issue", "Created At"],
                column_config={
                    "Status": st.column_config.SelectboxColumn(
                        "Status",
                        options=["Awaiting Booking", "Scheduled", "Completed", "Canceled"],
                        required=True,
                    )
                },
                use_container_width=True,
                key="leads_editor"
            )
            
            if st.button("Save Changes", key="save_leads_changes"):
                edited_rows = st.session_state["leads_editor"].get("edited_rows", {})
                if edited_rows:
                    for row_idx, edits in edited_rows.items():
                        if "Status" in edits:
                            new_status = edits["Status"]
                            lead_id = int(leads_df.iloc[int(row_idx)]["id"])
                            db_execute("UPDATE leads SET status = %s WHERE id = %s", (new_status, lead_id))
                    
                    st.success("Changes saved successfully!")
                    st.rerun()
        else:
            st.info("No client leads logged yet. Webhooks received from Twilio Studio will appear here.")
    except Exception as e:
        st.error(f"Error loading client leads: {e}")

# --- TAB 2: CALL LOGS ---
with tab_logs:
    st.header("📊 Call Log Command Center")
    st.write("Click any row in the log below to view caller history and take quick actions.")
    
    try:
        call_logs = fetch_dataframe(
            "SELECT id, phone_number, timestamp, call_type, details FROM call_logs ORDER BY timestamp DESC LIMIT 50"
        )
        
        if not call_logs.empty:
            event = st.dataframe(
                call_logs,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="call_logs_table"
            )
            
            selected_rows = event.selection.rows
            if selected_rows:
                row_idx = selected_rows[0]
                selected_phone = call_logs.iloc[row_idx]["phone_number"]
                
                st.markdown(f"### ⚡ Quick Actions for: `{selected_phone}`")
                
                conn = get_db_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT name FROM vip WHERE phone_number = %s", (selected_phone,))
                        is_vip = cur.fetchone()
                        cur.execute("SELECT reason FROM blacklist WHERE phone_number = %s", (selected_phone,))
                        is_blocked = cur.fetchone()
                finally:
                    conn.close()
                
                col_act1, col_act2 = st.columns(2)
                
                with col_act1:
                    if is_vip:
                        st.info(f"🔑 This number is in your VIP list (as '{is_vip[0]}').")
                        if st.button("Remove from VIP List", key="remove_vip_from_logs"):
                            db_execute("DELETE FROM vip WHERE phone_number = %s", (selected_phone,))
                            st.success(f"Removed {selected_phone} from VIP list.")
                            st.rerun()
                    else:
                        st.write("**Add to VIP List**")
                        vip_name_input = st.text_input("Contact Name:", value="Unnamed VIP", key="vip_name_from_logs")
                        vip_greeting_input = st.text_input("Custom Greeting (Optional):", placeholder="e.g. Welcome Bob!", key="vip_greeting_from_logs")
                        if st.button("Add to VIP List", key="add_vip_from_logs"):
                            db_execute("DELETE FROM blacklist WHERE phone_number = %s", (selected_phone,))
                            db_execute("INSERT INTO vip (phone_number, name, custom_greeting) VALUES (%s, %s, %s) ON CONFLICT (phone_number) DO UPDATE SET name = EXCLUDED.name, custom_greeting = EXCLUDED.custom_greeting", (selected_phone, vip_name_input, vip_greeting_input.strip() or None))
                            st.success(f"Added {selected_phone} to VIP List!")
                            st.rerun()
                            
                with col_act2:
                    if is_blocked:
                        st.info(f"🚫 This number is blocked (Reason: '{is_blocked[0]}').")
                        if st.button("Forgive Caller (Unban)", key="unban_from_logs"):
                            db_execute("DELETE FROM blacklist WHERE phone_number = %s", (selected_phone,))
                            st.success(f"Removed {selected_phone} from blacklist.")
                            st.rerun()
                    else:
                        st.write("**Block Caller**")
                        block_reason_input = st.text_input("Reason for block:", value="Manual Block", key="block_reason_from_logs")
                        if st.button("Block Number", key="block_from_logs"):
                            db_execute("DELETE FROM vip WHERE phone_number = %s", (selected_phone,))
                            db_execute("INSERT INTO blacklist (phone_number, reason) VALUES (%s, %s) ON CONFLICT (phone_number) DO NOTHING", (selected_phone, block_reason_input))
                            st.success(f"Blocked {selected_phone}!")
                            st.rerun()
        else:
            st.info("No calls logged yet.")
    except Exception as e:
        st.error(f"Could not load call logs: {e}")
        
    st.markdown("---")
    st.subheader("Convert Voicemail to Lead")
    with st.form("voicemail_to_lead_form"):
        caller_phone = st.text_input("Caller Phone")
        caller_name = st.text_input("Caller Name")
        appliance = st.selectbox("Appliance Type", ["Refrigerator", "Washer", "Dryer", "Oven / Stove", "Dishwasher", "Microwave", "Other"])
        issue = st.text_area("Issue")
        
        submit_btn = st.form_submit_button("Send to Automation Pipeline")
        
        if submit_btn:
            payload = {
                "Name": caller_name,
                "Phone": caller_phone,
                "Appliance": appliance,
                "Issue": issue
            }
            try:
                response = requests.post(MAKE_WEBHOOK_URL, json=payload)
                response.raise_for_status()
                st.success("Successfully sent to automation pipeline!")
            except Exception as req_e:
                st.error(f"Failed to send to webhook: {req_e}")

# --- TAB 3: VIP WHITELIST ---
with tab_vip:
    st.header(f"🔑 {COMPANY_NAME} VIP Whitelist")
    st.write("Numbers on this list bypass call screening and route straight to voicemail.")
    
    st.subheader("Add Contact Manually")
    manual_col1, manual_col2, manual_col3 = st.columns(3)
    with manual_col1:
        new_vip_name = st.text_input("Contact Name:", key="vip_name_input")
    with manual_col2:
        new_vip_number = st.text_input("VIP Phone Number (Format: +1256...):", key="vip_num_input")
    with manual_col3:
        new_vip_greeting = st.text_input("Custom Greeting (Optional):", placeholder="e.g. Welcome Bob!", key="vip_greeting_input")
        
    if st.button("Add to VIP List", key="add_vip_manual"):
        if new_vip_number.strip():
            try:
                db_execute("DELETE FROM blacklist WHERE phone_number = %s", (new_vip_number.strip(),))
                db_execute("INSERT INTO vip (phone_number, name, custom_greeting) VALUES (%s, %s, %s) ON CONFLICT (phone_number) DO UPDATE SET name = EXCLUDED.name, custom_greeting = EXCLUDED.custom_greeting", 
                             (new_vip_number.strip(), new_vip_name.strip() or "Unnamed VIP", new_vip_greeting.strip() or None))
                st.success(f"Added {new_vip_number.strip()} to VIP List!")
                st.rerun()
            except Exception as e:
                st.error(f"Error adding VIP: {e}")
        else:
            st.error("Phone number is required.")
            
    st.subheader("Current VIP Contacts")
    try:
        vip_data = fetch_dataframe("SELECT phone_number, name, custom_greeting, added_at FROM vip ORDER BY added_at DESC")
        
        if not vip_data.empty:
            event_vip = st.dataframe(
                vip_data,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="vip_table"
            )
            
            selected_vip_rows = event_vip.selection.rows
            selected_vip_phone = None
            if selected_vip_rows:
                selected_vip_phone = vip_data.iloc[selected_vip_rows[0]]["phone_number"]
            
            vip_to_remove = st.selectbox("Select a VIP number to manage:", vip_data["phone_number"], 
                                         index=vip_data["phone_number"].tolist().index(selected_vip_phone) if selected_vip_phone in vip_data["phone_number"].tolist() else 0)
            
            vip_col1, vip_col2 = st.columns(2)
            with vip_col1:
                if st.button("Remove VIP", key="remove_vip_btn"):
                    db_execute("DELETE FROM vip WHERE phone_number = %s", (vip_to_remove,))
                    st.success(f"Removed {vip_to_remove} from VIP List.")
                    st.rerun()
            with vip_col2:
                if st.button("Block (Move to Blacklist)", key="demote_vip_btn"):
                    conn = get_db_connection()
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT name FROM vip WHERE phone_number = %s", (vip_to_remove,))
                            v_name = cur.fetchone()
                    finally:
                        conn.close()
                    reason = f"Demoted from VIP: {v_name[0] if v_name else 'Unnamed'}"
                    db_execute("DELETE FROM vip WHERE phone_number = %s", (vip_to_remove,))
                    db_execute("INSERT INTO blacklist (phone_number, reason) VALUES (%s, %s) ON CONFLICT (phone_number) DO NOTHING", (vip_to_remove, reason))
                    st.success(f"Demoted {vip_to_remove} to Blacklist.")
                    st.rerun()
        else:
            st.write("No custom VIPs added yet.")
    except Exception as e:
        st.error(f"Could not load VIP list: {e}")

# --- TAB 4: BLACKLIST ---
with tab_blacklist:
    st.header(f"🚫 {COMPANY_NAME} Blacklisted Spammers")
    st.write("Numbers on this list are blocked automatically.")
    
    st.subheader("Add Spammer Manually")
    bl_manual_col1, bl_manual_col2 = st.columns(2)
    with bl_manual_col1:
        new_block_reason = st.text_input("Reason for Block:", key="block_reason_input")
    with bl_manual_col2:
        new_block_number = st.text_input("Phone Number (Format: +1256...):", key="block_num_input")
        
    if st.button("Add to Blacklist", key="add_blacklist_manual"):
        if new_block_number.strip():
            try:
                db_execute("DELETE FROM vip WHERE phone_number = %s", (new_block_number.strip(),))
                db_execute("INSERT INTO blacklist (phone_number, reason) VALUES (%s, %s) ON CONFLICT (phone_number) DO NOTHING", 
                             (new_block_number.strip(), new_block_reason.strip() or "Manual Block"))
                st.success(f"Blocked {new_block_number.strip()}!")
                st.rerun()
            except Exception as e:
                st.error(f"Error blocking number: {e}")
        else:
            st.error("Phone number is required.")
            
    st.subheader("Currently Blacklisted Numbers")
    try:
        blacklist_data = fetch_dataframe("SELECT phone_number, blocked_at, reason FROM blacklist ORDER BY blocked_at DESC")
        
        if not blacklist_data.empty:
            event_bl = st.dataframe(
                blacklist_data,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="blacklist_table"
            )
            
            selected_bl_rows = event_bl.selection.rows
            selected_bl_phone = None
            if selected_bl_rows:
                selected_bl_phone = blacklist_data.iloc[selected_bl_rows[0]]["phone_number"]
                
            phone_to_remove = st.selectbox("Select a number to manage:", blacklist_data["phone_number"],
                                           index=blacklist_data["phone_number"].tolist().index(selected_bl_phone) if selected_bl_phone in blacklist_data["phone_number"].tolist() else 0)
            
            bl_col1, bl_col2 = st.columns(2)
            with bl_col1:
                if st.button("Forgive Caller", key="unban_bl_btn"):
                    db_execute("DELETE FROM blacklist WHERE phone_number = %s", (phone_to_remove,))
                    st.success(f"Purged {phone_to_remove} from the blacklist.")
                    st.rerun()
            with bl_col2:
                promote_name = st.text_input("Name to Promote to VIP:", value="Promoted Spammer", key="promote_name_input")
                promote_greeting = st.text_input("Custom Greeting (Optional):", key="promote_greeting_input")
                if st.button("Forgive & Move to VIP", key="promote_bl_btn"):
                    db_execute("DELETE FROM blacklist WHERE phone_number = %s", (phone_to_remove,))
                    db_execute("INSERT INTO vip (phone_number, name, custom_greeting) VALUES (%s, %s, %s) ON CONFLICT (phone_number) DO UPDATE SET name = EXCLUDED.name, custom_greeting = EXCLUDED.custom_greeting", (phone_to_remove, promote_name, promote_greeting.strip() or None))
                    st.success(f"Promoted {phone_to_remove} to VIP List as '{promote_name}'.")
                    st.rerun()
        else:
            st.write("No spammers currently blocked.")
    except Exception as e:
        st.error(f"Could not load database: {e}")

# Custom Branding
st.sidebar.markdown("---")
st.sidebar.markdown("<div style='text-align: center;'>🚀 Engineered & Automated by <b>Henegar Services</b></div>", unsafe_allow_html=True)
st.sidebar.markdown("![H(AI²)](https://raw.githubusercontent.com/jhp7786-art/jhp7786-art/main/collab-logo.svg)")

