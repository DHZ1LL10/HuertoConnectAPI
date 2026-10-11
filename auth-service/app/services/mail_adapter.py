"""Confirm SMTP delivery before reporting success to the client."""
from fastapi import BackgroundTasks, HTTPException
from app.services.mail_service import send_otp_email, MailDeliveryError

async def send_otp_background(background_tasks: BackgroundTasks, *, email, otp_code, tipo, recipient_name="", challenge_id="", expires_at=""):
    # Name retained for router compatibility. Delivery is awaited and bounded.
    try:
        await send_otp_email(to_email=email, otp_code=otp_code, action=tipo, recipient_name=recipient_name, challenge_id=challenge_id, expires_at=expires_at)
    except MailDeliveryError:
        if challenge_id:
            from bson import ObjectId
            from app.core.database import get_db
            await get_db().otp_challenges.delete_one({"_id": ObjectId(challenge_id)})
        raise HTTPException(503, "No se pudo enviar el código. Intenta de nuevo en unos momentos.")
