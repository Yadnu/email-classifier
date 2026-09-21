"""Single Jev question map. All questions go in one system_one call."""
from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score

QUESTIONS = {
    "category": Choice(
        instructions="What category is this email?",
        criteria={
            "spam": "unsolicited bulk or junk",
            "phishing": "tries to steal credentials, money, or personal info",
            "promotional": "legitimate marketing from a sender I have a relationship with",
            "legitimate": "personal, work, or transactional mail",
            "other": "none of these fit",
        },
    ),
    "is_spam": Noul(
        instructions=(
            "This email is unsolicited junk or a scam that the recipient did not ask for"
        ),
    ),
    "needs_reply": Noul(
        instructions=(
            "The sender expects a personal response from the recipient, such as a "
            "direct question, a request, or a scheduling ask. Automated or bulk "
            "emails do not count."
        ),
    ),
    "credential_request": Noul(
        instructions=(
            "The email asks the recipient to log in, verify an account, or enter "
            "payment details via a link"
        ),
    ),
    "brand_impersonation": Noul(
        instructions=(
            "The sender claims to be a well-known company but the sender domain "
            "does not belong to that company"
        ),
    ),
    "pressure": Score(
        instructions="How much urgency or pressure the email applies",
        criteria=[
            "No pressure",
            "Mild time-limited offer",
            "Threats or deadlines to act immediately",
        ],
    ),
}
