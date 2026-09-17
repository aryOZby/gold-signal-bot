# WhatsApp + LLM automation for an Israeli insurance/pension agency — 2026 pricing & feasibility

**Research date: 17 September 2026.** All figures below were fetched live on that date. Where a number could not be
confirmed from a primary source, it is marked ⚠️ and repeated in the "Could NOT verify" section at the end.

---

## 0. The three findings that change the plan

1. **Meta starts charging for service messages on 1 October 2026 — 14 days from now.** Free-form replies inside the
   24-hour window, and utility templates inside that window, have been free since Nov 2024 / Jul 2025 respectively.
   Both become billable on 1 Oct. There is a new free allowance of 1,000 service messages per business phone number
   per month. Any cost model built on "service is free" is about to be wrong.
   ([Meta pricing docs](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing), updated 5 Aug 2026)

2. **Under Coexistence, replies the owner types on his own phone stay free forever.** Meta's own wording: "Messages
   sent from the WhatsApp Business app are not subject to the customer service window and do not create, extend, or
   affect Cloud API conversation windows or Cloud API pricing." Since the design is human-approves-then-sends, routing
   approved replies back to the phone rather than through the API removes almost the entire post-October service-message
   bill. This is a design decision worth real money.
   ([Meta coexistence docs](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users))

3. **The cheap OpenAI tier is measurably bad at Hebrew; Google's cheap tier is not.** On the community Hebrew LLM
   leaderboard, `gpt-5-nano` scores 14.6 on Nikud vs 70.7 for `gemini-2.5-flash-lite` — and `gpt-4o-mini` scores 11.8
   on translation vs 25.0. Defaulting to the cheapest OpenAI model because it is cheapest would be a mistake here.
   ([hebrew-llm-leaderboard/chat-results](https://huggingface.co/datasets/hebrew-llm-leaderboard/chat-results/viewer))

---

## A. WhatsApp Business Platform (Cloud API) in 2026

### A1. Current pricing model — confirmed

Per-**message** pricing, effective 1 July 2025, replacing conversation-based pricing (now deprecated). Charged on
**delivery**, not send. Rate depends on the recipient's country calling code and the template category.

| Category | Template? | When sendable | Charged today (≤30 Sep 2026) | Charged from 1 Oct 2026 |
|---|---|---|---|---|
| Marketing | Yes | Any time | **Yes** | Yes |
| Utility | Yes | Any time | Yes **outside** CSW; **free inside** CSW | **Yes, always** |
| Authentication | Yes | Any time | **Yes** | Yes |
| Service (free-form) | No | Only inside an open 24h CSW | **Free** | **Billable, after 1,000 free/number/month** |
| Inbound (user → business) | — | — | **Never charged** | Never charged |

Meta may only change prices on 1 Jan / 1 Apr / 1 Jul / 1 Oct, with 1 month notice for rate-card updates, 3 months for
pricing-model add-ons, and 6 months for pricing-model changes.

### A2. Are service and in-window utility messages still free? — Yes, for 13 more days

- **Service messages:** free since 1 November 2024. **Billable from 1 October 2026** at each market's utility/
  authentication rate. No volume tiers for service. **1,000 free service messages per business phone number per month**,
  not rolling over, resetting monthly.
- **Utility templates inside an open CSW:** free since 1 July 2025. **Billable from 1 October 2026.**
- **Free entry point (FEP) window:** unchanged — if a user reaches you via a Click-to-WhatsApp ad or Page CTA button and
  you reply within 24h, a 72-hour window opens in which *all* message types are free. Not relevant to this client unless
  they run WhatsApp ads.

Separately, **Meta Business Agent** (Meta's own hosted AI agent) began token billing on 1 Aug 2026 at **$2.00/M tokens**
(~4–5 ¢/message). This does **not** apply here — using your own LLM keeps you on plain service-message rates. Meta's
table is explicit: for third-party AI, "3rd-party AI charges the business."

### A3. Israel (IL, +972) per-message rates, USD

| Category | Rate (USD) | Notes |
|---|---|---|
| Marketing | **$0.0353** | |
| Utility | **$0.0053** | |
| Authentication | **$0.0053** | |
| Authentication-international | n/a | Israel has no auth-int'l rate |
| Service (from 1 Oct 2026) | **$0.0053** | matches utility/auth by market |

Israel is a **standalone market** on Meta's rate card (confirmed directly in Meta's country-calling-code table:
`Israel … 972 … IL`), so it is *not* subject to "Rest of Middle East" rates, and it is **not** in the list of markets
receiving rate changes on 1 Oct 2026. The rates above should therefore hold through Q4 2026.

⚠️ **Sourcing caveat:** Meta publishes the rate card as an interactive JS widget and downloadable files that I could not
fetch directly. The Israel figures come from two independent BSP mirrors of Meta's card that agree exactly
([Wabery](https://wabery.com/docs/whatsapp-pricing/), [SleekFlow](https://sleekflow.io/en-us/blog/whatsapp-business-price)).
Confirm against the live card at <https://whatsappbusiness.com/products/platform-pricing/> before quoting a client.

### A4. Free allowance

- **Today:** all service messages free; all in-window utility templates free. No separate numeric allowance.
- **From 1 Oct 2026:** 1,000 free service messages per business phone number per month.
- Volume tiers exist for utility and authentication (aggregated at business-portfolio level, reset monthly), but this
  client's volumes are far below the first tier boundary, so list rates apply.

### A5. Is Cloud API itself free? — Yes

Meta hosts Cloud API at no charge; there is no licence, setup, or hosting fee. You pay only per delivered message. This
is confirmed in multiple current setup guides and is consistent with Meta's pricing documentation, which describes only
per-message charges. (On-Premises API is deprecated; Cloud API is the only path.)

### A6. Coexistence — generally available, and the right answer for this client

**Status: GA in 2026.** Meta calls it "onboarding WhatsApp Business app users"; support and partner docs call it
Coexistence. The number stays registered on the WhatsApp Business app on the owner's phone *and* is connected to Cloud
API simultaneously, with messages mirrored both ways.

**What it supports:**

| Capability | Under Coexistence |
|---|---|
| Inbound 1:1 messages via webhook | ✅ Yes |
| Sending via Cloud API | ✅ Yes |
| Owner keeps normal WhatsApp on his phone | ✅ Yes — 1:1 chatting, calls, catalog, labels all unchanged in the app |
| Messages the owner sends from the phone | ✅ Mirrored to you via the `smb_message_echoes` webhook |
| Chat history sync | ✅ Up to **180 days** of 1:1 history; media asset IDs only for media from the last **14 days** |
| Contact sync | ✅ All contacts with a WhatsApp number |
| **Group chats** | ❌ **Not supported, not synchronised** |
| Voice/video calls | ❌ Not available via API (unchanged in the app) |
| Business profile, labels, quick replies, away messages, catalog | ❌ Not exposed on Cloud API (unchanged in the app) |

**What it breaks on the phone** (be explicit with the owner — these are permanent while connected):

- Disappearing messages turned **off** for all 1:1 chats
- View-once messages **disabled**
- Live-location messages **disabled**
- Broadcast lists **disabled**; existing lists become read-only
- Companion devices (WhatsApp Web / Mac) are **unlinked once** at onboarding and must be re-linked
- Throughput fixed at **20 messages/second** (irrelevant at this volume)

**Hard requirements and gotchas:**

- Number must be on the **WhatsApp Business app**, version **2.24.17+** — *not* the consumer WhatsApp app. If the owner
  is on regular WhatsApp today, he must migrate to the Business app first (supported, in-place, keeps the number).
- **If the number is later re-registered on consumer WhatsApp, Meta disconnects it** (`BUSINESS_DOWNGRADE` in the
  `account_update` webhook). Also watch `PRIMARY_INACTIVITY` (~14 days) and `COMPANION_INACTIVITY` (~30 days).
- **You must onboard through a Solution Partner or Tech Provider** with Advanced Access and Embedded Signup **v4**.
  Meta's requirements state plainly: "You must already be a Solution Partner or Tech Provider." A business cannot
  self-serve into Coexistence the way it can into plain Cloud API. **This is the single biggest architectural
  constraint** — it means either going through a BSP that supports Coexistence, or registering as a Tech Provider.
- **Embedded Signup v2 is deprecated on 15 October 2026.** Any provider you pick must already be on v4.
- History sync must be completed **within 24 hours** of onboarding or the customer must be offboarded and redo the flow.
- CSW nuance: a CSW only opens if the user messages *after* onboarding. Messages the owner sends from the phone do
  **not** open, extend, or bill against Cloud API windows.

⚠️ Meta publishes **no country availability list** for Coexistence. Third-party trackers describe it as broadly
available including "most of Europe" and the Middle East, but **Israel is not individually confirmed** in any source I
found. The only reliable test is to run Embedded Signup with the real number and see whether it throws a country error.
**Treat Israeli availability as unverified and test it before committing to the design.**

### A7. Groups and voice notes

**Groups — your assumption is half right, and the nuance matters.**

There *is* now a **Groups API** (Meta docs updated 16 June 2026), so "no groups" is no longer literally true. But it is
unusable for this client:

- Requires an **Official Business Account (OBA)** — the verified badge, which needs notable brand presence and takes
  1–4 weeks with no guarantee of approval. An individual insurance agency will most likely not qualify.
- **"Groups are not available for WhatsApp Business app phone numbers"** — i.e. **mutually exclusive with Coexistence**.
- Max **8 participants**; groups are **invite-only and must be created by the business via the API**; max 1 Cloud API
  business per group.

So: **you cannot read or receive messages from pre-existing WhatsApp groups the owner is already in.** That capability
does not exist on the official platform, with or without the Groups API. If group intake is a hard requirement, the only
technical routes are unofficial libraries (§B12 — don't) or asking participants to forward messages 1:1.

**Voice notes — fully supported.** Confirmed flow:

1. Inbound webhook carries `type: "audio"` with `audio.id`, `audio.mime_type` (`audio/ogg; codecs=opus` for in-app voice
   notes) and `audio.voice: true`. The `voice: true` flag distinguishes a recorded voice note from an uploaded audio file.
2. `GET https://graph.facebook.com/<VERSION>/<MEDIA_ID>?phone_number_id=<PHONE_NUMBER_ID>` with a bearer token → returns
   a temporary `url`, `mime_type`, `file_size`.
3. `GET <url>` with the **same bearer token** → raw bytes. Omitting the token fails.

Critical expiries: **media URLs expire after 5 minutes**; **media IDs received via webhook are downloadable for 7 days**.
Max media size 100 MB (error 131052 above that). Download and persist the bytes immediately — never store the temporary URL.

### A8. Onboarding requirements in 2026

| Step | Detail |
|---|---|
| Meta Business Portfolio | Required, with business email confirmation |
| Business verification | Required for messaging beyond the starter tier. Documents: legal business name, address, phone, ideally a website on your own domain. ⚠️ Typically **1–7 business days** (third-party reports; Meta publishes no SLA), longer if manually reviewed |
| Display name | Must relate to the real business name, no generic terms. Reviewed by Meta; status via `name_status`. ⚠️ Minutes to hours typically, no published SLA. After a name change is approved you must **re-register** the number |
| Phone number | **Plain Cloud API:** the number must NOT be active on consumer WhatsApp or the Business app — it must be deleted from WhatsApp first. **Coexistence:** the opposite — the number must already be live on the WhatsApp Business app |
| Personal number migration | A personal/consumer WhatsApp number can be used, but only after deleting the WhatsApp account on it (plain Cloud API), or after converting it to the WhatsApp Business app (Coexistence). Coexistence is the non-destructive path |
| Registration | API-only: `POST /<PHONE_NUMBER_ID>/register` with a 6-digit two-step PIN. Cannot be done in WhatsApp Manager. Limited to 10 requests per 72-hour moving window |
| Templates | Approval typically minutes to hours |
| Token | Create a System User and generate a permanent token with `business_management`, `whatsapp_business_messaging`, `whatsapp_business_management` |
| Webhook | Public HTTPS endpoint. Subscribe to `messages`; for Coexistence also `history`, `smb_message_echoes`, `smb_app_state_sync` |
| OBA / green tick | Optional, 1–4 weeks, not guaranteed, not needed |

### A9. Rate limits and messaging tiers for a new WABA

- **Messaging limit** (unique users you can *initiate* conversations with per rolling 24h, outside a CSW). Now set at
  **business-portfolio** level, not per phone number. New portfolios start at **250**.
- Ladder: **250 → 2,000 → 10,000 → 100,000 → Unlimited.** (There is no 1,000 tier.)
- To reach 2,000, complete one "scaling path": verify your business, have your partner verify it, or deliver 2,000
  high-quality template messages to unique users in a moving 30-day window. Automatic scaling after that requires high
  quality and using ≥50% of the current limit in the previous 7 days.
- Query via the `whatsapp_business_manager_messaging_limit` field — `messaging_limit_tier` is **deprecated**.
- **Throughput:** 20 mps fixed under Coexistence; 80 mps default otherwise; 1,000 mps only for very large senders.
- **Inbound messages and replies inside a CSW do not count against the messaging limit.** At 150 proactive
  messages/month, the starting 250/day tier is ~50× more headroom than this client needs. **Tier limits are a non-issue here.**

---

## B. BSPs and alternatives

### B10. Twilio

- **Twilio fee: $0.005 per message, inbound *or* outbound**, on top of Meta's fees, which Twilio passes through.
  (Twilio's page states "Pricing current as of August 2026.")
- No monthly platform fee for Programmable Messaging; the Conversations API adds a per-MAU fee and Flex is per-seat.
  A phone number is not required for WhatsApp itself.
- Twilio has confirmed it is passing through Meta's 1 Oct 2026 changes and that its own $0.005 is unchanged.
- **The inbound charge is what hurts here.** 3,000 inbound messages/month = **$15/month of pure Twilio fee** before a
  single reply, against a Meta bill that is currently under $1. Twilio is a poor fit for an inbound-heavy, low-outbound
  workload.

### B11. Other BSPs

| Provider | Entry price | Meta fee treatment | Verdict for 1–3 seats |
|---|---|---|---|
| **360dialog** | **€49/number/month** (Regular); €99 Premium; €500 high-throughput | **Pass-through, zero markup** | ✅ **Best fit.** Flat fee, no markup, no seat tax, API-first (not an inbox — which is fine, you're building the app) |
| **Twilio** | No platform fee | Pass-through + **$0.005/msg both directions** | ❌ Inbound fee dominates |
| **Wati** | ⚠️ $39–59/mo annual (sources disagree) | **~20% markup** + per-extra-user fees | ❌ Markup plus seat fees; AI features gated behind higher tiers |
| **respond.io** | $79/mo annual (Starter, 5 users) | Pass-through, no markup | ⚠️ Priced for teams; monthly-active-contact model; broadcasts need Growth ($159–199) |
| **Rasayel** | $400/mo for 10 users | — | ❌ Wildly oversized |
| **Chatwoot** (self-host) | **$0 licence**, Community Edition, unlimited agents | You bring your own BSP/Cloud API | ✅ Good *inbox* layer if you want one. Needs a ≥4 GB VPS. No Captain AI/SSO in CE. Cloud tiers $19/$39/$99 per agent/mo |

**Recommendation:** either **direct Cloud API** (cheapest, but see the Coexistence Tech-Provider constraint in §A6) or
**360dialog at €49/number/month** if you need a partner to get Coexistence onboarding. 360dialog's zero-markup,
per-number, no-seat-fee model is the only mainstream BSP whose pricing shape matches a 1–3 person business. Wati and
respond.io are priced for support teams and would cost more than the entire Meta + LLM + STT bill combined.

⚠️ 360dialog prices in **EUR**; I did not verify a current EUR/USD rate, so I have left it in euros throughout.

### B12. Unofficial libraries (Baileys, whatsapp-web.js, wppconnect) — blunt assessment

**Do not recommend these to an insurance agency. Not as a stopgap, not for the pilot.**

- **They violate WhatsApp's Terms of Service.** The Business ToS prohibits reverse-engineering and unauthorised
  automated access. Baileys' own documentation states it "is an unofficial library and is not affiliated with WhatsApp."
  Neither project offers any warranty against bans; both ship near-identical disclaimers.
- **Enforcement is real.** Meta issued a takedown against the original Baileys repository in April 2023. WhatsApp's
  Business Policy states that on termination for violations, Meta "may prohibit you and your organization from **all
  future use** of WhatsApp products and services."
- **The blast radius is catastrophic for this specific client.** The number at risk is a licensed agent's primary
  business line — the channel through which his entire book of clients reaches him. A ban is not a technical incident,
  it is the loss of his client communication channel with no appeal path and no migration window. The asymmetry is
  absurd: you are risking the core business asset to avoid a ~€49/month BSP fee.
- **Regulatory overlay.** An Israeli licensed insurance/pension agent handles personal financial data under supervisory
  obligations. Routing that data through a reverse-engineered client with no DPA, no vendor contract, no uptime
  commitment and no lawful-basis story is not defensible to a regulator, an E&O insurer, or the client himself.
- The "keep under 1,000–2,000 msgs/day and warm up slowly" folklore circulating in developer communities is **not a
  documented WhatsApp limit** and does not make the use compliant. It reduces, but does not eliminate, risk.

The only honest professional position: these libraries are interesting for hobby projects and internal throwaway tools
on burner numbers. Putting a regulated financial intermediary's main line on one would be malpractice.

### B13. Telegram Bot API for internal staff — free, and a genuinely good idea

- **Cost: $0.** "By default, bots are able to message their users at no cost." Paid broadcasts exist but require
  ≥100,000 Stars balance and ≥100,000 MAU — irrelevant here.
- **Voice notes: fully supported.** The `Voice` object provides `file_id`, `duration`, `mime_type`, `file_size`.
  Download via `getFile` then `https://api.telegram.org/file/bot<TOKEN>/<file_path>`.
- **Limits:** `getFile` downloads capped at **20 MB**; bot uploads capped at **50 MB**. A self-hosted local Bot API
  server removes the download cap and raises uploads to 2,000 MB. Sending: ~1 msg/sec per chat, 20/min per group,
  ~30/sec globally, with `429` + `parameters.retry_after` to honour.
- **20 MB is ample for voice notes.** A 45-second Opus voice note is on the order of tens of kilobytes.
- **Unlike WhatsApp, Telegram bots can be added to groups** — so an internal "office" group with the two back-office
  staff and the bot is workable, which is exactly the capability WhatsApp denies you.

**Recommendation: use Telegram for the 2 back-office staff and internal task routing, WhatsApp only for clients.** This
removes staff traffic from the WhatsApp service-message meter entirely (worth ~$0 today but real money after 1 Oct),
sidesteps the 24-hour CSW for internal messages, gives you group support, and costs nothing.

---

## C. LLM API pricing, 2026

### C14. OpenAI — current lineup

Per 1M tokens, **standard** tier, short context ([platform.openai.com/docs/pricing](https://platform.openai.com/docs/pricing)):

| Model | Input | Cached input | Cache write | Output |
|---|---|---|---|---|
| `gpt-6-astra` | $10.00 | $1.00 | $12.50 | $50.00 |
| `gpt-5.6-sol` | $4.00 | $0.40 | $5.00 | $20.00 |
| `gpt-5.6-terra` | $2.00 | $0.20 | $2.50 | $12.00 |
| **`gpt-5.6-luna`** (cheap tier) | **$0.20** | **$0.02** | $0.25 | **$1.20** |

- **Batch API: 50% discount** (the published batch table is exactly half of standard).
- **Fast mode** (formerly Priority) is **2× standard**. Long-context pricing is 2× short-context.
- Regional processing / data residency endpoints carry a **10% uplift** for models released on/after 5 Mar 2026.
- `gpt-5.6-sol` promotional pricing runs at least through 21 Nov 2026.
- Fine-tuning is being **wound down** — closed to new users.

### C15. Anthropic — current lineup

Per 1M tokens ([platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)):

| Model | Input | 5m cache write | 1h cache write | Cache read | Output |
|---|---|---|---|---|---|
| Claude Fable 5.1 | $10.00 | $12.50 | — | $0.25 | $50.00 |
| Claude Opus 5 | $5.00 | $6.25 | $10.00 | $0.50 | $25.00 |
| Claude Sonnet 5 | $2.00 | $2.50 | $4.00 | $0.20 | $10.00 |
| **Claude Haiku 4.5** (cheap tier) | **$1.00** | $1.25 | $2.00 | **$0.10** | **$5.00** |

- **Batch API: 50% discount** on both input and output (Haiku 4.5 → $0.50/$2.50). Combinable with prompt caching.
- Sonnet 5's $2/$10 introductory pricing is now **permanent** — the planned 1 Sep 2026 rise to $3/$15 was cancelled.
- ⚠️ **Tokenizer change:** Claude 4.7 and later use a new tokenizer producing **~30% more tokens for the same text**.
  Budget accordingly — a Claude 5-series quote is not directly comparable token-for-token with a Sonnet 4.6 quote.
- Note there is **no Haiku 5** yet; Haiku 4.5 remains the cheap tier.

### C16. Google Gemini

Per 1M tokens, paid tier ([ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)):

| Model | Input | Output | Context caching |
|---|---|---|---|
| **Gemini 3.1 Flash-Lite** | **$0.25** (text/image/video), $0.50 (audio) | **$1.50** | $0.025 |
| **Gemini 3.5 Flash-Lite** | **$0.30** (all modalities) | **$2.50** | $0.03 |
| Gemini 3.8 / 3.7 / 3.6 Flash | $0.75 → **$1.50 from 1 Jan 2027** | $3.75 → **$7.50 from 1 Jan 2027** | $0.075 |

- **Batch: 50% discount.** Flex tier is also 50%; Priority is ~1.8×.
- ⚠️ **The Flash tiers double on 1 January 2027.** Flash-Lite pricing carries no such published sunset. If you quote a
  12-month budget on Gemini Flash, it must step up in January.
- **Free tier still exists**, limited to Flash and Flash-Lite families (Pro models removed from free tier in April 2026).
  ⚠️ Google **no longer publishes a static free-tier rate table** — limits are visible only in AI Studio per project.
  Independent trackers put Flash-Lite at ~15 RPM / ~250K TPM / ~1,000–1,500 RPD; treat as directional, not contractual.
- Context caching carries an additional **storage** fee of $1.00 per 1M tokens per hour, which makes explicit caching
  uneconomic for short system prompts.

### C17. Training and retention — the part that matters for regulated data

| | Trained on by default? | Default retention | ZDR available? | Sales contact needed? |
|---|---|---|---|---|
| **OpenAI API** | **No** (opt-in only) | **30 days** abuse-monitoring logs | **Yes**, on eligible endpoints | **Yes — prior approval required** |
| **Anthropic API** | **No** (Commercial Terms) | **30 days**, auto-deleted | **Yes** | **Yes — contact sales, per-organization** |
| **Google Gemini API — paid** | **No** | not separately published ⚠️ | via Vertex/Enterprise ⚠️ | ⚠️ |
| **Google Gemini API — free tier** | **YES** — "Used to improve our products: Yes" | — | No | — |

**The single most important line in this whole report for a regulated client: do not put client data through the Gemini
free tier.** Google's own pricing table states free-tier content *is* used to improve their products; paid tier is not.
The free tier is for prototyping with synthetic data only.

Further detail:

- **OpenAI:** ZDR forces `store=false` on `/v1/responses` and `/v1/chat/completions`. **Not available** for Conversations,
  Assistants, Threads, Vector Stores, Files, fine-tuning, Batches or Evals — those retain until deleted. So a ZDR design
  must use stateless chat/responses calls only. Data residency is set **at project creation** and cannot be added later.
- **Anthropic:** ZDR is enabled **per organization** and does not extend automatically to other orgs on the same account.
  ⚠️ **Covered Models** (Fable 5/5.1, Mythos 5/5.1) **require 30-day retention and cannot use ZDR**; requests from a
  ZDR org return `400 invalid_request_error`. Sonnet 5 and Haiku 4.5 are not Covered Models, so ZDR is available for
  the tiers you'd actually use. Safety-flagged content may be retained up to 2 years (7 years for classifier scores).
- For a 1–3 person agency, ZDR approval from either vendor is realistically out of reach — both require a compliance
  justification and a sales conversation. **Plan on the 30-day default retention and disclose it**, rather than promising
  the client ZDR you cannot obtain.

### C18. Hebrew quality — concrete numbers

From the community [Hebrew LLM leaderboard](https://huggingface.co/datasets/hebrew-llm-leaderboard/chat-results/viewer)
(higher is better):

| Model | Nikud | Summary (pairwise) | Translation | Trivia | Winograd |
|---|---|---|---|---|---|
| gemini-3-flash-preview | **88.4** | 49.7 | **50.7** | 86.4 | 94.6 |
| gemini-3-pro-preview | 87.6 | 51.8 | 51.2 | **86.7** | **96.0** |
| gpt-5.1 | 80.5 | **66.0** | 44.2 | 81.7 | 91.0 |
| gemini-2.5-flash | 79.5 | 46.9 | 35.0 | 76.4 | 86.0 |
| gpt-4o | 74.8 | 33.7 | 32.0 | 77.1 | 89.2 |
| **gemini-2.5-flash-lite** | **70.7** | 43.0 | 25.0 | 61.8 | 80.9 |
| **claude-haiku-4.5** | 62.5 | 44.0 | **13.7** | 52.8 | 76.3 |
| **gpt-4o-mini** | 50.8 | 23.9 | 11.8 | 54.8 | 77.3 |
| **gpt-5-nano** | **14.6** | 31.0 | 25.0 | 60.5 | 77.7 |

Cross-checked against [AlephBench](https://huggingface.co/datasets/HebArabNlpProject/AlephBench) (snapshot 11 May 2026,
11 tasks): `gemini-2.5-flash` leads at 88.8, `gemma-4-31b-it` 88.1, `DictaLM-3.0-24B-Thinking` 85.2, `gpt-oss-120b` 84.2.

**Reading this for your use case:**

- **Yes, small/cheap models are notably worse in Hebrew — but not uniformly.** Google's cheap tier degrades gracefully;
  OpenAI's cheap tier falls off a cliff. `gpt-5-nano` at 14.6 Nikud is not a marginal gap, it is a different quality class.
- **Classification** (your step b) is the most forgiving task — it needs comprehension, not generation. Any of the
  cheap tiers will probably handle "is this a claim, a policy question, or scheduling?" acceptably.
- **Drafting business replies in Hebrew** (your step c) is the demanding one. It needs correct morphology, register and
  gender agreement. Here the cheap OpenAI tier is a real risk, and Claude Haiku 4.5's translation score of 13.7 is a
  warning sign for Hebrew generation quality specifically.
- **Practical recommendation: split the models.** Cheap tier for classification/routing, a mid tier for Hebrew draft
  generation. Given the leaderboard, Gemini Flash-Lite for classification and Gemini Flash (or `gpt-5.1`-class) for
  drafting is the best quality-per-shekel shape. **Note `gpt-5.1` has the best Hebrew summarisation score on the board
  (66.0) by a wide margin** — worth testing for the drafting step.
- ⚠️ **Major caveat: the leaderboard lags the market.** It benchmarks `gpt-5-nano`, `gpt-5.1`, `gemini-2.5-*` and
  `gemini-3-*-preview` — *not* the current `gpt-5.6-luna/terra/sol`, `gpt-6-astra`, `gemini-3.5/3.8`, or `Sonnet 5`.
  Treat it as evidence about **vendor tiers and trend**, not about the specific model IDs you will deploy. **Run your own
  eval on 50–100 real Hebrew messages before committing.** That eval costs a few dollars and is the highest-value
  hour of work in this project.
- **Hebrew tokenisation inflates cost.** Hebrew consumes meaningfully more tokens per character than English in BPE
  tokenizers. The 600/250 token estimate should be validated against real Hebrew traffic; if it is an English-derived
  estimate, expect actuals to run higher.

---

## D. Speech-to-text for Hebrew voice notes

### D19–D22. Pricing and measured Hebrew accuracy, together

The decisive source is the [ivrit.ai Hebrew Transcription Leaderboard `benchmark.csv`](https://huggingface.co/spaces/ivrit-ai/hebrew-transcription-leaderboard/blob/main/benchmark.csv),
which includes an **`eval-whatsapp`** split — literally Hebrew WhatsApp voice notes. **WER, lower is better:**

| Engine / model | Price | eval-d1 | **eval-whatsapp** | saspeech | fleurs/he | kan |
|---|---|---|---|---|---|---|
| ivrit-ai whisper-large-v3-**turbo**-ct2-20250403 | self-host | 0.055 | **0.061** | 0.074 | 0.208 | 0.100 |
| ivrit-ai whisper-large-v3-turbo-ct2-20250513 | self-host | 0.053 | **0.071** | 0.066 | 0.181 | 0.082 |
| ivrit-ai whisper-large-v3-ct2-20250513 | self-host | **0.051** | 0.072 | 0.064 | 0.174 | 0.081 |
| **Soniox `stt`** | **$0.10/hr async, $0.12/hr RT** | 0.048 | **0.090** | 0.065 | 0.177 | 0.114 |
| Amazon Transcribe (batch) | — | 0.066 | 0.104 | 0.085 | 0.230 | 0.090 |
| **Deepgram Nova-3** | ⚠️ ~$0.26/hr batch | 0.067 | 0.120 | 0.102 | 0.233 | 0.210 |
| **OpenAI `gpt-4o-transcribe`** | **$0.006/min ($0.36/hr)** | 0.073 | 0.126 | 0.109 | 0.210 | 0.394 |
| Whisper large-v3-turbo (vanilla) | — | 0.084 | 0.128 | 0.104 | 0.289 | 0.156 |
| Whisper large-v3 (vanilla) | — | 0.098 | 0.132 | 0.094 | 0.262 | 0.134 |
| **OpenAI `gpt-4o-mini-transcribe`** | **$0.003/min ($0.18/hr)** | 0.090 | 0.158 | 0.150 | 0.300 | 0.468 |
| **ElevenLabs Scribe v1** | ⚠️ v2 is $0.22/hr | 0.200 | **0.264** | 0.068 | 0.181 | 0.109 |
| **Google Cloud Speech** | $0.016/min ($0.96/hr) | 0.211 | **0.352** | 0.189 | 0.385 | 0.292 |

Additional current rates not on the leaderboard:

- **OpenAI:** `gpt-transcribe` $0.0045/min; `gpt-4o-transcribe` $0.006/min; `gpt-4o-mini-transcribe` $0.003/min;
  `gpt-live-transcribe` / `gpt-realtime-whisper` $0.017/min (streaming).
- **Google Cloud STT v2:** $0.016/min standard (0–500k min/mo); **dynamic batch $0.003/min**. **V1** has a 60 min/month
  free tier; the **v2 table shows no free tier**.
- **AssemblyAI:** Universal-2 $0.15/hr, Universal-3.5 Pro $0.21/hr async, Universal-Streaming $0.15/hr. Hebrew is
  supported. ⚠️ Not on the ivrit.ai leaderboard, so Hebrew accuracy is unmeasured here.
- **ElevenLabs:** Scribe v2 $0.22/hr batch, Scribe v2 Realtime $0.39/hr.

**Conclusions:**

- **Google Cloud Speech is disqualified for Hebrew.** 0.352 WER on WhatsApp audio is roughly one word in three wrong —
  and it is also the most expensive hosted option in the table. Do not use it.
- **ElevenLabs Scribe is disqualified on this evidence** (0.264 on WhatsApp audio), though ⚠️ only **v1** was
  benchmarked and v2 is current — this may have improved.
- **Soniox is the standout hosted option: best-in-class Hebrew accuracy *and* the cheapest hosted price** ($0.10/hr
  async vs OpenAI's $0.36/hr, at 0.090 vs 0.126 WER). This is the recommendation.
- **OpenAI's transcription models are mediocre at Hebrew** and `gpt-4o-mini-transcribe` is notably worse (0.158).

### D21. ivrit.ai — active, best-in-class, self-host only

- **Still active in 2026.** The HF org's leaderboard Space was updated within the last week as of this research;
  `benchmark.csv` was last changed ~3 months ago.
- **Models published** (Apache-2.0, Hebrew fine-tunes of Whisper): `ivrit-ai/whisper-large-v3`,
  `ivrit-ai/whisper-large-v3-turbo`, plus CTranslate2 builds `whisper-large-v3-ct2` and `whisper-large-v3-turbo-ct2`.
  Latest weights dated **2025-05-13**. ⚠️ **No newer model release found in 2026** — the project's model output appears
  to have plateaued, though the benchmarking effort is live.
- **No official hosted API.** ivrit.ai's own API page directs you to self-host, typically via their RunPod serverless
  template (`ivrit-ai/runpod-serverless`), using the `ivrit` Python package. Their free web services explicitly prohibit
  automated API access. Diarization is available via the `stable-whisper` core engine.
- **Cost:** ivrit.ai states RunPod serverless comes in at **~$0.03 per transcribed hour**. ⚠️ Their README's
  "$0.00016/second" worker figure is dated **1 August 2024** and should be re-checked against current RunPod pricing.
- **Accuracy vs Whisper:** decisively better. On WhatsApp audio, ivrit.ai turbo scores **0.061–0.071** vs vanilla
  `large-v3-turbo` at **0.128** — roughly **half the error rate**. Against hosted APIs it beats everything including Soniox.
- **Language detection is degraded** by the fine-tuning; you must explicitly set the language token to Hebrew.

**Verdict on ivrit.ai for this client:** technically the best Hebrew accuracy available, and effectively free at this
volume — but it means owning a GPU serverless deployment, cold starts, and model updates for a workload of **one audio
hour per month**. The accuracy delta over Soniox (0.071 vs 0.090 WER) is real but small; the operational delta is large.
**Start on Soniox; keep ivrit.ai as the escalation path if transcription quality becomes the binding constraint.**

---

## E. Cost model

### Assumptions (as specified)

- 3,000 inbound WhatsApp messages/month, each LLM-classified at **600 input / 250 output tokens**
  → **1.8M input tokens, 0.75M output tokens per month**
- 80 Hebrew voice notes/month × 45 s = 3,600 s = **exactly 60 minutes = 1.0 audio hour/month**
- 150 proactive **utility** template messages/month to Israeli numbers
- Replies: modelled at 3,000/month (one per inbound), with three routing scenarios

### E1. LLM classification cost

`cost = (1.8 × input_rate) + (0.75 × output_rate)`

| Model | Input $/M | Output $/M | Input | Output | **Monthly** |
|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite | 0.25 | 1.50 | 1.8×0.25 = $0.45 | 0.75×1.50 = $1.13 | **$1.58** |
| gpt-5.6-luna | 0.20 | 1.20 | $0.36 | $0.90 | **$1.26** |
| Gemini 3.5 Flash-Lite | 0.30 | 2.50 | $0.54 | $1.88 | **$2.42** |
| Gemini 3.8 Flash | 0.75 | 3.75 | $1.35 | $2.81 | **$4.16** ¹ |
| Claude Haiku 4.5 | 1.00 | 5.00 | $1.80 | $3.75 | **$5.55** |
| Claude Sonnet 5 | 2.00 | 10.00 | $3.60 | $7.50 | **$11.10** |
| gpt-5.6-terra | 2.00 | 12.00 | $3.60 | $9.00 | **$12.60** |
| gpt-5.6-sol | 4.00 | 20.00 | $7.20 | $15.00 | **$22.20** |

¹ rises to **$8.33/month** on 1 Jan 2027 when Flash pricing doubles.

**With prompt caching** (assume 400 of the 600 input tokens are a stable system prompt → 1.2M cached-read + 0.6M fresh):

- gpt-5.6-luna: (1.2 × 0.02) + (0.6 × 0.20) + 0.90 = 0.024 + 0.12 + 0.90 = **$1.04**
- Claude Haiku 4.5: (1.2 × 0.10) + (0.6 × 1.00) + 3.75 = 0.12 + 0.60 + 3.75 = **$4.47**

Caching saves cents at this scale. ⚠️ Gemini explicit caching is not worth modelling here — it carries a $1.00/M-tokens-
per-hour storage fee and minimum cacheable token thresholds that a 400-token prompt won't meet. **Batch API (50% off) is
not applicable** to the interactive classify-and-draft path, though it could apply to generating the 150 proactive messages.

### E2. Speech-to-text cost (1.0 audio hour/month)

| Provider | Rate | **Monthly** | WhatsApp-Hebrew WER |
|---|---|---|---|
| ivrit.ai self-host (RunPod) | ~$0.03/hr | **~$0.03** ⚠️ + idle/cold-start | **0.061–0.071** |
| **Soniox async** | $0.10/hr | **$0.10** | **0.090** |
| AssemblyAI Universal-2 | $0.15/hr | $0.15 | unmeasured |
| Google STT v2 dynamic batch | $0.003/min | $0.18 | 0.352 |
| gpt-4o-mini-transcribe | $0.003/min | $0.18 | 0.158 |
| AssemblyAI Universal-3.5 Pro | $0.21/hr | $0.21 | unmeasured |
| ElevenLabs Scribe v2 | $0.22/hr | $0.22 | (v1: 0.264) |
| Deepgram Nova-3 | ~$0.26/hr ⚠️ | $0.26 | 0.120 |
| gpt-4o-transcribe | $0.006/min | $0.36 | 0.126 |
| Google STT v2 standard | $0.016/min | $0.96 | 0.352 |

**Every option costs under $1/month.** STT price is irrelevant at this volume — **choose purely on Hebrew accuracy.**
That points at Soniox (best hosted) or ivrit.ai (best overall, self-hosted).

### E3. Meta message fees

**Proactive utility templates** (sent outside any CSW — true for 6/12/18-month check-ins):

    150 × $0.0053 = $0.795 → $0.80/month

**Inbound messages:** 3,000 × $0 = **$0.00** (Meta never charges inbound).

**Replies** — three scenarios, all identical today, sharply different from 1 Oct 2026:

| Scenario | ≤30 Sep 2026 | From 1 Oct 2026 |
|---|---|---|
| All 3,000 replies sent via Cloud API | $0.00 | (3,000 − 1,000 free) × $0.0053 = 2,000 × 0.0053 = **$10.60** |
| Half (1,500) via API, half typed on phone | $0.00 | (1,500 − 1,000) × $0.0053 = 500 × 0.0053 = **$2.65** |
| **All replies approved & sent from the phone app** | $0.00 | **$0.00** |

**Meta subtotal:** **$0.80/month today**; **$0.80 – $11.40/month** from 1 October depending on reply routing.

### E4. Transport layer

| Option | Monthly |
|---|---|
| Direct Cloud API | **$0** (but see Coexistence Tech-Provider constraint, §A6) |
| 360dialog Regular | **€49** per number |
| Twilio | $0.005 × (3,000 in + 3,000 out + 150 templates) = 0.005 × 6,150 = **$30.75** |
| Chatwoot CE self-hosted (optional inbox) | $0 licence + VPS |
| App/VPS hosting | ⚠️ **~$10–25** (4 GB VPS; Hetzner low end, DigitalOcean high end) |

### E5. Full combinations — total monthly cost

Assuming **replies typed on the phone under Coexistence** (the recommended design), plus a $15 VPS:

| # | Combination | Meta | Transport | LLM | STT | Hosting | **Total (today)** | **Total (post-1 Oct, worst case²)** |
|---|---|---|---|---|---|---|---|---|
| **1** | **Direct Cloud API + Gemini 3.5 Flash-Lite + Soniox** | $0.80 | $0 | $2.42 | $0.10 | $15 | **≈ $18.32** | **≈ $28.92** |
| 2 | Direct Cloud API + gpt-5.6-luna + Soniox | $0.80 | $0 | $1.26 | $0.10 | $15 | ≈ $17.16 | ≈ $27.76 |
| 3 | Direct Cloud API + Claude Haiku 4.5 + Soniox | $0.80 | $0 | $5.55 | $0.10 | $15 | ≈ $21.45 | ≈ $32.05 |
| 4 | Direct Cloud API + Gemini 3.8 Flash + ivrit.ai self-host | $0.80 | $0 | $4.16 | ~$3³ | $15 | ≈ $22.96 | ≈ $33.56 |
| **5** | **360dialog + Gemini 3.5 Flash-Lite + Soniox** | $0.80 | **€49** | $2.42 | $0.10 | $15 | **≈ $18.32 + €49** | **≈ $28.92 + €49** |
| 6 | Twilio + Gemini 3.5 Flash-Lite + Soniox | $0.80 | $30.75 | $2.42 | $0.10 | $15 | ≈ $49.07 | ≈ $59.67 |
| 7 | Split-model (Flash-Lite classify + gpt-5.1-class draft) ⁴ | $0.80 | $0 | ~$8–12 | $0.10 | $15 | ≈ $24–28 | ≈ $35–39 |

² worst case = all 3,000 replies sent via Cloud API (+$10.60). Routing approved replies through the phone app keeps the
"today" column valid indefinitely.
³ ivrit.ai compute is ~$0.03/hr but serverless cold starts and minimum billing dominate at 1 hr/month; budgeted conservatively.
⁴ classification on Flash-Lite (1.8M in / small out) plus drafting on a mid-tier model for the subset of messages that
need a drafted reply. Exact figure depends on what fraction of the 3,000 get a draft.

**Headline: the realistic all-in cost is roughly $18–30/month direct, or €49 + $18–30/month via 360dialog.**
The LLM and STT — the parts that feel expensive — total **under $3/month combined**. The cost drivers are, in order:
(1) any BSP platform fee, (2) VPS hosting, (3) Meta service messages after 1 October. Twilio nearly triples the direct
bill purely on its inbound fee.

---

## What I could NOT verify

1. **Meta's own Israel rate-card row.** The official card is a JS widget plus downloadable files I could not fetch.
   $0.0353 marketing / $0.0053 utility / $0.0053 auth / $0.0053 service comes from two independent BSP mirrors that
   agree exactly (Wabery, SleekFlow), cross-checked against Meta's confirmation that Israel is a standalone market and
   is *not* in the 1 Oct 2026 rate-change list. **Verify on the live card before billing a client.**
2. **Coexistence availability in Israel specifically.** Meta publishes no country list. Confirmed GA as a feature;
   Israeli eligibility is **unconfirmed**. The only test is running Embedded Signup against the real number.
3. **Business verification and display-name approval timelines.** Meta publishes **no SLA**. The "1–7 days" /
   "minutes to hours" figures are third-party reports, not commitments.
4. **Wati's current entry price.** Sources disagree: $39/mo annual ($49 monthly) vs $59/mo annual ($69 monthly), the
   latter dated 10 Sep 2026. I did not fetch Wati's own pricing page. The ~20% Meta markup is consistently reported.
5. **EUR/USD rate** for converting 360dialog's €49. Left in euros throughout.
6. **Deepgram Nova-3 pricing** (~$0.26/hr batch, ~$0.46/hr streaming) comes from AssemblyAI's comparison page — a
   competitor. Not fetched from Deepgram directly.
7. **ElevenLabs Scribe v2 Hebrew accuracy.** Only **Scribe v1** appears on the ivrit.ai leaderboard (0.264 WER on
   WhatsApp audio). v2 is current and may be substantially better. Its $0.22/hr price *is* confirmed from ElevenLabs.
8. **AssemblyAI Hebrew accuracy.** They advertise Hebrew support and pricing is confirmed, but they are absent from the
   ivrit.ai leaderboard, so there is no independent Hebrew WER figure.
9. **Current RunPod pricing for ivrit.ai self-hosting.** The "$0.00016/second" worker figure in their README is dated
   **1 August 2024**. ivrit.ai's "~$0.03 per transcribed hour" is their own current claim, unverified against RunPod.
10. **Hebrew benchmarks for the models you would actually deploy.** Both leaderboards predate `gpt-5.6-*`, `gpt-6-astra`,
    `gemini-3.5/3.8-*` and `Sonnet 5`. The tier-level conclusion (cheap OpenAI weak in Hebrew, cheap Google strong) is
    well supported; per-model-ID claims for the current lineup are **not**. Run your own eval.
11. **Google Gemini API default retention period and ZDR availability.** The pricing page cleanly confirms the
    training question (free tier: yes; paid tier: no), but I did not locate a Gemini-API-specific retention window or a
    documented ZDR offering comparable to OpenAI's and Anthropic's. Likely requires Vertex AI / Google Cloud enterprise
    terms. **Treat as an open question for any regulated deployment.**
12. **Hebrew token inflation.** The 600/250 token assumption was taken as given and not measured against real Hebrew
    text. Hebrew typically consumes more tokens per character than English; actual LLM costs may run above the table.
13. **Whether Israeli insurance/pension supervisory rules impose specific constraints** on processing client
    communications through non-Israeli cloud LLM providers. Out of scope for this research and a question for the
    client's compliance counsel — but it may override every cost conclusion above.

---

## Recommended configuration

**Transport:** WhatsApp Cloud API via **Coexistence** so the owner keeps normal WhatsApp on his phone. Verify Israeli
eligibility first. Because Coexistence requires Solution Partner / Tech Provider access with Embedded Signup v4, either
onboard through **360dialog (€49/number/month, zero markup)** or register as a Tech Provider yourself.

**Design for the October pricing change now:** route approved replies back through the owner's phone app rather than the
Cloud API wherever possible. Meta does not charge for app-sent messages, and this alone is the difference between
$0.80 and $11.40/month on Meta fees — and it scales with volume.

**Internal channel:** Telegram Bot API for the two back-office staff. Free, supports groups, supports voice notes,
no 24-hour window.

**LLM:** Gemini Flash-Lite for classification; a mid tier (Gemini Flash or a GPT-5.1-class model) for Hebrew drafting.
**Paid tier only — never the Gemini free tier with client data.** Run a 50–100 message Hebrew eval before committing.

**STT:** Soniox at $0.10/hr — best measured Hebrew accuracy among hosted APIs and the cheapest. Keep ivrit.ai
self-hosting as the escalation path.

**Do not:** use Baileys/whatsapp-web.js/wppconnect on the owner's number; use Google Cloud Speech for Hebrew; use Twilio
for this inbound-heavy workload; or promise the client Zero Data Retention that a business this size will not be granted.

**Expect ~$18–30/month all-in direct, or that plus €49 via 360dialog** — plus your build and maintenance time, which
will dominate the total cost of ownership by orders of magnitude.
