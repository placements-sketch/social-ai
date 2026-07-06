"""
app/utils/email.py
Minimal transactional email sender over SMTP (Brevo). No SDK — plain smtplib.
"""
import os
import ssl
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.utils.logger import log_event


def send_email(to_email, subject, html_body, text_body=None):
    host = os.getenv('SMTP_HOST', 'smtp-relay.brevo.com')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_email = os.getenv('SMTP_FROM')
    from_name = os.getenv('SMTP_FROM_NAME', 'Shop Zetu')

    if not all([user, password, from_email]):
        log_event('error', 'email.config', 'SMTP env vars not set — cannot send email')
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>"
    msg['To'] = to_email
    if text_body:
        msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
        log_event('info', 'email.sent', f'Email sent to {to_email}: {subject}')
        return True
    except Exception as e:
        log_event('error', 'email.send_failed', f'Failed to send to {to_email}: {str(e)[:200]}')
        return False