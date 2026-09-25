def format_alert(risk_data: dict) -> str:
    """
    Formats the /risk/{field_id} response dictionary into a concise,
    farmer-readable WhatsApp message (< 500 characters).
    
    Backend response contract:
    {
        "field_id": int,
        "disease": str,
        "weather_risk": float,
        "photo_risk": float | None,
        "final_risk": float,
        "spray_start": "HH:MM" | None,
        "spray_end": "HH:MM" | None,
        "treatment": str,
        "estimated_loss_rupees": number,
        "crop": str (optional extra)
    }
    """
    final_risk = float(risk_data.get("final_risk", 0.0))
    disease = risk_data.get("disease", "Unknown Condition")
    crop = risk_data.get("crop")
    photo_risk = risk_data.get("photo_risk")
    spray_start = risk_data.get("spray_start")
    spray_end = risk_data.get("spray_end")
    treatment = risk_data.get("treatment", "Consult local Krishi Vigyan Kendra.")
    estimated_loss = risk_data.get("estimated_loss_rupees", 0)

    # 1. Determine urgency emoji and risk label based on final_risk threshold
    if final_risk > 0.7:
        urgency_emoji = "🚨"
        urgency_label = "HIGH RISK"
    elif final_risk >= 0.4:
        urgency_emoji = "⚠️"
        urgency_label = "MODERATE RISK"
    else:
        urgency_emoji = "✅"
        urgency_label = "LOW RISK"

    risk_pct = round(final_risk * 100)

    # 2. Build structured message lines
    crop_header = f"🌾 Crop: {crop}\n" if crop else ""
    lines = [
        f"{urgency_emoji} *KrishiRaksha Advisory - {urgency_label}*",
        f"{crop_header}🎯 Condition: *{disease}*",
        f"📊 Risk Level: *{risk_pct}%*",
    ]

    # Spray window recommendation if available
    if spray_start and spray_end:
        lines.append(f"⏱ Spray Window: *{spray_start} - {spray_end}*")
    elif spray_start:
        lines.append(f"⏱ Spray Window: *from {spray_start}*")

    # Treatment and estimated economic loss
    lines.append(f"💊 Treatment: {treatment}")
    lines.append(f"💰 Est. Potential Loss: *₹{estimated_loss:,.0f}*")

    # If photo_risk is absent/null, add weather-only note
    if photo_risk is None:
        lines.append("\nℹ️ _Weather-only assessment. Send a leaf photo for a more precise reading._")

    message = "\n".join(lines).strip()
    return message

def format_spoken_alert(risk_data: dict) -> str:
    """
    Creates a simplified, spoken-language version of the alert for text-to-speech.
    """
    final_risk = float(risk_data.get("final_risk", 0.0))
    disease = risk_data.get("disease", "Unknown Condition")
    crop = risk_data.get("crop", "crop")
    treatment = risk_data.get("treatment", "Consult local Krishi Vigyan Kendra")
    spray_start = risk_data.get("spray_start", "")
    spray_end = risk_data.get("spray_end", "")
    estimated_loss = risk_data.get("estimated_loss_rupees", 0)

    # Determine risk levels
    if final_risk > 0.7:
        risk_level = "high"
    elif final_risk >= 0.4:
        risk_level = "moderate"
    else:
        risk_level = "low"

    # Round rupee amount to nearest hundred
    rounded_loss = int(round(estimated_loss / 100) * 100)

    # Build the spoken sentence
    sentences = [f"{risk_level.title()} alert for your {crop} field.", f"{disease} risk is {risk_level}."]
    
    if spray_start and spray_end:
        sentences.append(f"Please spray {treatment} between {spray_start} and {spray_end} today.")
    else:
        sentences.append(f"Please spray {treatment} today.")
        
    sentences.append(f"If untreated, you may lose around {rounded_loss} rupees.")
    
    return " ".join(sentences)
