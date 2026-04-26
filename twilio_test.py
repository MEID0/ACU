import os
from twilio.rest import Client

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_WHATSAPP_FROM")
to_number = os.getenv("TWILIO_WHATSAPP_TO")
content_sid = os.getenv("TWILIO_CONTENT_SID")

print("SID set:", bool(account_sid))
print("TOKEN set:", bool(auth_token))
print("FROM set:", bool(from_number))
print("TO set:", bool(to_number))
print("CONTENT SID set:", bool(content_sid))

client = Client(account_sid, auth_token)

message = client.messages.create(
    from_=from_number,
    to=to_number,
    content_sid=content_sid
)

print("Message SID:", message.sid)
print("Status:", message.status)
