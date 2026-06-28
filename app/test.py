import resend
import os
from email_engine import preorder_email

resend.api_key = os.getenv("RESEND_API_KEY")



if __name__ == "__main__":
    params: resend.Emails.SendParams = {
        "from": "support@vijayebhav.com",
        "to": "arjunsinghtomar03511@gmail.com",
        "subject": "Your Preorder Confirmation - ORDER123456",
        "html": preorder_email({
    "name": "Arjun Singh Tomar",
    "order_id": "ORDER123456",
    "address_flat": "184-B-1",
    "address_street": "KANYA KUBJA NAGAR",
    "address_city": "Indore",
    "address_pin": "452006",
    "address_state": "Madhya Pradesh",
}),
    }

    try:
        response = resend.Emails.send(params)
        print("Email sent successfully:", response)
    except Exception as e:
        print("Error sending email:", e)