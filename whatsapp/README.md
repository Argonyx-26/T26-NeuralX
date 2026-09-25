# KrishiRaksha — WhatsApp Farmer Interface & Alert Service (Person 4 Module)

This service manages the end-to-end farmer communication lifecycle over WhatsApp:
1. **Interactive Onboarding State Machine** (Location pin capture, Crop & Sowing Date parsing, Field Registration).
2. **AI & Weather Risk Advisories** (Instant leaf disease diagnosis from photos, weather risk updates).
3. **Multimodal Accessibility** (Concise farmer-readable text alerts + gTTS voice notes).
4. **Surveillance Push Alerts** (Proactive outbound alerts via Twilio REST API).

---

## 📁 Architecture & File Breakdown

- `webhook_server.py`: Flask service exposing `/webhook` for Twilio WhatsApp inbound messages, `/media/<file>` for static MP3 audio serving, and `/health`.
- `formatter.py`: Formats the `/risk/{field_id}` backend JSON payload into clean WhatsApp alerts with urgency emojis (`🚨`, `⚠️`, `✅`), spray windows, and estimated losses under 500 characters.
- `voice.py`: Generates MP3 voice notes using `gTTS` and sends media notes via Twilio REST API.
- `proactive.py`: Independent dispatcher for surveillance alerts (callable by background workers or cron).
- `requirements.txt`: Python package dependencies.

---

## ⚙️ Required Environment Variables

Create a `.env` file inside `whatsapp/` (or set in your environment):

```env
# Twilio Sandbox Credentials (from https://console.twilio.com)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Backend REST API Base URL (Person 1/2/3 service)
BACKEND_URL=http://localhost:8000

# Public URL of this webhook server (e.g. your ngrok https URL)
# Needed so Twilio can download generated voice notes from /media/...
SERVER_PUBLIC_URL=https://your-subdomain.ngrok-free.app

# Server Port
PORT=5000
```

---

## 🚀 Quickstart & Local Setup

### 1. Install Dependencies
```bash
cd whatsapp
pip install -r requirements.txt
```

### 2. Start Webhook Server
```bash
python webhook_server.py
```
*The server will start on `http://localhost:5000`.*

### 3. Expose Server to Internet with Ngrok
In a separate terminal:
```bash
ngrok http 5000
```
Copy your forwarding HTTPS URL (e.g. `https://abcd-1234.ngrok-free.app`) and set it in your `.env` as `SERVER_PUBLIC_URL`.

---

## 📱 Twilio WhatsApp Sandbox Setup & Testing

### Step 1: Configure Twilio Sandbox Webhook
1. Go to **Twilio Console** → **Messaging** → **Try it out** → **Send a WhatsApp message**.
2. Under **Sandbox Settings**:
   - **WHEN A MESSAGE COMES IN**: `https://abcd-1234.ngrok-free.app/webhook`
   - **HTTP METHOD**: `POST`
3. Click **Save**.

### Step 2: Test with a Real Phone

1. **Join Twilio Sandbox**:
   Send the sandbox join code (e.g., `join silver-fox`) from your WhatsApp phone to the Twilio number (+1 415 523 8886).

2. **Step 1 — Welcome & Prompt**:
   Send any message (e.g. "Hi").
   - **Bot Response:**
     ```
     Welcome to KrishiRaksha 🌱
     To get started, please share your location, then reply with your crop and sowing date in this format:
     Tomato, 10 September
     ```

3. **Step 2 — Location Sharing**:
   In WhatsApp, tap **📎 (Attachment)** → **Location** → **Send your current location**.
   - **Bot Response:**
     ```
     📍 Location received!
     Now reply with your crop and sowing date in this format:
     Tomato, 10 September
     ```

4. **Step 3 — Registration**:
   Reply with: `Tomato, 10 September` (or `Wheat, 15 Oct`).
   - The bot calls `POST /fields` and replies:
     ```
     Registration complete ✅ Field ID: 101.
     We're now monitoring your Tomato field.
     ```

5. **Step 4 — Leaf Photo Diagnosis**:
   Send a photo of a diseased tomato leaf.
   - The bot downloads the image securely from Twilio, calls `POST /risk/101`, and returns:
     ```
     🚨 KrishiRaksha Advisory - HIGH RISK
     🌾 Crop: Tomato
     🎯 Condition: Early Blight (Alternaria solani)
     📊 Risk Level: 82%
     ⏱ Spray Window: 06:30 - 09:30
     💊 Treatment: Apply Chlorothalonil 75 WP (2g/L).
     💰 Est. Potential Loss: ₹18,500
     ```
     *(Plus an attached audio voice note if `SERVER_PUBLIC_URL` is set!)*

6. **Step 5 — Weather-Only Risk Check**:
   Send plain text like `check risk` or `status`.
   - The bot calls `POST /risk/101` (omitting `image_path`) and returns weather advisory with disclaimer:
     ```
     ℹ️ Weather-only assessment. Send a leaf photo for a more precise reading.
     ```

---

## 🔔 Testing Proactive Surveillance Alerts

To simulate an automated outbreak warning pushed to a farmer:

```bash
python proactive.py 101 +919876543210
```

---

## 💡 Live Q&A Defense Notes

1. **Twilio Media Download Auth**: Twilio media CDN URLs require HTTP Basic Authentication using `(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)`. Simple unauthenticated `requests.get()` calls will return 401 Unauthorized.
2. **Resilient Fallbacks**: If the backend is temporarily offline during testing, the bot gracefully responds with standard contract-compliant simulated data instead of crashing or showing raw tracebacks.
3. **Date Parsing**: The custom date parser in `webhook_server.py` handles diverse formats (e.g. `DD Month`, `Month DD`, `YYYY-MM-DD`, `DD/MM/YYYY`) without strict rigid constraints.
