# Users & Profile, explained

Who has access, who is around right now, and what each person can do. Written so
you can answer "how does that work?" without preparation.

---

## 1. The three roles

| Role | Can do |
|---|---|
| **Admin** | Everything — settings, users, the assistant's behaviour, every conversation |
| **Supervisor** | Oversees agents — sees every conversation, assigns work, reads analytics company-wide |
| **Agent** | Answers conversations assigned to them, and can claim unclaimed ones |

The badge used to say "admin" and leave you to guess what that bought. Your own
profile now spells it out.

**Scoping is real, not cosmetic.** An agent opening Analytics sees figures for
their own conversations only — on the development data that is 5 inbound against
an admin's 127. The page says so directly above the numbers, and it takes that
from the server's own declaration of what it scoped rather than guessing from
your role.

---

## 2. Presence — online or offline

A browser tab sends a heartbeat every 30 seconds while it is **visible**.
Someone counts as online if we have heard from them in the last 90 seconds —
three missed beats of headroom, so a slow request or a brief drop does not make
the dot flicker.

The dot sits on the avatar. Beside the name you get either **"Online now"** or
**"Last seen 4m ago"**.

### Why "Idle" is gone

There used to be an amber middle state, 90 seconds to 5 minutes.

It was removed because nobody could act on it. An agent shown as idle might be
reading a long thread, or might have shut their laptop four minutes ago — and
the badge could not tell you which. Worse, it made someone who had genuinely
left look half-available for five minutes, which is exactly the moment you want
to route work elsewhere.

**"Offline · last seen 4m ago"** carries the same information without the false
reassurance.

### Two bugs that were in here

**Logging out did not make you offline.** The logout endpoint wrote an audit
line and nothing else, so the one moment we know for certain that someone has
left, the page kept insisting they were there — online for 90 seconds, then
lingering as "last seen just now". Signing out now clears presence immediately.

**A malformed timestamp rendered as nothing.** The "last seen" helper returned
`undefined` rather than a string, so instead of an honest "unknown" you got a
blank space. Fixed.

### What presence is not

It is **not** a productivity measure. It tells you whether a browser tab is open
and visible. Someone on a call with a customer, or thinking, is as "online" as
someone idling on the dashboard.

---

## 3. The Users page

The summary is one line — **"● 1 online · 4 people"** — with a deactivated count
appearing only when there is one.

It used to be three bordered cards: Total, Active, Online. On any healthy team
"Total 4" and "Active 4" are the same number, so two of the three said nothing,
and three cards took more vertical space than the list of users itself.

Each row shows the avatar with its presence dot, the name, role, whether they
are online or when they were last seen, and when they joined. Status only
appears when it is **not** active — "active" on every row is noise.

The row used to render a dot, then the word "Online", then "last seen…" —
three renderings of one fact. The dot carries the state now; the text carries
what the dot cannot say, which is *when*.

---

## 4. The lockout you could cause, and can't any more

This is the one worth understanding.

Changing a user's role had **no self-check and no last-admin check**. So an
admin could:

- **Demote themselves** to agent
- **Demote or deactivate the last remaining admin**

Either leaves nobody able to manage users, settings, or the assistant — and
**no way back through the interface**, because every route that could undo it is
itself admin-only. Recovery would have meant editing the database by hand.

Deleting a user already refused self-deletion. This was the same mistake through
two other doors, and both were open.

Now refused, with a reason:

| Attempt | Result |
|---|---|
| Demote yourself | *"You cannot change your own role. Ask another admin."* |
| Deactivate yourself | *"You cannot deactivate your own account."* |
| Demote the only admin | *"This is the only active admin. Promote someone else first."* |
| Rename yourself | Allowed |
| Promote someone to admin | Allowed |

> **If asked how it was verified** — by attempting each one against the real
> endpoint and checking the active-admin count afterwards.

---

## 5. Your Profile page

Your name, email, and password. Also your own presence dot, so what colleagues
see of you on the Users page is not a mystery.

Two small honesty fixes:

- **"Nothing to update" was shown as an error** — in red, beside genuine
  validation errors, teaching people to read a mistake where there was none. It
  is now a neutral "No changes to save."
- The page carried a **private copy of the input styling** that hardcoded white
  backgrounds and grey borders, so its fields drifted from every other field in
  the product and had to be maintained separately. It uses the shared style now.

Password strength is a guide, not a gate — length, mixed case, a digit, a
symbol. It does not stop you saving a weak password.

---

## 6. Honest limitations

- **Presence measures an open tab**, not attention or availability.
- **Deleting a user is permanent.** Their conversations survive, but the account
  does not come back.
- **There is no invitation flow.** An admin creates the account and sets the
  first password, which means that password travels to the person some other
  way.
- **Nothing enforces password rotation or two-factor.**

---

## 7. The one-paragraph version

Three roles, and the scoping behind them is real — an agent genuinely sees only
their own conversations, and the pages say so. Presence is now just online or
offline, because the middle state told you nothing you could act on, and logging
out finally makes you offline. The Users page leads with who is around rather
than three cards restating the same headcount. And the thing most worth knowing:
an admin used to be able to demote themselves or the last remaining admin and
lock everybody out of the platform with no way back through the interface — that
is refused now, with a message saying why.
