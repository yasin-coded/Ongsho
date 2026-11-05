# Product

<!-- impeccable:product-schema 1 -->

Summarised from `docs/PRD.md` and `docs/design.md`. Those files stay the source of truth.

## Platform

web

## Users

Students, young professionals and families in Bangladesh who pay for digital subscriptions (Netflix, Spotify, YouTube Premium, ChatGPT and other AI tools, Canva, hosting, domains) in BDT or USD, and often share them with friends and family. One person is usually the owner of some plans and a member of others. Resellers are users who create a plan in Reseller mode to sell access to buyers.

## Product Purpose

Ongsho (অংশ) tracks every subscription a person pays for, gets renewal dates right, and keeps a clear record of who owes what and who paid when on shared plans. Success: nobody forgets a renewal, nobody pays the wrong amount or pays twice, and every payment has a transaction ID the owner confirmed.

## Positioning

Ongsho is a notebook, not a wallet. It never moves money. Owners pay providers their own way; members pay owners their own way (bKash, Nagad, bank, cash) and record the transaction ID, which only the owner can confirm. A spreadsheet stores numbers; Ongsho calculates correct due dates, splits, running balances and IOUs.

## Operating Context

- Payments happen outside the app, through bKash, Nagad, Rocket, mobile banking, bank, cash or a dollar card.
- Today the money side lives in group chats and screenshots.
- Roles belong to a plan, not a person: "My Plans" (owner) and "Shared Plans" (member) are separate.
- All dates are in Asia/Dhaka time; money is BDT, with USD plans stored with the exchange rate used.

## Capabilities and Constraints

- Accounts with verified email; profile with preset avatar, email change (pending until verified), password change.
- Plans: Owner or Reseller mode (locked after creation), BDT or USD, weekly / monthly / yearly / custom cycle, auto-renew or fixed term, trial, status (trial, active, paused, cancelled, expired), recommended payment method, note, rarely-used flag.
- Shared plans: email invites (single use, expiring, backup link), equal or custom split, leftover paisa to the owner, owner seat auto-Paid in Owner mode, no owner seat in Reseller mode.
- Due statuses: Due, Pending, Paid, Waived. Only the owner changes a status. Transaction ID required and unique per plan. No partial payments.
- IOUs when a member pays someone else's due, netted per pair.
- Members never see other members' emails or payment status.
- Leave, remove, replace members; ownership transfer (Owner mode only); delete with password (erase or archive).
- Reminders, calendar (next 30 days), notifications tab, dashboard insights (monthly spend, by category, six-month forecast, rarely-used yearly cost).
- Current scope: frontend only, against a mock API layer with the same shapes as the planned endpoints.
- Light theme only. No dark mode.

## Brand Commitments

- Name: Ongsho (অংশ). Wordmark and illustrations supplied in `Assets/` (copied into the web app). Fonts: Cocogoose and Bahnschrift, supplied as woff2.
- Fixed sentence: "Payments happen outside Ongsho. Ongsho only keeps the record."
- Visual system is fully specified in `docs/design.md`.

## Evidence on Hand

- Supplied SVGs: wordmark, hero, footer, chat phone, ten service logos (Spotify, YouTube, Apple Music, Netflix, Claude, ChatGPT, Cursor, Google, Amazon Prime, Hotstar). No Canva logo yet.
- Mock data in `docs/design.md` Section 9. No real users, testimonials, metrics or pricing exist; do not invent them.

## Product Principles

1. Never imply Ongsho moves money.
2. Every number is derived from records, never typed or hard-coded.
3. Owner and member views are separate; member views protect other members' privacy.
4. History is never deleted; reversals and archives keep the record honest.
5. Status is always text plus color.

## Accessibility & Inclusion

WCAG AA contrast, full keyboard use, visible focus, usable at 200% and 400% zoom, respects reduced motion (no blinking, no smooth scroll).
