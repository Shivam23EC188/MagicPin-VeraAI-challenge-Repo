import time
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

app = FastAPI()

# --- MEMORY STORE ---
contexts = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {}
}

conversations = {}  # conv_id -> state dict
sent_keys = set()
start_time = time.time()

# --- PATTERNS ---
AUTO_PAT = [
    "thank you for contacting", "jaankari ke liye", "bahut-bahut shukriya", 
    "team tak", "automated assistant", "auto reply", "get back to you", 
    "hamari team", "we will revert", "currently unavailable", 
    "received your message", "as soon as possible"
]

NEG_PAT = [
    "nahi", "not interested", "stop", "band karo", "baad mein bol", 
    "not now", "no need", "do not", "don't", "bas karo", "abhi nahi", 
    "no thanks", "later"
]

POS_PAT = [
    "yes", "haan", "theek hai", "thik hai", "ok", "okay", "sure", 
    "go ahead", "kar do", "kardo", "bhejo", "chalega", "bilkul", 
    "sounds good", "perfect", "why not", "done", "kar lo", "whats next", "what's next"
]

ASK_TIME_PAT = [
    "thoda time", "give me time", "baad mein", "busy hoon", 
    "occupied", "thodi der", "after some time"
]

ABUSE_PAT = [
    "stupid", "bakwas", "useless", "shut up", "idiot", "pagal", 
    "chor", "fraud", "damn", "gali", "spam"
]

# --- MODELS ---
class ContextPayload(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str

class TickPayload(BaseModel):
    now: str
    available_triggers: List[str]

class ReplyPayload(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

# --- ENDPOINTS ---

@app.get("/v1/healthz")
def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - start_time),
        "contexts_loaded": {
            "category": len(contexts["category"]),
            "merchant": len(contexts["merchant"]),
            "customer": len(contexts["customer"]),
            "trigger": len(contexts["trigger"])
        }
    }

@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": "MLarper",
        "team_members": ["Shivam"],
        "contact_email": "shivam_23ec188@dtu.ac.in",
        "model": "rule-based deterministic composer (no LLM)",
        "approach": "fact-anchored trigger templates + merchant/category fit + auto-reply detection + intent routing",
        "version": "1.1.0",
        "submitted_at": "2026-09-27T12:00:00Z"
    }

@app.post("/v1/context")
def ingest_context(req: ContextPayload):
    if req.scope not in contexts:
        raise HTTPException(status_code=400, detail="Invalid scope")
    
    current = contexts[req.scope].get(req.context_id)
    if current and current["version"] >= req.version:
        return {"status": "ignored", "reason": "stale version", "accepted": False}
        
    contexts[req.scope][req.context_id] = {
        "version": req.version,
        "payload": req.payload,
        "raw": req.model_dump()
    }
    return {"status": "accepted", "accepted": True}

@app.post("/v1/tick")
def tick(req: TickPayload):
    actions = []
    
    for t_id in req.available_triggers:
        if t_id not in contexts["trigger"]:
            continue
            
        t_data = contexts["trigger"][t_id]["payload"]
        m_id = t_data.get("merchant_id")
        sup_key = t_data.get("suppression_key")
        
        if sup_key in sent_keys:
            continue
            
        m_data = contexts["merchant"].get(m_id, {}).get("payload", {})
        m_identity = m_data.get("identity", {})
        m_name = m_identity.get("name", "your business")
        m_locality = m_identity.get("locality", "")
        category = m_data.get("category_slug", "")
        is_clinical = category in ("dentists", "pharmacies")

        c_id = t_data.get("customer_id")
        c_data = contexts["customer"].get(c_id, {}).get("payload", {}) if c_id else {}
        c_identity = c_data.get("identity", {})
        c_name = c_identity.get("name", "this customer")

        def _readable_id(raw):
            parts = raw.split("_")
            return " ".join(parts[2:]).strip() if len(parts) > 2 else raw.replace("_", " ")
        
        # Deterministic formatting
        kind = t_data.get("kind")
        p = t_data.get("payload", {})
        
        body = f"We noticed an update for {m_name}'s profile ({kind}). Should we optimize it?"
        cta = "Review Optimization"
        
        if kind == "milestone_reached":
            metric_raw = p.get("metric", "metric")
            metric = "reviews" if metric_raw == "review_count" else metric_raw.replace("_", " ")
            now = p.get("value_now", 0)
            target = p.get("milestone_value", 0)
            diff = max(0, target - now)
            if is_clinical:
                body = f"{m_name} is at {now} {metric}, {diff} short of {target}. A quick profile update could help close the gap."
            else:
                body = f"{m_name} ka profile ek naye milestone ke bohot kareeb hai! You currently have {now} {metric}. Just {diff} more to reach {target}. Let's push a quick update to hit the goal."
            cta = "Review Draft Update"
            
        elif kind == "review_theme_emerged":
            theme_raw = p.get("theme", "topic")
            theme = theme_raw.replace("_", " ")
            trend = p.get("trend", "rising")
            count = p.get("occurrences_30d", 0)
            quote = p.get("common_quote", "")
            body = f"{m_name}'s recent reviews mention '{theme}' {count} times in the last 30 days (trend: {trend}). One customer wrote: '{quote}'. Let's address this to build trust."
            cta = "View Details"
            
        elif kind == "regulation_change":
            deadline = p.get("deadline_iso", "soon")
            item = _readable_id(p.get("top_item_id", "regulation"))
            body = f"Compliance update for {m_name}: a new requirement related to '{item}' takes effect by {deadline}. Let's update your profile so customers know you're compliant."
            cta = "Update Profile"

        elif kind == "perf_spike":
            metric = p.get("metric", "metric")
            delta_pct = p.get("delta_pct", 0)
            window = p.get("window", "recent period")
            baseline = p.get("vs_baseline", 0)
            driver = p.get("likely_driver", "").replace("_", " ")
            driver_txt = f", likely driven by {driver}" if driver else ""
            if is_clinical:
                body = f"{m_name}'s {metric} are up {delta_pct*100:.0f}% over the last {window} (baseline ~{baseline}){driver_txt}. Worth reviewing your listing while traffic is up."
            else:
                body = f"Great news, {m_name}! Your {metric} are up {delta_pct*100:.0f}% over the last {window}{driver_txt}. Let's capitalize on it."
            cta = "Boost Now"

        elif kind == "perf_dip":
            metric = p.get("metric", "metric")
            delta_pct = p.get("delta_pct", 0)
            window = p.get("window", "recent period")
            baseline = p.get("vs_baseline", 0)
            body = f"{m_name}'s {metric} are down {abs(delta_pct)*100:.0f}% over the last {window} (baseline ~{baseline}). I've prepared a fix for your listing."
            cta = "Apply Fix"

        elif kind == "festival_upcoming":
            fest = p.get("festival", "the festival")
            date = p.get("date", "")
            date_txt = f" ({date})" if date else ""
            if is_clinical:
                body = f"{fest}{date_txt} is on the way. Updating {m_name}'s hours and available slots now can help patients plan ahead."
            else:
                body = f"{fest}{date_txt} is coming up! Let's update {m_name}'s timings and add a festive offer to attract more customers."
            cta = "View Festive Draft"

        elif kind == "research_digest":
            topic = _readable_id(p.get("top_item_id", ""))
            body = f"A new {category} research update on '{topic}' is relevant to {m_name}. Want me to draft a post referencing it? (I can pull the full citation before we send.)"
            cta = "View Research Draft"

        elif kind == "recall_due":
            service = p.get("service_due", "checkup").replace("_", " ")
            due = p.get("due_date", "soon")
            slots = p.get("available_slots", [])
            slot_txt = slots[0].get("label", "") if slots else ""
            slot_clause = f" I can offer {slot_txt}." if slot_txt else ""
            body = f"{c_name} is due for a {service} by {due} at {m_name}.{slot_clause} Want me to send the reminder?"
            cta = "Send Recall Reminder"

        elif kind == "renewal_due":
            days = p.get("days_remaining", 0)
            plan = p.get("plan", "your")
            amount = p.get("renewal_amount", 0)
            body = f"{m_name}'s {plan} plan renews in {days} days (₹{amount}). Let's make sure your profile is fully optimized before then."
            cta = "Review Before Renewal"

        elif kind == "wedding_package_followup":
            wedding_date = p.get("wedding_date", "")
            days_to = p.get("days_to_wedding", 0)
            next_step = p.get("next_step_window_open", "").replace("_", " ")
            body = f"{c_name}'s wedding is on {wedding_date} ({days_to} days away). The {next_step} window is open — want me to draft a follow-up for {m_name}?"
            cta = "Draft Follow-up"

        elif kind == "curious_ask_due":
            ask = p.get("ask_template", "a quick question").replace("_", " ")
            body = f"Quick one for {m_name}: {ask}? This helps me tailor better offers for your customers."
            cta = "Answer Quick Question"

        elif kind == "winback_eligible":
            days_exp = p.get("days_since_expiry", 0)
            dip = p.get("perf_dip_pct", 0)
            lapsed = p.get("lapsed_customers_added_since_expiry", 0)
            body = f"{m_name}'s offer expired {days_exp} days ago — since then {lapsed} customers have gone lapsed and performance is down {abs(dip)*100:.0f}%. A win-back offer could help recover them."
            cta = "Draft Win-back Offer"

        elif kind == "ipl_match_today":
            match = p.get("match", "")
            venue = p.get("venue", "")
            city = p.get("city", "")
            body = f"{match} is on today at {venue}, {city}. Good night for a match-day offer at {m_name} — want me to draft one?"
            cta = "Draft Match-day Offer"

        elif kind == "active_planning_intent":
            topic = p.get("intent_topic", "").replace("_", " ")
            last_msg = p.get("merchant_last_message", "")
            body = f"You mentioned: \"{last_msg}\" about {topic}. I've drafted next steps for {m_name} — want to see them?"
            cta = "Review Draft"

        elif kind == "seasonal_perf_dip":
            metric = p.get("metric", "metric")
            delta_pct = p.get("delta_pct", 0)
            window = p.get("window", "recent period")
            note = p.get("season_note", "").replace("_", " ")
            body = f"{m_name}'s {metric} are down {abs(delta_pct)*100:.0f}% over the last {window} — this lines up with the usual {note} pattern, so nothing alarming. A quick refresh could still help offset it."
            cta = "Review Refresh Ideas"

        elif kind == "customer_lapsed_hard":
            days_since = p.get("days_since_last_visit", 0)
            focus = p.get("previous_focus", "").replace("_", " ")
            months = p.get("previous_membership_months", 0)
            body = f"{c_name} hasn't visited {m_name} in {days_since} days (was focused on {focus}, {months} months as a member). A tailored win-back message could bring them back."
            cta = "Draft Win-back Message"

        elif kind == "trial_followup":
            trial_date = p.get("trial_date", "")
            options = p.get("next_session_options", [])
            slot_txt = options[0].get("label", "") if options else ""
            slot_clause = f" I can offer {slot_txt} for their next session." if slot_txt else ""
            body = f"{c_name} completed a trial at {m_name} on {trial_date}.{slot_clause} Want me to send it?"
            cta = "Send Next Session Offer"

        elif kind == "supply_alert":
            molecule = p.get("molecule", "")
            batches = ", ".join(p.get("affected_batches", []))
            manufacturer = p.get("manufacturer", "")
            body = f"Supply alert for {m_name}: a recall affects {molecule} batches {batches} from {manufacturer}. Please check your stock."
            cta = "Check Stock"

        elif kind == "chronic_refill_due":
            molecules = ", ".join(p.get("molecule_list", []))
            runs_out_raw = p.get("stock_runs_out_iso", "soon")
            runs_out = runs_out_raw.split("T")[0] if "T" in runs_out_raw else runs_out_raw
            body = f"{c_name}'s regular medicines ({molecules}) are due to run out around {runs_out}. Want me to send a refill reminder from {m_name}?"
            cta = "Send Refill Reminder"

        elif kind == "category_seasonal":
            season = p.get("season", "this season")
            trends = "; ".join(t.replace("_", " ") for t in p.get("trends", [])[:3])
            body = f"Seasonal shift for {m_name}: {trends}. Worth adjusting your shelf focus for {season}."
            cta = "Review Shelf Suggestions"

        elif kind == "gbp_unverified":
            path = p.get("verification_path", "").replace("_", " ")
            uplift = p.get("estimated_uplift_pct", 0)
            body = f"{m_name}'s Google Business Profile isn't verified yet. Verifying via {path} could improve visibility (~{uplift*100:.0f}% estimated uplift)."
            cta = "Start Verification"

        elif kind == "cde_opportunity":
            credits = p.get("credits", 0)
            fee = p.get("fee", "").replace("_", " ")
            body = f"A continuing education opportunity worth {credits} CDE credits is available ({fee}) for {m_name}. Want details?"
            cta = "View CDE Details"

        elif kind == "competitor_opened":
            comp = p.get("competitor_name", "a competitor")
            dist = p.get("distance_km", 0)
            offer = p.get("their_offer", "")
            body = f"{comp} opened {dist} km from {m_name} with '{offer}'. Want me to draft a response offer?"
            cta = "Draft Response Offer"

        elif kind == "dormant_with_vera":
            days = p.get("days_since_last_merchant_message", 0)
            topic = p.get("last_topic", "").replace("_", " ")
            body = f"It's been {days} days since we last spoke about {topic}. Should I check in on where things stand for {m_name}?"
            cta = "Resume Conversation"
            
        sent_keys.add(sup_key)
        
        actions.append({
            "conversation_id": f"conv_{m_id}_{int(time.time())}",
            "merchant_id": m_id,
            "customer_id": t_data.get("customer_id"),
            "send_as": "vera",
            "trigger_id": t_id,
            "template_name": kind,
            "template_params": p,
            "body": body,
            "cta": cta,
            "suppression_key": sup_key,
            "rationale": f"Triggering for {kind} based on local rules."
        })
        
        if len(actions) >= 20:
            break
            
    return {"actions": actions}

def _match_any(patterns, text):
    """Word-boundary match to avoid false positives like 'sure' inside 'not sure'
    or 'ok' inside 'broke'."""
    for pat in patterns:
        if re.search(r"\b" + re.escape(pat) + r"\b", text):
            return True
    return False


ACTION_VARIANTS = [
    "Bilkul. Next step: maine aapke current profile context ke basis par draft ready kiya hai. Main use review ke liye dikha sakti hoon.",
    "Just checking in — the draft based on your current profile is ready whenever you'd like to review it.",
    "Whenever you're ready, the draft is prepared and waiting for your go-ahead."
]


@app.post("/v1/reply")
def reply(req: ReplyPayload):
    cid = req.conversation_id
    if cid not in conversations:
        conversations[cid] = {"turns": 0, "auto_tried": False, "bot_nudges": 0, "mode": "nudge"}
    
    state = conversations[cid]
    state["turns"] += 1
    msg = req.message.lower().strip()
    
    # 1. ABUSE & OFF-TOPIC HANDLING
    if _match_any(ABUSE_PAT, msg):
        if "gst" in msg or "tax" in msg:
            return {
                "action": "send",
                "body": "I am Vera, your local marketing assistant. I cannot file GST, but I am here to help optimize your magicpin profile.",
                "cta": "Continue with Profile",
                "rationale": "Hostile with unrelated task -> redirect to mission."
            }
        return {
            "action": "end",
            "rationale": "Hostile/Abuse intent detected."
        }
        
    # 2. AUTO-REPLY HANDLING
    if _match_any(AUTO_PAT, msg):
        if not state["auto_tried"]:
            state["auto_tried"] = True
            return {
                "action": "send",
                "body": "It looks like you're away. I've left a draft ready for you. Reply YES whenever you are back to review it.",
                "cta": "Review Draft",
                "rationale": "Auto-reply detected -> rescue attempt."
            }
        return {
            "action": "end",
            "rationale": "Repeated auto-reply -> graceful exit."
        }
        
    # 3. NEGATIVE INTENT
    if _match_any(NEG_PAT, msg):
        return {
            "action": "end",
            "rationale": "Explicit opt-out detected."
        }
        
    # 4. WAIT INTENT
    if _match_any(ASK_TIME_PAT, msg):
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Merchant asked for time."
        }
        
    # 5. POSITIVE / ACTION INTENT
    if _match_any(POS_PAT, msg) or state["mode"] == "action":
        state["mode"] = "action"
        idx = state.get("action_count", 0)
        body = ACTION_VARIANTS[idx % len(ACTION_VARIANTS)]
        state["action_count"] = idx + 1
        return {
            "action": "send",
            "body": body,
            "cta": "Approve Draft",
            "rationale": "Positive intent -> Action mode activated."
        }
        
    # 6. UNCLEAR/UNCATEGORIZED
    state["bot_nudges"] += 1
    if state["bot_nudges"] >= 3:
        return {
            "action": "end",
            "rationale": "Max unclear turns reached -> graceful exit."
        }
        
    return {
        "action": "send",
        "body": "Could you clarify? If you'd like to proceed with the update, just say 'yes'. If not, say 'stop'.",
        "cta": "Proceed",
        "rationale": "Unclear input -> sending nudge."
    }

@app.post("/v1/teardown")
def teardown():
    contexts["category"].clear()
    contexts["merchant"].clear()
    contexts["customer"].clear()
    contexts["trigger"].clear()
    conversations.clear()
    sent_keys.clear()
    return {"status": "ok"}