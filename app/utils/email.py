"""
app/utils/email.py
Transactional email via Brevo's HTTP API (HTTPS/443).
SMTP is intentionally avoided — Render blocks outbound SMTP ports.
"""
import os
import requests

from app.utils.logger import log_event

BREVO_ENDPOINT = 'https://api.brevo.com/v3/smtp/email'


# ── Deliverability gate ───────────────────────────────────────────────────
#
# Four of the five active accounts on production are placeholders left from
# setup: admin@company.com, agent@company.com, duck@example.com and
# supervisor@company.com. Escalation mail was going to all of them, and Brevo
# returned 200, so every one of those sends logged as 'email.sent'. Nothing on
# screen or in the logs said the mail had nowhere to land.
#
# example.com is inert by standard. company.com is NOT — it is a real
# registered domain belonging to someone else, and the escalation body carries
# the customer's social handle, the channel, and why they escalated. That mail
# was leaving Shop Zetu, not merely failing.
#
# So this refuses rather than warns. A blocked send returns False exactly like
# a failed one, which the callers already handle.
#
# RFC 2606 and RFC 6761 reserve the first group; the second is the set of
# stand-ins that setup wizards and seed data hand out. Domains people really
# use as mailboxes - gmail.com, outlook.com, mail.com - are deliberately absent.
_RESERVED_TLDS = ('.invalid', '.test', '.localhost', '.example')
_PLACEHOLDER_DOMAINS = {
    'example.com', 'example.net', 'example.org',
    'company.com', 'yourcompany.com', 'mycompany.com',
    'acme.com', 'test.com', 'domain.com', 'email.example',
    'changeme.com', 'placeholder.com', 'localhost',
}


def unreachable_reason(to_email):
    """Why this address cannot receive mail, or None if it looks deliverable.

    Deliberately syntactic. There is no way to prove an address is live without
    sending to it, and the point here is to catch the addresses nobody ever
    meant to send to - not to validate mailboxes.
    """
    addr = (to_email or '').strip().lower()
    if not addr or addr.count('@') != 1:
        return 'not a valid address'
    domain = addr.rsplit('@', 1)[1]
    if not domain or '.' not in domain:
        return f'domain "{domain}" is not routable'
    if domain in _PLACEHOLDER_DOMAINS:
        return f'"{domain}" is a placeholder domain, not a real mailbox'
    if domain.endswith(_RESERVED_TLDS):
        return f'"{domain}" uses a reserved TLD that cannot receive mail'
    return None


def send_email(to_email, subject, html_body, text_body=None):
    # Refuse before anything leaves the process.
    bad = unreachable_reason(to_email)
    if bad:
        log_event('error', 'email.unreachable',
                  f'Refused to send "{subject}" to {to_email}: {bad}. '
                  f'Fix the account email address - mail to it is being discarded.')
        return False

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