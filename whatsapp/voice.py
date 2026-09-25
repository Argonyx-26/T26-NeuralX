import os
import re
from gtts import gTTS
from twilio.rest import Client

def clean_text_for_speech(text: str) -> str:
    """
    Strips markdown formatting (*, _, ~) and emoji characters so the text-to-speech
    engine delivers clear, natural speech output without reading raw symbols.
    """
    # Remove markdown asterisks, underscores, backticks, tildes
    clean = re.sub(r'[*_`~]', '', text)
    # Remove emojis and special symbol ranges
    clean = re.sub(r'[^\w\s,.:/₹%@!?\-–]', '', clean)
    # Replace Rupee symbol with word for natural pronunciation
    clean = clean.replace('₹', ' Rupees ')
    # Normalize multiple spaces or blank lines
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def generate_voice_note(text: str, output_path: str, lang: str = "en") -> str:
    """
    Converts alert text into an MP3 audio note using gTTS and saves it to output_path.
    Returns the absolute path to the generated MP3 file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Preprocess text for clear audio pronunciation
    speech_text = clean_text_for_speech(text)
    if not speech_text:
        speech_text = "KrishiRaksha crop risk advisory update."
        
    tts = gTTS(text=speech_text, lang=lang, slow=False)
    tts.save(output_path)
    return os.path.abspath(output_path)

def send_voice_note(
    to_phone: str,
    media_url: str,
    account_sid: str = None,
    auth_token: str = None,
    from_number: str = None
) -> str:
    """
    Sends an audio file URL as a WhatsApp media message via the Twilio REST API.
    
    Parameters:
    - to_phone: recipient phone number (e.g. "+919876543210" or "whatsapp:+919876543210")
    - media_url: public URL to the audio file (must be publicly reachable, e.g. via ngrok)
    """
    account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
    from_number = from_number or os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables must be set.")

    # Twilio WhatsApp numbers must be prefixed with 'whatsapp:'
    if not to_phone.startswith("whatsapp:"):
        to_phone = f"whatsapp:{to_phone}"
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        from_=from_number,
        to=to_phone,
        media_url=[media_url]
    )
    return message.sid
