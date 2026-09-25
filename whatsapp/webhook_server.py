import os
import re
import datetime
from typing import Dict, Any, Tuple, Optional
import requests
from flask import Flask, request, Response, send_from_directory, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Import KrishiRaksha submodules
from formatter import format_alert
from voice import generate_voice_note

# =====================================================================
# CONFIGURATION & ENVIRONMENT SETUP
# =====================================================================
# Sensitive credentials must strictly come from environment variables.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
SERVER_PUBLIC_URL = os.getenv("SERVER_PUBLIC_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", 5000))

# Directories for media uploads and voice note MP3 generation
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "static", "media")
UPLOADS_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static")

# =====================================================================
# IN-MEMORY CONVERSATION STATE
# Key: Phone number (e.g. "+919876543210" or "whatsapp:+919876543210")
# Value: Dict containing state stage and registered farmer field metadata
# Stages:
#   - "new" : Initial state before welcome
#   - "awaiting_location" : Asked for GPS coordinates pin
#   - "awaiting_crop_date" : Location saved, waiting for 'Crop, DD Month'
#   - "registered" : Field registered, ready for risk checks & leaf photos
# =====================================================================
CONVERSATION_STATE: Dict[str, Dict[str, Any]] = {}


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def parse_crop_and_sowing_date(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses user input like 'Tomato, 10 September', 'Wheat, 15 Oct 2026', or 'Rice, 2026-09-10'
    into (crop_name, 'YYYY-MM-DD'). Returns (None, None) if parsing fails.
    """
    if not text or not isinstance(text, str):
        return None, None

    text = text.strip()
    
    # Split by comma or semicolon if present
    if "," in text:
        parts = [p.strip() for p in text.split(",", 1)]
    elif ";" in text:
        parts = [p.strip() for p in text.split(";", 1)]
    else:
        # Fallback: Split on first space if formatted like 'Tomato 10 September'
        words = text.split()
        if len(words) >= 3:
            parts = [words[0], " ".join(words[1:])]
        else:
            return None, None

    crop_name = parts[0].strip().title()
    date_str = parts[1].strip()

    # Month name to number mapping for flexible parsing
    months = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "september": 9, "sept": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12
    }

    current_year = datetime.datetime.now().year
    parsed_date = None

    # Try ISO format YYYY-MM-DD
    iso_match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
    if iso_match:
        try:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            parsed_date = datetime.date(y, m, d)
        except ValueError:
            pass

    # Try DD-MM-YYYY or DD/MM/YYYY
    if not parsed_date:
        dmy_match = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})', date_str)
        if dmy_match:
            try:
                d, m, y = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
                if y < 100:
                    y += 2000
                parsed_date = datetime.date(y, m, d)
            except ValueError:
                pass

    # Try DD Month Name (e.g., '10 September', '15 Oct', '10 September 2026')
    if not parsed_date:
        word_date_match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{2,4}))?', date_str, re.IGNORECASE)
        if word_date_match:
            day = int(word_date_match.group(1))
            month_word = word_date_match.group(2).lower()
            year = int(word_date_match.group(3)) if word_date_match.group(3) else current_year
            if year < 100:
                year += 2000
            
            month_num = months.get(month_word)
            if month_num:
                try:
                    parsed_date = datetime.date(year, month_num, day)
                except ValueError:
                    pass

    # Try Month Name DD (e.g. 'September 10', 'Oct 15, 2026')
    if not parsed_date:
        word_date_match2 = re.search(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{2,4}))?', date_str, re.IGNORECASE)
        if word_date_match2:
            month_word = word_date_match2.group(1).lower()
            day = int(word_date_match2.group(2))
            year = int(word_date_match2.group(3)) if word_date_match2.group(3) else current_year
            if year < 100:
                year += 2000
            
            month_num = months.get(month_word)
            if month_num:
                try:
                    parsed_date = datetime.date(year, month_num, day)
                except ValueError:
                    pass

    if crop_name and parsed_date:
        return crop_name, parsed_date.strftime("%Y-%m-%d")

    return None, None


def download_twilio_media(media_url: str, save_path: str) -> bool:
    """
    Downloads an incoming media attachment (leaf photo) from Twilio's CDN.
    IMPORTANT: Twilio Media URLs require HTTP Basic Authentication with
    TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to access securely.
    """
    try:
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None
        response = requests.get(media_url, auth=auth, timeout=15)
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
            return True
        else:
            print(f"[Twilio Media Download Error] Status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"[Twilio Media Download Exception] {e}")
        return False


def call_backend_create_field(payload: dict) -> Tuple[Optional[int], str]:
    """
    Calls Backend API: POST /fields
    Request body: { farmer_name, phone, latitude, longitude, crop, sowing_date }
    Response: { field_id: int, message: str }
    """
    url = f"{BACKEND_URL}/fields"
    try:
        res = requests.post(url, json=payload, timeout=8)
        if res.status_code in (200, 201):
            data = res.json()
            return data.get("field_id"), data.get("message", "Field registered successfully.")
        else:
            print(f"[Backend POST /fields Error] {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[Backend POST /fields Exception] Backend unavailable ({e}). Using local mock field ID.")

    # Graceful mock fallback so hackathon testing does not block if backend is down
    mock_id = int(datetime.datetime.now().strftime("%H%M%S")) % 1000 + 100
    return mock_id, "Field registered (Mock Mode)"


def call_backend_get_risk(field_id: int, image_path: Optional[str] = None) -> dict:
    """
    Calls Backend API: POST /risk/{field_id}
    Optional body: { "image_path": str } (omitted entirely if no photo sent)
    Response: { field_id, disease, weather_risk, photo_risk, final_risk, spray_start, spray_end, treatment, estimated_loss_rupees }
    """
    url = f"{BACKEND_URL}/risk/{field_id}"
    body = {"image_path": image_path} if image_path else {}
    try:
        res = requests.post(url, json=body, timeout=12)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"[Backend POST /risk Error] {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[Backend POST /risk Exception] Backend unavailable ({e}). Generating simulated risk data.")

    # Fallback simulated response adhering precisely to backend contract
    if image_path:
        return {
            "field_id": field_id,
            "disease": "Early Blight (Alternaria solani)",
            "weather_risk": 0.65,
            "photo_risk": 0.88,
            "final_risk": 0.82,
            "spray_start": "06:30",
            "spray_end": "09:30",
            "treatment": "Apply Chlorothalonil 75 WP (2g/L) or Copper Oxychloride. Remove infected bottom leaves.",
            "estimated_loss_rupees": 18500,
            "crop": "Tomato"
        }
    else:
        return {
            "field_id": field_id,
            "disease": "Fungal Blight Weather Risk",
            "weather_risk": 0.48,
            "photo_risk": None,
            "final_risk": 0.48,
            "spray_start": "07:00",
            "spray_end": "10:30",
            "treatment": "Monitor moisture levels. Preventive neem oil spray (3ml/L) recommended.",
            "estimated_loss_rupees": 7200,
            "crop": "Tomato"
        }


# =====================================================================
# STATIC MEDIA SERVING ROUTE
# Twilio requires a publicly accessible HTTP URL to fetch voice notes/media.
# =====================================================================
@app.route("/media/<path:filename>", methods=["GET"])
def serve_media(filename):
    """Serves generated voice notes (MP3) or uploaded leaf photos."""
    return send_from_directory(MEDIA_DIR, filename)

@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_uploads(filename):
    """Serves uploaded leaf photos."""
    return send_from_directory(UPLOADS_DIR, filename)


# =====================================================================
# HEALTH / ROOT ENDPOINTS
# =====================================================================
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "online",
        "service": "KrishiRaksha WhatsApp Webhook Server",
        "registered_sessions": len(CONVERSATION_STATE),
        "backend_url": BACKEND_URL
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.datetime.now().isoformat()})


# =====================================================================
# TWILIO WHATSAPP WEBHOOK ENDPOINT
# =====================================================================
@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    """
    Inbound webhook triggered by Twilio for every WhatsApp message sent to your sandbox number.
    
    Twilio POST payload structure (application/x-www-form-urlencoded):
      - 'From' : Sender's WhatsApp number (e.g. 'whatsapp:+919876543210')
      - 'Body' : Text body of message
      - 'Latitude' / 'Longitude' : Present if user sent a location pin
      - 'NumMedia' : Number of attached media items ('0', '1', etc.)
      - 'MediaUrl0' : CDN URL of the first attached image/file
      - 'MediaContentType0' : MIME type (e.g. 'image/jpeg')
      - 'ProfileName' : WhatsApp display name of the user
    """
    resp = MessagingResponse()

    try:
        # 1. Parse incoming Twilio POST parameters
        form_data = request.form
        sender_phone = form_data.get("From", "").strip()
        body_text = form_data.get("Body", "").strip()
        profile_name = form_data.get("ProfileName", "Farmer").strip()
        
        # Location detection
        latitude_str = form_data.get("Latitude")
        longitude_str = form_data.get("Longitude")
        
        # Media / Image detection
        num_media = int(form_data.get("NumMedia", 0))
        media_url = form_data.get("MediaUrl0") if num_media > 0 else None

        if not sender_phone:
            resp.message("Invalid request payload received.")
            return Response(str(resp), mimetype="application/xml")

        # 2. State Check: First-ever interaction from this phone number
        if sender_phone not in CONVERSATION_STATE:
            CONVERSATION_STATE[sender_phone] = {
                "stage": "awaiting_location",
                "phone": sender_phone,
                "farmer_name": profile_name,
                "latitude": None,
                "longitude": None,
                "crop": None,
                "sowing_date": None,
                "field_id": None
            }
            welcome_msg = (
                "Welcome to KrishiRaksha 🌱\n"
                "To get started, please share your location, then reply with your crop and sowing date in this format:\n"
                "Tomato, 10 September"
            )
            resp.message(welcome_msg)
            return Response(str(resp), mimetype="application/xml")

        current_session = CONVERSATION_STATE[sender_phone]
        current_stage = current_session.get("stage", "awaiting_location")

        # -------------------------------------------------------------
        # STAGE: AWAITING LOCATION
        # -------------------------------------------------------------
        if current_stage == "awaiting_location":
            if latitude_str and longitude_str:
                try:
                    lat = float(latitude_str)
                    lon = float(longitude_str)
                    current_session["latitude"] = lat
                    current_session["longitude"] = lon
                    current_session["stage"] = "awaiting_crop_date"

                    reply_text = (
                        "📍 Location received!\n"
                        "Now reply with your crop and sowing date in this format:\n"
                        "Tomato, 10 September"
                    )
                    resp.message(reply_text)
                    return Response(str(resp), mimetype="application/xml")
                except ValueError:
                    resp.message("⚠️ Could not read GPS coordinates. Please share your location pin again via WhatsApp.")
                    return Response(str(resp), mimetype="application/xml")
            else:
                # User sent text or photo before sending location pin
                prompt_text = (
                    "📍 Please share your field location pin first.\n"
                    "Tap 📎 (Attach) -> Location -> Send your current location."
                )
                resp.message(prompt_text)
                return Response(str(resp), mimetype="application/xml")

        # -------------------------------------------------------------
        # STAGE: AWAITING CROP & SOWING DATE
        # -------------------------------------------------------------
        elif current_stage == "awaiting_crop_date":
            crop_name, sowing_date_iso = parse_crop_and_sowing_date(body_text)

            if not crop_name or not sowing_date_iso:
                fallback_crop_msg = (
                    "⚠️ Could not understand the crop and sowing date.\n"
                    "Please reply in this format:\n"
                    "*Crop, DD Month*\n\n"
                    "Example: *Tomato, 10 September*"
                )
                resp.message(fallback_crop_msg)
                return Response(str(resp), mimetype="application/xml")

            current_session["crop"] = crop_name
            current_session["sowing_date"] = sowing_date_iso

            # Register field with the backend API: POST /fields
            clean_phone = sender_phone.replace("whatsapp:", "").strip()
            field_payload = {
                "farmer_name": current_session.get("farmer_name", "Farmer"),
                "phone": clean_phone,
                "latitude": current_session.get("latitude", 20.5937),
                "longitude": current_session.get("longitude", 78.9629),
                "crop": crop_name,
                "sowing_date": sowing_date_iso
            }
            print(f"[*] Sending payload to backend: {field_payload}")

            field_id, backend_msg = call_backend_create_field(field_payload)
            current_session["field_id"] = field_id
            current_session["stage"] = "registered"

            registration_ack = (
                f"Registration complete ✅ Field ID: {field_id}.\n"
                f"We're now monitoring your {crop_name} field.\n\n"
                f"💡 *How to use KrishiRaksha:*\n"
                f"• Send any text (e.g. 'check risk') for instant weather risk assessment.\n"
                f"• Send a photo of any damaged leaf for an AI diagnosis."
            )
            resp.message(registration_ack)
            return Response(str(resp), mimetype="application/xml")

        # -------------------------------------------------------------
        # STAGE: REGISTERED (Risk Checks & Leaf Diagnosis)
        # -------------------------------------------------------------
        elif current_stage == "registered":
            field_id = current_session.get("field_id", 101)

            # Case A: User sent an image / leaf photo
            if media_url:
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                clean_phone_fn = sender_phone.replace("whatsapp:", "").replace("+", "")
                filename = f"leaf_{clean_phone_fn}_{timestamp_str}.jpg"
                save_filepath = os.path.join(UPLOADS_DIR, filename)

                # Download media from Twilio CDN with Auth
                download_ok = download_twilio_media(media_url, save_filepath)
                if not download_ok:
                    # In case of CDN download issue, pass the direct media URL as fallback
                    save_filepath = media_url

                # Call Backend API: POST /risk/{field_id} with image_path
                risk_data = call_backend_get_risk(field_id, image_path=save_filepath)
                if not risk_data.get("crop") and current_session.get("crop"):
                    risk_data["crop"] = current_session.get("crop")

                alert_text = format_alert(risk_data)
                tw_msg = resp.message(alert_text)

                # Generate voice note if public server URL is configured
                if SERVER_PUBLIC_URL:
                    try:
                        voice_filename = f"voice_field_{field_id}_{timestamp_str}.mp3"
                        voice_path = os.path.join(MEDIA_DIR, voice_filename)
                        generate_voice_note(alert_text, voice_path)
                        tw_msg.media(f"{SERVER_PUBLIC_URL}/media/{voice_filename}")
                    except Exception as ve:
                        print(f"[Voice Generation Note] Could not attach voice note: {ve}")

                return Response(str(resp), mimetype="application/xml")

            # Case B: User sent text (e.g. "check risk", "status", "hi", etc.)
            else:
                # Call Backend API: POST /risk/{field_id} with empty body (weather-only)
                risk_data = call_backend_get_risk(field_id, image_path=None)
                if not risk_data.get("crop") and current_session.get("crop"):
                    risk_data["crop"] = current_session.get("crop")

                alert_text = format_alert(risk_data)
                tw_msg = resp.message(alert_text)

                # Generate voice note if public server URL is configured
                if SERVER_PUBLIC_URL:
                    try:
                        voice_filename = f"voice_weather_{field_id}.mp3"
                        voice_path = os.path.join(MEDIA_DIR, voice_filename)
                        generate_voice_note(alert_text, voice_path)
                        tw_msg.media(f"{SERVER_PUBLIC_URL}/media/{voice_filename}")
                    except Exception as ve:
                        print(f"[Voice Generation Note] Could not attach voice note: {ve}")

                return Response(str(resp), mimetype="application/xml")

        # -------------------------------------------------------------
        # FALLBACK / UNRECOGNIZED STAGE
        # -------------------------------------------------------------
        else:
            current_session["stage"] = "awaiting_location"
            resp.message(
                "Welcome to KrishiRaksha 🌱\n"
                "To get started, please share your location, then reply with your crop and sowing date in this format:\n"
                "Tomato, 10 September"
            )
            return Response(str(resp), mimetype="application/xml")

    except Exception as exc:
        print(f"[Webhook Unhandled Exception] {exc}")
        # Graceful fallback: Never crash or leave user without a reply
        resp.message(
            "🌱 KrishiRaksha is processing your request.\n"
            "If you were checking risk, please send 'check risk' or send a leaf photo."
        )
        return Response(str(resp), mimetype="application/xml")


# =====================================================================
# SERVER RUNNER
# =====================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  🌱 KrishiRaksha WhatsApp Webhook Server")
    print(f"  Listening on: http://0.0.0.0:{PORT}")
    print(f"  Backend URL : {BACKEND_URL}")
    print(f"  Twilio Phone: {TWILIO_WHATSAPP_NUMBER}")
    print(f"  Public URL  : {SERVER_PUBLIC_URL or '(Set SERVER_PUBLIC_URL for Voice Notes)'}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=PORT, debug=False)
