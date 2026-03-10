# ARIA Health Master Plan
*AI-powered therapy and life coaching platform*
*Repo: gummihurdal/katherina-trader (until dedicated repo created)*
*Server: EX63 @ 157.180.104.136*

---

## Vision
A three-tier mental health and life coaching platform combining AI sessions, licensed professionals, and corporate wellness — running largely autonomously with ML doing most of the work.

---

## The Three Tiers

```
Tier 1 — AI Aria          CHF 20-35/session    (fully automated, 90% margin)
Tier 2 — Licensed Pros    CHF 80-150/session   (platform fee 15-20%)
Tier 3 — Corporate Plans  CHF 20/employee/mo   (bulk licensing)
```

---

## ARIA — The AI Persona

### Appearance
- Photorealistic AI avatar generated with Stable Diffusion
- Consistent face, expressions, eye contact across all interactions
- Professional warm office setting — bookshelf, plants, soft lighting
- Real-time facial expressions — nods, smiles, shows concern
- NOT a static image — feels alive

### Voice
- ElevenLabs ultra-realistic conversational voice
- Warm, calm, therapist tone
- Natural pauses and hesitation
- Remembers your name and full history

### Personality
- Empathetic, non-judgmental, warm
- Asks the right questions
- Never rushes
- Knows when to refer to a human professional
- Transparent about being AI — builds trust not deception

### Specialties
**As psychiatrist knowledge base:**
- CBT (Cognitive Behavioral Therapy)
- DBT (Dialectical Behavior Therapy)
- ACT (Acceptance and Commitment Therapy)
- Anxiety and stress management
- Depression support (non-clinical)
- Sleep hygiene
- Trauma-informed responses
- Mindfulness and meditation
- Personality frameworks (Big 5, MBTI, attachment styles)

**As life coach:**
- Goal setting and accountability
- Career transitions
- Confidence building
- Habit formation (Atomic Habits framework)
- Productivity systems
- Work-life balance
- Relationship coaching
- High performance psychology

### Legal Boundaries (non-negotiable)
| Aria CAN do | Aria CANNOT do |
|---|---|
| Emotional support | Diagnose mental illness |
| CBT/DBT/ACT exercises | Prescribe medication |
| Life coaching | Replace clinical therapy |
| Stress management | Handle active crisis alone |
| Goal setting | Provide medical advice |

Every session disclaimer: *"I'm an AI life coach — not a licensed therapist. For clinical concerns please consult a professional."*

---

## Training Data

### Tier 1 — Books (highest quality)
**CBT / Therapy:**
- Cognitive Behavior Therapy — Aaron Beck
- Feeling Good — David Burns
- Mind Over Mood — Greenberger & Padesky
- The Body Keeps the Score — Bessel van der Kolk
- DBT Skills Training Manual — Marsha Linehan
- Acceptance and Commitment Therapy — Steven Hayes

**Life Coaching:**
- The Life Coaching Handbook — Curly Martin
- Co-Active Coaching — Kimsey-House
- The Coaching Habit — Michael Bungay Stanier
- Unlimited Power — Tony Robbins
- Atomic Habits — James Clear
- The 7 Habits — Stephen Covey

**Psychology:**
- Man's Search for Meaning — Viktor Frankl
- Emotional Intelligence — Daniel Goleman
- The Power of Now — Eckhart Tolle
- Thinking Fast and Slow — Daniel Kahneman

**Source:** Project Gutenberg, Open Library (archive.org), PDFs
**Volume:** ~25M words
**Cost:** $0

### Tier 2 — Academic Datasets (free)
- ESConv — Emotional Support Conversation dataset
- AnnoMI — Motivational interviewing transcripts
- EmpatheticDialogues — Facebook AI, 25,000 conversations
- PsyQA — Psychology Q&A dataset
- IEMOCAP — Emotional conversation dataset

**Volume:** ~2M words
**Cost:** $0

### Tier 3 — YouTube Transcripts
**Channels:**
- Therapy in a Nutshell (Emma McAdam, LMFT)
- Kati Morton (licensed therapist)
- Tony Robbins (live coaching sessions)
- Brendon Burchard (high performance coaching)
- Jay Shetty (life coaching conversations)
- Huberman Lab (neuroscience of behavior)
- TED Talks Psychology

**Download method:**
```bash
pip install yt-dlp
yt-dlp --write-auto-sub --skip-download [channel_url]
```
**Volume:** ~5M words from 500 videos
**Cost:** $0

### Tier 4 — Synthetic Data (highest ROI)
Generate 10,000 realistic therapy dialogues via Claude API:
```
"Generate a realistic 20-minute CBT therapy session 
between a therapist and a client with social anxiety. 
Include therapist techniques, client resistance, 
and the breakthrough moment."
```
**Volume:** ~10M words
**Cost:** ~$50 Claude API

### Total Training Data
| Source | Volume | Cost |
|---|---|---|
| Books | 25M words | $0 |
| Academic datasets | 2M words | $0 |
| YouTube transcripts | 5M words | $0 |
| Synthetic sessions | 10M words | $50 |
| **Total** | **42M words** | **$50** |

---

## ML Training Plan (Vast.ai RTX 4090 @ $0.28/hr)

| Model | Purpose | Time | Cost |
|---|---|---|---|
| Mistral 7B fine-tune (therapy) | Core Aria brain | 12 hours | $3.36 |
| Personality adapter | MBTI/Big5 response tuning | 4 hours | $1.12 |
| Stable Diffusion fine-tune | Aria visual appearance | 6 hours | $1.68 |
| Session quality classifier | Detect bad responses | 2 hours | $0.56 |
| **Total** | | **24 hours** | **$6.72** |

---

## Continuous Learning Architecture

### Daily (automated on EX63)
```python
sources = [
    "pubmed.gov",           # latest psychology research
    "psychologytoday.com",  # therapy articles
    "apa.org",              # APA publications
    "ncbi.nlm.nih.gov",     # medical research
]
# Scrape → Clean → Summarize → Add to knowledge base
```
Cost: $0

### Weekly (Vast.ai)
- Batch all session feedback signals
- Quick retrain incorporating new learnings
- Deploy updated model to EX63
Cost: ~$0.28/week

### Monthly (Vast.ai + human review)
- Deep retrain with all new data
- Freelance psychologist reviews 20 session transcripts ($50-100)
- A/B test new vs old model
- Deploy winner
Cost: ~$1.68 compute + $50-100 human review

### Version Control
```
/data/aria/models/
  aria_v1.0_2026-04-01.zip
  aria_v1.1_2026-04-08.zip
  aria_v2.0_2026-05-01.zip
```
Full rollback capability at any time.

---

## Platform Features

### For Users
- AI sessions (Aria) 24/7 — instant, no waitlist
- Browse licensed professionals by specialty
- Filter: language, price, availability, therapeutic approach
- Instant booking with calendar integration
- Secure video room (built in — no Zoom needed)
- Full session history and progress tracking
- Mood journal between sessions
- Crisis button → immediate resources + emergency contacts
- Anonymous option available
- Mobile app (PWA — works on all devices)

### For Licensed Professionals
- Professional profile page with verification badge
- Calendar sync (Google, Outlook)
- Built-in secure video room
- Client session notes (GDPR compliant)
- Payment dashboard — automatic payouts
- Analytics: session completion, client retention rates
- Aria referral feed — complex clients escalated from AI
- No marketing needed — platform provides clients

### For Corporates
- Employee wellness dashboard
- Usage analytics (anonymous/aggregated)
- Bulk session credits
- Custom Aria persona with company branding
- Mental health trend reporting for HR
- Invoicing and billing management

---

## Professional Verification System
```
Professional applies
→ Upload license/credentials
→ Automated check against official registries
   (Swiss Psychologists Federation, BACP UK, APA USA)
→ Background check (premium verification option)
→ Video onboarding interview (AI-conducted by Aria)
→ Approved → profile goes live
→ Annual renewal check
```

---

## Tech Stack

| Component | Tool | Monthly Cost |
|---|---|---|
| Frontend | React (existing skills) | $0 |
| Backend | FastAPI on EX63 | $0 |
| Database | Supabase | $0-25 |
| Auth | Supabase Auth | $0 |
| Video sessions | Daily.co API | $0-100 |
| Payments | Stripe Connect | 2.9% + CHF 0.30 |
| AI Brain | Fine-tuned Mistral 7B on EX63 | $0 after training |
| Avatar | HeyGen real-time | $29 |
| Voice | ElevenLabs | $22 |
| Email | Resend.com | $0-20 |
| Calendar | Custom or Calendly API | $0-12 |
| **Total** | | **~$150-200/mo** |

---

## Revenue Model

| Stream | Unit | At 100 users | At 1,000 users |
|---|---|---|---|
| AI sessions (90% margin) | CHF 30/session | CHF 2,700 | CHF 27,000 |
| Pro session fees (15%) | CHF 15/session | CHF 1,500 | CHF 15,000 |
| Pro subscriptions | CHF 99/mo | CHF 990 | CHF 9,900 |
| Corporate plans | CHF 20/employee | CHF 2,000 | CHF 20,000 |
| **Total** | | **CHF 7,190/mo** | **CHF 71,900/mo** |

Break even: 4 monthly subscribers.

---

## Social Media Strategy

Aria has her own Instagram/TikTok/Facebook:
- Daily mental health tips
- "Ask Aria" — answers follower questions publicly
- Guided meditation videos
- "A day in the life of an AI therapist"
- Success stories (anonymized, with consent)
- Drives traffic to session bookings

Same ML infrastructure as GeoQuest ARIA — different personality layer.

---

## Legal Structure

| Risk | Mitigation |
|---|---|
| Aria giving bad advice | Clear AI disclaimer every session |
| Licensed pro malpractice | Pro's own insurance — platform not liable |
| Data privacy (GDPR) | All data encrypted, Swiss servers (EX63) |
| Crisis situations | Mandatory crisis protocol — auto-escalate |
| Financial liability | Stripe holds payments — clear ToS |

**Legal documents needed (one-time ~CHF 500-1,000):**
- Terms of Service with AI disclaimer
- Privacy Policy (GDPR compliant)
- Professional Services Agreement
- User informed consent form
- Crisis protocol policy

---

## Go-To-Market Strategy

### Phase 1 — AI Only (Month 1-2)
- Launch with Aria only
- Free beta for 50 users
- Collect feedback, improve model
- Build reputation and case studies

### Phase 2 — Add Professionals (Month 3-4)
- Recruit 20 licensed therapists/coaches
- 0% commission for first 6 months to attract supply
- Launch paid plans for users
- Target: 100 paying users

### Phase 3 — Corporate (Month 5-6)
- Package for Swiss SMEs (50-500 employees)
- Pitch HR departments directly
- First corporate client = CHF 10,000+/mo
- Target: 3 corporate clients

---

## Competitive Advantage

| Competitor | Weakness | ARIA Health advantage |
|---|---|---|
| BetterHelp | No AI tier, US-focused, expensive | Aria at CHF 30 fills gap |
| Headspace | No human therapists | Full spectrum AI + human |
| Psychology Today | Just a directory | Full practice management |
| Talkspace | US only, expensive | Swiss/European focus |
| Calm | No real sessions | Actual therapy sessions |

**Nobody combines AI + human + corporate in one seamless European platform.**

---

## Platform Name Options
- **ARIA Health** — clean, professional
- **MindBridge** — connects AI to human
- **Therapia** — therapy + AI
- **Innerspace** — psychological feel
- **Haven** — safe space concept

---

## Development Timeline

| Month | Milestone |
|---|---|
| April 2026 | Build core platform (React + FastAPI) |
| May 2026 | Collect training data, train Aria on Vast.ai |
| June 2026 | Beta launch — 50 free users |
| July 2026 | Recruit 20 licensed professionals |
| August 2026 | Paid launch — all three tiers |
| September 2026 | First corporate client pitch |
| December 2026 | 500 users, CHF 15,000/mo revenue |
| 2027 | Expand to Germany, Austria, Netherlands |

---

## Pending Tasks
- [ ] Create dedicated GitHub repo: aria-health
- [ ] Design Aria's visual appearance (Stable Diffusion)
- [ ] Collect training data (books + YouTube + datasets)
- [ ] Generate synthetic sessions via Claude API ($50)
- [ ] Train Aria on Vast.ai (~$7)
- [ ] Build core platform (React + FastAPI)
- [ ] Set up Daily.co video integration
- [ ] Set up Stripe Connect for pro payouts
- [ ] Draft legal documents (find Swiss lawyer)
- [ ] Build professional verification system
- [ ] Beta recruit 50 test users
- [ ] Recruit first 20 licensed professionals
- [ ] Launch social media (Instagram + TikTok)

---

## Monthly Running Costs at Launch
| Item | Cost |
|---|---|
| Hetzner EX63 (shared with KAT + GeoQuest) | €0 additional |
| HeyGen avatar | $29 |
| ElevenLabs voice | $22 |
| Daily.co video | $0-100 |
| Supabase | $0-25 |
| Weekly ML retraining | ~$1.12 |
| Monthly deep retrain | ~$1.68 |
| Human expert review | $50-100 |
| **Total** | **~$150-280/mo** |

---
*Last updated: March 10, 2026*
