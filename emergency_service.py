import json
import os
from twilio.rest import Client


def send_emergency_whatsapp() -> str:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    to_number = os.getenv("TWILIO_WHATSAPP_TO")
    content_sid = os.getenv("TWILIO_CONTENT_SID", "HX6d4547284fdbc71693dd2207a3a4aa68")
    content_variables_raw = os.getenv("TWILIO_CONTENT_VARIABLES", "")

    if not account_sid:
        raise RuntimeError("Missing TWILIO_ACCOUNT_SID")
    if not auth_token:
        raise RuntimeError("Missing TWILIO_AUTH_TOKEN")
    if not to_number:
        raise RuntimeError("Missing TWILIO_WHATSAPP_TO")

    client = Client(account_sid, auth_token)

    payload = {
        "from_": from_number,
        "to": to_number,
        "content_sid": content_sid,
    }

    # Only send content variables if you actually need them in the template.
    if content_variables_raw.strip():
        try:
            json.loads(content_variables_raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("TWILIO_CONTENT_VARIABLES is not valid JSON") from exc
        payload["content_variables"] = content_variables_raw

    message = client.messages.create(**payload)
    return message.sid