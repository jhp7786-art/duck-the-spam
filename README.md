# 🦆 Duck the Spam

A multi-mode, automated telecom command center and call-screening PBX built with **FastAPI**, **Twilio Programmable Voice**, and **DuckDB**. 

Features an interactive **Streamlit Admin Panel** to manage your business routing, monitor blocked spammers, and cycle active defense protocols.

---

## 🛡️ Active Spam Defense Protocols

When a telemarketer or robocaller ignores your business menu, the bouncer takes over. You can toggle between these modes instantly from the dashboard:

### 🎭 1. The "John" (UNO Reverse)
* **How it works:** The ultimate trap. Stalls financial/loan spammers by pretending to be their long-lost friend 'John' in a panic about his own extended car warranty, then exits with a sarcastic, automated "wonk wonk wonk."

### 👶 2. The Toddler
* **How it works:** Frustrates callers to the point of rage-quitting by trapping them in an infinite loop that constantly interrupts their pitch by asking "Why?" every time they stop speaking.

### 🦜 3. The Parrot
* **How it works:** Echoes the spammer's exact transcribed words right back to them in a robotic voice loop, mimicking them until they hang up in frustration.

### 🔨 4. The Hammer
* **How it works:** A stern, no-nonsense warning informing the solicitor that their number has been logged and blacklisted, followed by an immediate disconnect.

---

## 🛠️ Tech Stack & Features
- **FastAPI Backend:** Lightweight, asynchronous web routing for Twilio Webhooks.
- **Twilio Voice API:** High-fidelity speech recognition and Neural Text-to-Speech (TTS).
- **PostgreSQL (Neon):** Centralized cloud database storing blocker lists, VIP whitelist, and call logs.
- **Streamlit Dashboard:** Command center UI for configuring settings, managing the VIP/blacklist, and checking call records on the fly.
- **VIP Bypass:** Whitelists family and friends to skip automated menus and route straight to custom voicemail boxes.

---

## 💼 Contractor & Small Business Solutions

This architecture was specifically designed for solo contractors (painters, roofers, handymen) who spend their days on ladders or under sinks. It acts as a digital PBX, screening out the noise so you only answer real leads. 

We offer this as a fully managed telecom service, available in two tiers:

### 🥉 Tier 1: The "Off-the-Ladder" Package
Perfect for contractors who just want their phones to stop ringing with spam.
* **Local Business Number:** A dedicated local line for your business cards and truck.
* **The Automated Spam Trap:** "Duck the Spam" actively quarantines robocalls and warranty pitches.
* **Family & Supplier Bypass:** Important numbers (wife, kids, key suppliers) skip the screener entirely and ring your phone directly.

### 🥇 Tier 2: The "Lead Catcher" Package
A complete front-office replacement for busy solo operators.
* *Everything in Tier 1, plus:*
* **Professional IVR Front Desk:** A custom greeting routing clients (e.g., "Press 1 for Estimates, Press 2 for Billing").
* **Instant Native SMS Alerts:** When a real client clears the menu and leaves a lead, the system uses carrier gateways to instantly text your personal phone with their number and what they called about—bypassing telecom restrictions.
* **Voicemail-to-Email Drops:** End of the day? All your leads and their audio files are perfectly organized in your email inbox ready for quoting.

---

## 🌐 Distributed Cloud Architecture

"Duck the Spam" is structured as a distributed microservice setup:

* **Centralized Ledger (Neon PostgreSQL):** The system uses a hosted Neon PostgreSQL database as its single source of truth for whitelisting, blacklisting, and call tracking.
* **Independent Render Services:**
  * **FastAPI Backend (Bouncer):** Runs as a Render Web Service to receive real-time webhook calls from Twilio, check caller privileges, run defense traps, and log actions.
  * **Streamlit Admin Dashboard:** Runs as a separate Render Web Service to allow real-time control, blacklist management, and quick whitelisting.
* **Dynamic Real-Time Synced State:** Whitelisting a number or blocking a caller on the dashboard takes effect instantly on the call bouncer, without any database replication lag or file locking issues.
