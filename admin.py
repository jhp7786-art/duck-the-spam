import streamlit as st
import duckdb
import os
from dotenv import load_dotenv, set_key

# Load environment variables
load_dotenv()
DB_FILE = "duck_the_spam.db"
ENV_FILE = ".env"

# Initialize DB structure in Streamlit as well to prevent catalog exceptions
def ensure_db():
    conn = duckdb.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            phone_number VARCHAR PRIMARY KEY,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip (
            phone_number VARCHAR PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            name VARCHAR
        )
    """)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_call_log_id")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS call_logs (
            id INTEGER DEFAULT nextval('seq_call_log_id') PRIMARY KEY,
            phone_number VARCHAR,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            call_type VARCHAR,
            details VARCHAR
        )
    """)
    conn.close()

ensure_db()

st.set_page_config(page_title="Henegar Services - Telecom Control", page_icon="📞", layout="wide")

st.title("📞 Henegar Services Telecom Command Center")
st.markdown("---")

# ==========================================
# 1. MODE SELECTOR (THE LOOM SHOWCASE)
# ==========================================
st.header("🛡️ Active Spam Defense Protocol")

# Read current mode from .env, default to JOHN
current_mode = os.getenv("SPAM_PROTOCOL", "JOHN").upper()

modes = {
    "JOHN": {
        "title": "🎭 The 'John' (UNO Reverse)",
        "desc": "The ultimate trap. Stalls financial/loan spammers by pretending to be their long-lost friend 'John' in a panic about his own extended car warranty, then exits with a sarcastic 'wonk wonk wonk'."
    },
    "TODDLER": {
        "title": "👶 The Toddler",
        "desc": "Frustrates callers to the point of rage-quitting by trapping them in an infinite loop that constantly interrupts their pitch by asking 'Why?' every time they stop speaking."
    },
    "PARROT": {
        "title": "🦜 The Parrot",
        "desc": "Echos the spammer's exact transcribed words right back to them in a robotic voice loop, mimicking them until they hang up in frustration."
    },
    "HAMMER": {
        "title": "🔨 The Hammer",
        "desc": "A stern, no-nonsense warning informing the solicitor that their number has been logged and blacklisted, followed by an immediate disconnect."
    }
}

# Determine index for selectbox
mode_keys = list(modes.keys())
default_index = mode_keys.index(current_mode) if current_mode in mode_keys else 0

selected_key = st.selectbox(
    "Select Active Trap Mode:", 
    options=mode_keys, 
    format_func=lambda x: modes[x]["title"],
    index=default_index
)

# Display description for Loom walkthrough
st.info(modes[selected_key]["desc"])

# Save button to update .env on the fly
if st.button("Apply Selected Protocol"):
    set_key(ENV_FILE, "SPAM_PROTOCOL", selected_key)
    st.success(f"Successfully switched to {modes[selected_key]['title']}! (FastAPI will reload automatically)")

st.markdown("---")

# ==========================================
# 2. CALL LOGS & LIST MANAGEMENT (TABS)
# ==========================================
tab_logs, tab_vip, tab_blacklist = st.tabs([
    "📊 Call Log Command Center",
    "🔑 VIP List (Bypass)",
    "🚫 Blacklisted Spammers"
])

with tab_logs:
    st.header("📊 Call Log Command Center")
    st.write("Click any row in the log below to view caller history and take quick actions.")
    
    try:
        conn = duckdb.connect(DB_FILE)
        call_logs = conn.execute(
            "SELECT id, phone_number, timestamp, call_type, details FROM call_logs ORDER BY timestamp DESC LIMIT 50"
        ).fetch_df()
        conn.close()
        
        if not call_logs.empty:
            # Interactive Dataframe with Row Selection
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
                
                # Check status
                conn = duckdb.connect(DB_FILE)
                is_vip = conn.execute("SELECT name FROM vip WHERE phone_number = ?", [selected_phone]).fetchone()
                is_blocked = conn.execute("SELECT reason FROM blacklist WHERE phone_number = ?", [selected_phone]).fetchone()
                conn.close()
                
                col_act1, col_act2 = st.columns(2)
                
                with col_act1:
                    if is_vip:
                        st.info(f"🔑 This number is in your VIP list (as '{is_vip[0]}').")
                        if st.button("Remove from VIP List", key="remove_vip_from_logs"):
                            conn = duckdb.connect(DB_FILE)
                            conn.execute("DELETE FROM vip WHERE phone_number = ?", [selected_phone])
                            conn.close()
                            st.success(f"Removed {selected_phone} from VIP list.")
                            st.rerun()
                    else:
                        st.write("**Add to VIP List**")
                        vip_name_input = st.text_input("Contact Name (e.g. John Doe):", value="Unnamed VIP", key="vip_name_from_logs")
                        if st.button("Add to VIP List", key="add_vip_from_logs"):
                            conn = duckdb.connect(DB_FILE)
                            # Remove from blacklist first if it exists there
                            conn.execute("DELETE FROM blacklist WHERE phone_number = ?", [selected_phone])
                            conn.execute("INSERT OR IGNORE INTO vip (phone_number, name) VALUES (?, ?)", [selected_phone, vip_name_input])
                            conn.close()
                            st.success(f"Added {selected_phone} to VIP List!")
                            st.rerun()
                            
                with col_act2:
                    if is_blocked:
                        st.info(f"🚫 This number is blocked (Reason: '{is_blocked[0]}').")
                        if st.button("Forgive Caller (Unban)", key="unban_from_logs"):
                            conn = duckdb.connect(DB_FILE)
                            conn.execute("DELETE FROM blacklist WHERE phone_number = ?", [selected_phone])
                            conn.close()
                            st.success(f"Removed {selected_phone} from blacklist.")
                            st.rerun()
                    else:
                        st.write("**Block Caller**")
                        block_reason_input = st.text_input("Reason for block (e.g. Loan Spam):", value="Manual Block", key="block_reason_from_logs")
                        if st.button("Block Number", key="block_from_logs"):
                            conn = duckdb.connect(DB_FILE)
                            # Remove from VIP first if it exists there
                            conn.execute("DELETE FROM vip WHERE phone_number = ?", [selected_phone])
                            conn.execute("INSERT OR IGNORE INTO blacklist (phone_number, reason) VALUES (?, ?)", [selected_phone, block_reason_input])
                            conn.close()
                            st.success(f"Blocked {selected_phone}!")
                            st.rerun()
        else:
            st.info("No calls logged yet. Incoming calls will appear here in real time.")
    except Exception as e:
        st.error(f"Could not load call logs: {e}")

with tab_vip:
    st.header("🔑 VIP List (Ladder Bypass)")
    st.write("Numbers on this list bypass all IVR menus and screening, routing straight to your friendly voicemail.")
    
    # VIP Form to add new number manually
    st.subheader("Add Contact Manually")
    manual_col1, manual_col2 = st.columns(2)
    with manual_col1:
        new_vip_name = st.text_input("Contact Name (e.g. John Doe):", key="vip_name_input")
    with manual_col2:
        new_vip_number = st.text_input("VIP Phone Number (Format: +1256...):", key="vip_num_input")
        
    if st.button("Add to VIP List", key="add_vip_manual"):
        if new_vip_number.strip():
            conn = duckdb.connect(DB_FILE)
            try:
                # Remove from blacklist first if there
                conn.execute("DELETE FROM blacklist WHERE phone_number = ?", [new_vip_number.strip()])
                conn.execute("INSERT OR IGNORE INTO vip (phone_number, name) VALUES (?, ?)", 
                             [new_vip_number.strip(), new_vip_name.strip() or "Unnamed VIP"])
                st.success(f"Added {new_vip_number.strip()} to the VIP List!")
                st.rerun()
            except Exception as e:
                st.error(f"Error adding VIP: {e}")
            finally:
                conn.close()
        else:
            st.error("Phone number is required.")
            
    st.subheader("Current VIP Contacts")
    # Load and show current VIP list
    try:
        conn = duckdb.connect(DB_FILE)
        vip_data = conn.execute("SELECT phone_number, name, added_at FROM vip ORDER BY added_at DESC").fetch_df()
        conn.close()
        
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
                    conn = duckdb.connect(DB_FILE)
                    conn.execute("DELETE FROM vip WHERE phone_number = ?", [vip_to_remove])
                    conn.close()
                    st.success(f"Removed {vip_to_remove} from the VIP List.")
                    st.rerun()
            with vip_col2:
                if st.button("Block (Move to Blacklist)", key="demote_vip_btn"):
                    conn = duckdb.connect(DB_FILE)
                    # Get VIP name to use as reason
                    v_name = conn.execute("SELECT name FROM vip WHERE phone_number = ?", [vip_to_remove]).fetchone()
                    reason = f"Demoted from VIP: {v_name[0] if v_name else 'Unnamed'}"
                    conn.execute("DELETE FROM vip WHERE phone_number = ?", [vip_to_remove])
                    conn.execute("INSERT OR IGNORE INTO blacklist (phone_number, reason) VALUES (?, ?)", [vip_to_remove, reason])
                    conn.close()
                    st.success(f"Demoted {vip_to_remove} to Blacklist.")
                    st.rerun()
        else:
            st.write("No custom VIPs added yet.")
    except Exception as e:
        st.error(f"Could not load VIP list: {e}")

with tab_blacklist:
    st.header("🚫 Blacklisted Spammers")
    st.write("Numbers on this list are blocked automatically without routing to a menu.")
    
    # Form to blacklist a number manually
    st.subheader("Add Spammer Manually")
    bl_manual_col1, bl_manual_col2 = st.columns(2)
    with bl_manual_col1:
        new_block_reason = st.text_input("Reason for Block:", key="block_reason_input")
    with bl_manual_col2:
        new_block_number = st.text_input("Phone Number (Format: +1256...):", key="block_num_input")
        
    if st.button("Add to Blacklist", key="add_blacklist_manual"):
        if new_block_number.strip():
            conn = duckdb.connect(DB_FILE)
            try:
                # Remove from VIP first if there
                conn.execute("DELETE FROM vip WHERE phone_number = ?", [new_block_number.strip()])
                conn.execute("INSERT OR IGNORE INTO blacklist (phone_number, reason) VALUES (?, ?)", 
                             [new_block_number.strip(), new_block_reason.strip() or "Manual Block"])
                st.success(f"Blocked {new_block_number.strip()}!")
                st.rerun()
            except Exception as e:
                st.error(f"Error blocking number: {e}")
            finally:
                conn.close()
        else:
            st.error("Phone number is required.")
            
    st.subheader("Currently Blacklisted Numbers")
    try:
        conn = duckdb.connect(DB_FILE)
        blacklist_data = conn.execute("SELECT phone_number, blocked_at, reason FROM blacklist ORDER BY blocked_at DESC").fetch_df()
        conn.close()
        
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
                    conn = duckdb.connect(DB_FILE)
                    conn.execute("DELETE FROM blacklist WHERE phone_number = ?", [phone_to_remove])
                    conn.close()
                    st.success(f"Purged {phone_to_remove} from the blacklist.")
                    st.rerun()
            with bl_col2:
                # Ask for name to promote to VIP
                promote_name = st.text_input("Name to Promote to VIP:", value="Promoted Spammer", key="promote_name_input")
                if st.button("Forgive & Move to VIP", key="promote_bl_btn"):
                    conn = duckdb.connect(DB_FILE)
                    conn.execute("DELETE FROM blacklist WHERE phone_number = ?", [phone_to_remove])
                    conn.execute("INSERT OR IGNORE INTO vip (phone_number, name) VALUES (?, ?)", [phone_to_remove, promote_name])
                    conn.close()
                    st.success(f"Promoted {phone_to_remove} to VIP List as '{promote_name}'.")
                    st.rerun()
        else:
            st.write("No spammers currently blocked. The wall stands tall!")
    except Exception as e:
        st.error(f"Could not load database: {e}")

st.markdown("---")

# ==========================================
# 3. NOTIFICATION PREFERENCES (DEMO / SALES FEATURE)
# ==========================================
st.header("📲 Lead Routing & Notifications")
st.write("Configure how you want to be notified when a legitimate client leaves a message or passes the screener.")

col3, col4 = st.columns(2)

with col3:
    notification_method = st.selectbox(
        "Select Notification Delivery Method:",
        options=[
            "Direct SMS Alert (Carrier Native - Free)", 
            "Slack / Discord Push Notification", 
            "Voicemail-to-Email Drop", 
            "Pushover (High Priority Alert App)"
        ]
    )
    
    # Fake a save button for the demo
    if st.button("Save Routing Preferences"):
        st.info(f"Demo Mode: In a live environment, leads will now be routed via {notification_method.split(' (')[0]}.")

with col4:
    st.info("**Sales Demo Note:**")
    if "Direct SMS" in notification_method:
        st.write("Uses the carrier's native Email-to-SMS gateway to bypass Twilio's A2P 10DLC restrictions. Client gets a standard text message instantly for $0.00.")
    elif "Slack" in notification_method:
        st.write("Routes the transcript, phone number, and audio link directly to a private Slack or Discord channel. Perfect for keeping personal texts and business separate.")
    elif "Voicemail-to-Email" in notification_method:
        st.write("Packages the audio file (.mp3) and a written transcript into an email. Ideal for contractors who do their quotes at a desk at the end of the day.")
    else:
        st.write("Triggers a dedicated push notification app for high-priority alerts that break through 'Do Not Disturb' settings.")
