from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


ACTION_WORDS = [
    "action",
    "required",
    "please",
    "reply",
    "urgent",
    "approve",
    "sign",
    "confirm",
    "invoice",
    "meeting",
    "schedule",
    "deadline",
    "follow up",
    "follow-up",
    "review",
    "decision",
    "needs",
]

NOISE_HINTS = [
    "unsubscribe",
    "newsletter",
    "promo",
    "promotion",
    "sale",
    "deal",
    "noreply",
    "no-reply",
    "notification",
    "digest",
]


@dataclass
class IntelligenceResult:
    summary: str
    intent: str
    actionability_score: int
    noise_score: int
    suggested_action: str
    cluster_label: str
    reason_codes: list[str]


class IntelligenceEngine:
    def summarize(self, subject: str, snippet: str, body: str, sender: str = "") -> str:
        parts = []
        if subject:
            parts.append(subject.strip())
        body_text = (snippet or body or "").strip()
        if body_text:
            cleaned = re.sub(r"\s+", " ", body_text)
            parts.append(cleaned[:220])
        if sender:
            parts.append(f"from {sender}")
        return " — ".join(parts[:3])

    def detect_intent(self, text: str) -> str:
        lower = text.lower()
        if any(w in lower for w in ["schedule", "meeting", "calendar", "availability"]):
            return "schedule"
        if any(w in lower for w in ["invoice", "payment", "bill", "receipt", "pay"]):
            return "finance"
        if any(w in lower for w in ["approve", "sign", "decision", "legal"]):
            return "approval"
        if any(w in lower for w in ["follow up", "follow-up", "remind"]):
            return "follow_up"
        if any(w in lower for w in ["thanks", "got it", "received", "confirm"]):
            return "acknowledgement"
        if any(w in lower for w in ["newsletter", "digest", "promo"]):
            return "noise"
        return "reply_needed"

    def score_actionability(self, text: str) -> int:
        lower = text.lower()
        return sum(1 for w in ACTION_WORDS if w in lower)

    def score_noise(self, sender: str, text: str) -> int:
        lower = f"{sender}\n{text}".lower()
        return sum(1 for w in NOISE_HINTS if w in lower)

    def suggest_action(self, intent: str, actionability_score: int, noise_score: int) -> str:
        if noise_score >= 2 and actionability_score <= 1:
            return "archive"
        if intent == "schedule":
            return "draft_schedule_reply"
        if intent == "finance":
            return "review_and_route"
        if intent == "approval":
            return "review"
        if intent == "follow_up":
            return "set_follow_up"
        if actionability_score >= 2:
            return "reply"
        if noise_score >= 1:
            return "quiet"
        return "review"

    def cluster_label(self, subject: str, sender: str, body: str) -> str:
        subj = subject.strip()
        if subj:
            cleaned = re.sub(r"^(re|fw|fwd):\s*", "", subj, flags=re.IGNORECASE)
            if len(cleaned) > 48:
                cleaned = cleaned[:45].rstrip() + "…"
            return cleaned

        sender_domain = sender.split("@")[-1].strip(" >") if "@" in sender else ""
        if sender_domain:
            return sender_domain

        words = re.findall(r"[a-zA-Z]{4,}", body.lower())
        if words:
            counts = Counter(words)
            return counts.most_common(1)[0][0].title()
        return "Uncategorized"

    def analyze(self, subject: str, sender: str, snippet: str, body: str) -> IntelligenceResult:
        text = f"{subject}\n{snippet}\n{body}".strip()
        intent = self.detect_intent(text)
        actionability_score = self.score_actionability(text)
        noise_score = self.score_noise(sender, text)
        reason_codes = []
        if actionability_score:
            reason_codes.append("contains_action_language")
        if noise_score:
            reason_codes.append("contains_noise_language")
        if intent != "reply_needed":
            reason_codes.append(f"intent:{intent}")
        suggested_action = self.suggest_action(intent, actionability_score, noise_score)
        summary = self.summarize(subject, snippet, body, sender)
        cluster_label = self.cluster_label(subject, sender, body)
        return IntelligenceResult(
            summary=summary,
            intent=intent,
            actionability_score=actionability_score,
            noise_score=noise_score,
            suggested_action=suggested_action,
            cluster_label=cluster_label,
            reason_codes=reason_codes,
        )

    def action_items(self, subject: str, body: str) -> list[str]:
        text = f"{subject}\n{body}".strip()
        items = []
        lower = text.lower()
        if any(w in lower for w in ["schedule", "meeting", "calendar"]):
            items.append("Review scheduling request")
        if any(w in lower for w in ["invoice", "payment", "bill", "receipt"]):
            items.append("Check finance/receipt details")
        if any(w in lower for w in ["approve", "sign", "review"]):
            items.append("Review for approval")
        if any(w in lower for w in ["follow up", "follow-up", "later"]):
            items.append("Set a follow-up reminder")
        if any(w in lower for w in ["deadline", "due", "by friday", "tomorrow"]):
            items.append("Identify deadline and owner")
        return items

    def draft_reply(self, subject: str, sender: str, summary: str, intent: str, tone: str = "concise") -> str:
        if intent == "schedule":
            body = "Thanks — I can take a look. Send over a couple of times that work for you and I’ll confirm."
        elif intent == "finance":
            body = "Thanks. I’m reviewing this now and will route it appropriately if anything needs action."
        elif intent == "approval":
            body = "Thanks — I’m reviewing this and will confirm once I’ve checked the details."
        elif intent == "follow_up":
            body = "Understood — I’ll keep this on my radar and follow up if needed."
        elif intent == "acknowledgement":
            body = "Received, thanks."
        else:
            body = "Thanks — I’ve seen this and will get back to you shortly."

        if tone == "warm":
            body = body.replace("Thanks", "Thanks so much")
        elif tone == "firm":
            body = body.replace("I’ll get back to you shortly", "I’ll respond once I’ve reviewed the details")
        elif tone == "boundary":
            body = body.replace("I’ll get back to you shortly", "I’ll reply when I’m able")
        return body + f"\n\n—\nContext: {summary[:220]}"
