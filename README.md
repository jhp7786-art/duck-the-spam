
---

# Duck the Spam 🦆📱

An automated digital bouncer for your phone, because absolutely no one has the patience to hear about another "pre-approved business advance."

## What is this?

**Duck the Spam** is a lightweight, zero-tolerance call-screening API built with FastAPI, Twilio, and DuckDB. It acts as a frontline defense against relentless telemarketers, loan sharks, and spam callers.

When an unknown number calls, this application answers, politely interrogates them using speech-to-text, and listens for specific trigger words (like "loan", "funding", or "capital"). If triggered, it plays a legally unambiguous "lose my number" message, hangs up immediately, and throws their Caller ID into a local DuckDB black hole so they can never get through again.

Why was this built? Because nothing ruins the flow of a good vibe coding session—or being elbow-deep in a car door trying to fix a broken latch—quite like a ringing phone from an auto-dialer.

## Features

* **The Interrogator:** Prompts unknown callers to state their business using Twilio's `<Gather>` verb.
* **Zero-Tolerance Keyword Sniffing:** Transcribes the response and checks it against a customizable array of spam triggers.
* **The "Drop the Hammer" Protocol:** Spammers are met with an uncompromising recorded warning followed by a ruthless, immediate `<Hangup>`. No small talk.
* **DuckDB Blacklist:** Fast, local, serverless database logging. If a blacklisted number tries to call back, the app drops the call at the carrier level before it even rings.
* **Legitimate Caller Fallback:** Cleared callers are politely directed to a voicemail system (perfect for Conditional Call Forwarding setups).

## The Tech Stack

* **Backend:** Python / FastAPI
* **Telephony & Speech-to-Text:** Twilio API
* **Storage:** DuckDB (because it's blazing fast and stays out of the way)

## Installation & Setup

**1. Clone the repo and install dependencies**

```bash
git clone https://github.com/jhp7786-art/duck-the-spam.git
cd duck-the-spam
pip install -r requirements.txt

```

**2. Configure your environment**
Create a `.env` file in the root directory. **Do not commit this file to GitHub.**

```text
MY_REAL_PHONE_NUMBER=+1234567890

```

*(Note: If you are using the voicemail/call-forwarding method, this variable isn't strictly necessary, but it's good practice for when you eventually want to build out SMS notifications or call bridging).*

**3. Run the application locally**

```bash
uvicorn main:app --reload --port 8000

```

**4. Expose to the internet & link to Twilio**
Use a tool like `ngrok` to expose port 8000. Take that public URL, append `/incoming-call`, and set it as the webhook for your Twilio phone number under "A CALL COMES IN".

## Managing the Blacklist

Want to see whose day you ruined? You can query the DuckDB file (`duck_the_spam.db`) directly using Python:

```python
import duckdb
conn = duckdb.connect("duck_the_spam.db")
print(conn.execute("SELECT * FROM blacklist").fetchdf())

```

## Contributing

Feel free to fork this and add your own favorite spam-busting features. Just remember to keep your personal API keys out of your commits.

## License

MIT License. Free to use, modify, and deploy. Spammers, however, have no rights here.