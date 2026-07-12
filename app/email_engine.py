import resend
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

resend.api_key = os.getenv("RESEND_API_KEY")

TEMPLATES_DIR = Path(__file__).parent / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def send_preorder_confirmation_email(email, order_details):
    template = env.get_template("preorder_confirmation.html")
    html_content = template.render(order_details)
    resend.Emails.send({
        "from": os.getenv("RESEND_FROM_EMAIL", "no-reply@vijayebhav.com"),
        "to": email,
        "subject": "Pre-order confirmed — welcome to the future of learning!",
        "html": html_content,
    })

# notification email is user opts for notify whenever selected device is available for purchase
def send_notify_new_device_email(email, device_info):
    template = env.get_template("notify_new_device.html")
    html_content = template.render(device_info)
    resend.Emails.send({
        "from": os.getenv("RESEND_FROM_EMAIL", "no-reply@vijayebhav.com"),
        "to": email,
        "subject": "We've saved your spot — VijayeBhav is coming",
        "html": html_content,
    })