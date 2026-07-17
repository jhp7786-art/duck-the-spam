import streamlit as st
import duckdb
import os
from dotenv import load_dotenv, set_key

# Load environment variables
load_dotenv()
DB_FILE = "duck_the_spam.db"
ENV_FILE = ".env"

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
# 2. BLACKLIST & VIP MANAGEMENT
# ==========================================
col1, col2 = st.columns(2)

with col1:
    st.header("🚫 Blacklisted Spammers")
    try:
        conn = duckdb.connect(DB_FILE)
        blacklist_data = conn.execute("SELECT phone_number, blocked_at, reason FROM blacklist ORDER BY blocked_at DESC").fetch_df()
        conn.close()
        
        if not blacklist_data.empty:
            st.dataframe(blacklist_data, use_container_width=True)
            
            # Simple unban feature
            phone_to_remove = st.selectbox("Select a number to unban:", blacklist_data["phone_number"])
            if st.button("Forgive Caller"):
                conn = duckdb.connect(DB_FILE)
                conn.execute("DELETE FROM blacklist WHERE phone_number = ?", [phone_to_remove])
                conn.close()
                st.success(f"Purged {phone_to_remove} from the blacklist.")
                st.rerun()
        else:
            st.write("No spammers currently blocked. The wall stands tall!")
    except Exception as e:
        st.error(f"Could not load database: {e}")

with col2:
    st.header("🔑 VIP List (Ladder Bypass)")
    st.write("Numbers on this list bypass all IVR menus and screening, routing straight to a friendly voicemail.")
    
    # In a production app, you can save this to DuckDB or .env. For now, let's display what is in VIP_NUMBERS
    # Show input to add a VIP
    new_vip = st.text_input("Add VIP Phone Number (Format: +1256...):")
    if st.button("Add to VIP List"):
        st.warning("To finalize VIP lists in Phase 1, drop them into your VIP_NUMBERS list in main.py!")
