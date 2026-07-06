"""
app/utils/email.py
Transactional email via Brevo's HTTP API (HTTPS/443).
SMTP is intentionally avoided — Render blocks outbound SMTP ports.
"""
import os
import requests

from app.utils.logger import log_event

BREVO_ENDPOINT = 'https://api.brevo.com/v3/smtp/email'


def send_email(to_email, subject, html_body, text_body=None):
    api_key = os.getenv('BREVO_API_KEY')
    from_email = os.getenv('SMTP_FROM')
    from_name = os.getenv('SMTP_FROM_NAME', 'Shop Zetu')

    if not api_key or not from_email:
        log_event('error', 'email.config', 'BREVO_API_KEY or SMTP_FROM not set — cannot send email')
        return False

    payload = {
        'sender': {'name': from_name, 'email': from_email},
        'to': [{'email': to_email}],
        'subject': subject,
        'htmlContent': html_body,
    }
    if text_body:
        payload['textContent'] = text_body

    try:
        res = requests.post(
            BREVO_ENDPOINT,
            json=payload,
            headers={'api-key': api_key, 'accept': 'application/json', 'content-type': 'application/json'},
            timeout=15,
        )
        if res.status_code in (200, 201):
            log_event('info', 'email.sent', f'Email sent to {to_email}: {subject}')
            return True
        log_event('error', 'email.send_failed', f'Brevo API {res.status_code} for {to_email}: {res.text[:200]}')
        return False
    except Exception as e:
        log_event('error', 'email.send_failed', f'Failed to send to {to_email}: {str(e)[:200]}')
        return False