# Sufiyan Consultancy Services — Website

A modern, fully responsive single-page website for **Sufiyan Consultancy Services** —
a firm offering company registration, GST/taxation, trademark, legal (advocate) and
web/digital services with an in-house team of CAs, Advocates and Developers.

## Files
- `index.html` — all page content and sections
- `styles.css` — styling (navy + gold theme, mobile responsive)
- `script.js` — mobile menu, scroll effects, and the enquiry forms

## How to view
Just open `index.html` in any browser — no build step, no dependencies.

## What to customize (before going live)
Search-and-replace these placeholders with the real details:

| Placeholder | Where | What to change |
|-------------|-------|----------------|
| `919999999999` | `script.js` (top, `WHATSAPP_NUMBER`), `index.html` (WhatsApp/`wa.me` links) | Business WhatsApp number — country code + number, no `+` |
| `+91 99999 99999` | `index.html` (top bar, contact, footer) | Display phone number |
| `info@sufiyanconsultancy.com` | `index.html` | Business email |
| `Your Office Address, City, State - PIN` | `index.html` (contact section) | Full office address |
| Stats (`500+`, `1000+`, `15+`, `4.9★`) | `index.html` | Real numbers |
| Testimonials | `index.html` | Real client reviews/names |

## Forms
The "Request a Callback" and "Contact" forms open **WhatsApp** with a pre-filled
enquiry message (no backend needed). If you later want the enquiries to arrive by
email instead, connect the form to a service like Formspree, Google Forms, or a
small backend — happy to wire that up.

## Deploy (free options)
- **GitHub Pages** — push and enable Pages on this folder
- **Netlify / Vercel** — drag-and-drop the `sufiyan-consultancy` folder
