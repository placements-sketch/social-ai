# Sign in with an emailed code — how it works

Companion to `USERS_AND_PROFILE_EXPLAINED.md`. Read that first for the role
model; this covers the second way in.

---

## The one-sentence version

A one-time code emailed to an address that **already has an account** — same
door as the password, different key, same checks on the way through.

---

## What happens, step by step

1. Someone types their email and clicks **Email me a code**.
2. The server generates six random digits, stores a **bcrypt hash** of them
   against the account, sets a 10-minute expiry, and emails the code.
3. They type the code. The server compares it to the hash, checks it has not
   expired, and checks the attempt budget.
4. On success the code is **destroyed** and the session issued.

That last session is the *same* one the password login issues — same 24-hour
expiry, same role claim, same `last_login` stamp, same audit row. Both paths run
through one function, `_issue_session()`. A second login route that quietly
forgot one of those would be a hole nobody notices, because the user would
simply be logged in and everything would look fine.

---

## The four things that stop this being abusable

A six-digit code is only a million possibilities. On its own that is weak; it is
the constraints around it that make it safe.

| Control | Value | What it stops |
|---|---|---|
| Expiry | 10 minutes | A code read from an old email months later |
| Attempt budget | 5 wrong guesses, then the code is destroyed | Online brute force — without it, a script walks all million codes |
| Single use | Burned the instant it works | Replay from a forwarded or intercepted email |
| Resend cooldown | 60s per account, 8/hour per IP | Flooding someone's inbox — which is both a nuisance and cover for a phishing mail dressed up as one more code |

**Codes are stored hashed, never in plain text.** And with **bcrypt**, not the
sha256 used for password-reset tokens right beside it. That difference is the
detail worth being able to defend: a reset token is 32 random bytes, so sha256
of it is unguessable. Six digits is not — a fast hash is reversible in under a
second by anyone who can read the table. bcrypt puts ~100ms on every guess.

---

## Why the two endpoints answer so differently

**Requesting a code always says the same thing**, whether or not the address has
an account, whether it is deactivated, whether it is on cooldown:

> *If that address has an account, a sign-in code is on its way.*

Anyone can type any address into that box. If it answered truthfully, it would
become a tool for discovering who works here — the first step of a phishing
campaign. The person who genuinely owns the address learns everything they need
from their inbox. (The password-reset endpoint takes the same position, for the
same reason.)

**Verifying a code is specific**, because by then the reason decides what the
person does next:

| Situation | Message |
|---|---|
| Wrong digits | *That code is not right. 3 attempts left.* |
| Past 10 minutes | *That code has expired. Request a new one.* |
| Budget exhausted | *Too many incorrect attempts. Request a new code.* |

Vagueness here would leave someone retyping a code that expired ten minutes ago.
It still never confirms whether an address has an account — an unknown email
gets exactly the same answer as a wrong code.

---

## What it deliberately does not do

- **It does not create accounts.** Accounts carry a role, and an admin
  provisions them. If a code could mint an account, anyone with an email address
  could walk in and the role model would be decoration.
- **It does not let deactivated people in.** Checked at both ends: no code is
  issued to a deactivated account, and even a code issued moments before
  deactivation is refused at verification. Otherwise emailed codes would become
  the documented way around offboarding.
- **It does not replace passwords.** Password sign-in is untouched. If the
  mailer goes down, everyone can still get in.

---

## Setup

**Nothing new.** Delivery reuses the Brevo HTTP API that already sends
password-reset mail — `BREVO_API_KEY` and `SMTP_FROM`, both already in Render.
If password resets arrive today, codes will too.

One database change, **Step 23** in `database/PRODUCTION_CHANGES.md`: four
columns on `auth_users`. No new table — a code belongs to exactly one account
and only one is ever live at a time, so a row per account is the whole story.

*(Brevo over HTTPS rather than SMTP because Render blocks outbound SMTP ports —
see `app/utils/email.py`.)*

---

## Questions you will get

**"Why not SMS?"** It costs money per message, needs a phone number on every
account that we do not collect, and Kenyan carrier delivery is not something we
control. Email is already provisioned for every user by definition — it *is*
their account name.

**"What if someone's email is compromised?"** They can be signed in as, yes —
which is exactly as true of the existing password-reset link. Deactivate the
account and both doors close immediately: the session-revocation hook kills any
live token on the next request.

**"Can we drop passwords entirely?"** Possible later, but not advisable yet. It
would make Brevo a single point of failure for all access to the platform.

**"Why six digits and not eight?"** Six is what people can hold in their head
between the inbox and the tab. The attempt budget, not the length, is what
makes brute force fail.

**"Does the code work if they request two?"** No — a new code replaces the old
one. Only the most recent is ever valid, so the code from the first email stops
working the moment a second is sent.
