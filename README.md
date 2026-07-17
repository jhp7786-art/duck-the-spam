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
- **DuckDB:** Embedded database to store spammer numbers and log call interactions.
- **Streamlit Dashboard:** Local UI for configuring settings, purging the blacklist, and checking call records on the fly.
- **VIP Bypass:** Whitelists family and friends to skip automated menus and route straight to custom voicemail boxes.
