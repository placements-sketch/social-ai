# Google sign-in — how it works and how to answer questions about it

Companion to `USERS_AND_PROFILE_EXPLAINED.md`. Read that first for the role
model; this document only covers the second front door.

---

## The one-sentence version

Google sign-in is a **faster way in for people who already have an account** —
it never creates accounts, never bypasses deactivation, and never replaces the
password form.

If you remember nothing else, remember that sentence. Every design decision
below follows from it.

---

## What it does not do (and why that matters)

Three things it deliberately refuses, each of which is the default behaviour of
most "Sign in with Google" buttons you have used elsewhere:

| It will not… | Because |
|---|---|
| Create an account for a new Google user | Accounts carry a **role** — admin, supervisor, agent. That role decides what someone can see and do. If Google could mint accounts, anyone with a Gmail address could walk in, and the role model would be decoration. |
| Let a deactivated person in | Offboarding is a real security control. If Google sign-in ignored `status`, it would become the documented way around it — you would remove someone's access and they would still be able to log in. |
| Replace passwords | An outage at Google would otherwise lock every administrator out of the platform at once. Passwords stay as the floor. |

**If someone asks "so anyone at the company can just log in?"** — no. An admin
creates the account first, on the Users page, with a role. Google only proves
that the person at the keyboard owns that email address.

---

## What actually happens when you click the button

1. The login page asks the server `GET /api/auth/google/config`. The server
   replies with whether Google sign-in is switched on, and the public client id.
   **If it is not configured, the button never appears** — there is no dead
   button to click.
2. Google shows its account chooser and hands the browser an **ID token**: a
   signed statement from Google saying "this person owns `you@shopzetu.com`".
3. The browser posts that token to `POST /api/auth/google`.
4. The server verifies it (next section), finds the matching account by email,
   checks it is active, and issues the **same 24-hour session token** the
   password login issues.

Step 4 runs through `_issue_session()` — one function, shared with the password
path. That is deliberate: a second login route that quietly forgot to stamp
`last_login`, attach the role claim, or write the audit row would be a hole
nobody would ever notice, because the user would simply be logged in and
everything would look fine.

---

## The security question you will actually get asked

> "How do you know the token is real?"

Two separate checks, and the second is the one that matters:

**1. Is it genuinely from Google?** Google verifies the signature for us at its
`tokeninfo` endpoint. An expired, altered, or invented token is rejected there.

**2. Was it issued *to us*?** This is the check people forget, and skipping it
is a complete authentication bypass. A valid, correctly-signed Google ID token
issued to *any other application in the world* is trivially obtainable — sign
into any random site that uses Google, and your browser is holding one. If we
only checked the signature, that token would be accepted here too.

So we check `aud` (audience) equals our own client id. Signature validity says
*"Google issued this."* Only `aud` says *"Google issued this to us."*

We also check `iss` is genuinely Google, and `email_verified` is true.

**Proof it works.** All four cases are tested:

```
401  token minted for ANOTHER app     → This sign-in was issued for a different application
401  unverified email address         → That Google account has no verified email address
401  wrong issuer                     → Unexpected token issuer
403  email with no account here       → No account exists for stranger@gmail.com…
403  email of a DEACTIVATED account   → User account is not active
200  email of an active account       → session issued
```

---

## Why the error messages differ from the password form

The password form says "that email and password combination did not match an
account" — vague on purpose, so it cannot be used to discover which email
addresses have accounts.

Google sign-in says the opposite: *"No account exists for stranger@gmail.com.
Ask an administrator to create one."*

That is not an inconsistency. By that point the person **has already proved they
own that address** — there is nothing left to leak, and knowing they need an
admin to provision them is the one thing that gets them unstuck. Being vague
there would strand a new employee with no idea what to do.

---

## Setting it up (Render + Google Cloud Console)

Nothing in the database changes. One environment variable, one console entry.

**1. Google Cloud Console** → APIs & Services → Credentials → *Create
credentials* → **OAuth client ID** → Web application.

Add your frontend origin under **Authorised JavaScript origins** — the origin
only, no path:

```
https://<your-frontend-domain>
http://localhost:5173        ← only if you want it working locally too
```

You do **not** need a redirect URI: this uses Google's in-page flow, which hands
the token to JavaScript rather than redirecting.

**2. Render** → the backend service → Environment → add:

```
GOOGLE_CLIENT_ID = <the client id ending in .apps.googleusercontent.com>
```

The **client secret is not needed and must not be added.** We never exchange an
authorization code, so there is nothing to keep secret. The client id is public
by design — it ships in the page source of every site using Google sign-in.

**3. Redeploy.** The button appears on its own; the frontend asks the server
whether it is configured rather than being rebuilt with the value baked in. That
is why setting the variable is enough, and why a frontend built before you set
it does not need rebuilding.

---

## Things that will come up

**"Can we restrict it to @shopzetu.com only?"** Not needed as built — a Gmail
address gets in only if an admin already created an account with that exact
address. The email match *is* the restriction, and it is stricter than a domain
check because it is per-person rather than per-domain.

**"What if someone's Google account is compromised?"** Deactivate them on the
Users page. Both doors close: the password path and the Google path check
`status` on every login, and the session-revocation hook kills their existing
token on the next request rather than waiting for it to expire.

**"Does it work on mobile?"** Yes — Google's button handles its own layout, and
the login page is already responsive.

**"Why is the button styled differently from ours?"** Google renders it inside
an iframe and does not permit restyling. That is a condition of using their
sign-in, not an oversight. It sits above the password form with a divider
carrying the visual join.
