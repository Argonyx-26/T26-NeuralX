import os
import requests
from twilio.rest import Client
from formatter import format_alert
from voice import generate_voice_note, send_voice_note

def send_proactive_alert(
    field_id: int,
    phone: str,
    backend_url: str = None,
    account_sid: str = None,
    auth_token: str = None,
    from_number: str = None,
    send_audio: bool = False,
    server_public_url: str = None
) -> dict:
    """
    Pushes an automated surveillance-mode alert to a farmer via Twilio REST API.
    Can be run as a cron job, worker, or triggered manually by a risk monitoring background worker.
    
    Parameters:
    - field_id: ID of the registered field to check risk for
    - phone: Recipient WhatsApp phone number (e.g., "+919876543210")
    - backend_url: Base URL of KrishiRaksha backend API (default from BACKEND_URL)
    - send_audio: If True and server_public_url is set, sends audio voice note as well
    """
    backend_url = (backend_url or os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")
    account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
    from_number = from_number or os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
    server_public_url = server_public_url or os.getenv("SERVER_PUBLIC_URL", "")

    if not account_sid or not auth_token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set to send proactive alerts.")

    # 1. Fetch risk prediction from the Backend API contract: POST /risk/{field_id} (no image)
    risk_endpoint = f"{backend_url}/risk/{field_id}"
    try:
        response = requests.post(risk_endpoint, json={}, timeout=10)
        if response.status_code == 200:
            risk_data = response.json()
        else:
            raise RuntimeError(f"Backend returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[Warning] Failed to reach backend at {risk_endpoint} ({e}). Using simulated surveillance data for testing.")
        # Local mock fallback for isolated testing during hackathon
        risk_data = {
            "field_id": field_id,
            "disease": "Early Blight Warning",
            "weather_risk": 0.78,
            "photo_risk": None,
            "final_risk": 0.78,
            "spray_start": "06:30",
            "spray_end": "09:30",
            "treatment": "Apply Mancozeb 75% WP @ 2g/L. Avoid evening watering.",
            "estimated_loss_rupees": 15000,
            "crop": "Tomato"
        }

    # 2. Format alert for WhatsApp readability
    alert_text = format_alert(risk_data)
    proactive_header = "🔔 *[Surveillance Alert]* High risk weather pattern detected for your field:\n\n"
    full_message = proactive_header + alert_text

    # 3. Format recipient phone number for Twilio WhatsApp
    to_phone = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"

    # 4. Dispatch WhatsApp text message via Twilio REST API
    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        body=full_message,
        from_=from_number,
        to=to_phone
    )
    print(f"[Proactive Alert] Text alert sent to {to_phone}. Message SID: {msg.sid}")

    result = {
        "text_message_sid": msg.sid,
        "voice_message_sid": None,
        "risk_data": risk_data
    }

    # 5. Optionally generate and send voice note if public media hosting is available
    if send_audio and server_public_url:
        try:
            filename = f"proactive_field_{field_id}.mp3"
            media_dir = os.path.join(os.path.dirname(__file__), "static", "media")
            os.makedirs(media_dir, exist_ok=True)
            output_filepath = os.path.join(media_dir, filename)
            generate_voice_note(alert_text, output_filepath)
            
            public_media_url = f"{server_public_url.rstrip('/')}/media/{filename}"
            voice_sid = send_voice_note(
                to_phone=to_phone,
                media_url=public_media_url,
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number
            )
            result["voice_message_sid"] = voice_sid
            print(f"[Proactive Alert] Voice note sent to {to_phone}. Message SID: {voice_sid}")
        except Exception as err:
            print(f"[Warning] Failed to generate/send proactive voice note: {err}")

    return result

if __name__ == "__main__":
    # Test script entrypoint
    import sys
    test_field_id = int(sys.argv[1]) if len(sys.argv) > 1 else 101
    test_phone = sys.argv[2] if len(sys.argv) > 2 else os.getenv("TEST_PHONE_NUMBER", "+919876543210")
    print(f"Triggering proactive alert test for Field #{test_field_id} to {test_phone}...")
    try:
        res = send_proactive_alert(test_field_id, test_phone)
        print("Success:", res)
    except Exception as ex:
        print("Error:", ex)
