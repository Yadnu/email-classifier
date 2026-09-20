"""Tests for email_classifier.ingest.ground_truth.

Uses synthetic label lists — no real email content.
"""
from __future__ import annotations

import pytest

from email_classifier.ingest.ground_truth import is_replied_in_thread, label_for_message


class TestLabelForMessage:
    # ── spam ──────────────────────────────────────────────────────────────────

    def test_spam_label(self) -> None:
        assert label_for_message(["SPAM"]) == "spam"

    def test_spam_plus_inbox(self) -> None:
        """SPAM takes precedence even if INBOX is also present."""
        assert label_for_message(["INBOX", "SPAM", "UNREAD"]) == "spam"

    # ── ham ───────────────────────────────────────────────────────────────────

    def test_inbox_is_ham(self) -> None:
        assert label_for_message(["INBOX", "UNREAD"]) == "ham"

    def test_sent_is_ham(self) -> None:
        assert label_for_message(["SENT"]) == "ham"

    def test_inbox_and_sent_is_ham(self) -> None:
        assert label_for_message(["INBOX", "SENT"]) == "ham"

    def test_empty_labels_is_ham(self) -> None:
        """Messages with no recognised labels default to ham."""
        assert label_for_message([]) == "ham"

    def test_custom_user_label_is_ham(self) -> None:
        assert label_for_message(["Label_123456"]) == "ham"

    # ── promotions ────────────────────────────────────────────────────────────

    def test_promotions_as_promotional(self) -> None:
        assert (
            label_for_message(["CATEGORY_PROMOTIONS"], promotions_as="promotional")
            == "promotional"
        )

    def test_promotions_as_ham(self) -> None:
        assert (
            label_for_message(["CATEGORY_PROMOTIONS"], promotions_as="ham") == "ham"
        )

    def test_promotions_as_ignore(self) -> None:
        assert (
            label_for_message(["CATEGORY_PROMOTIONS"], promotions_as="ignore") is None
        )

    def test_promotions_with_spam_is_spam(self) -> None:
        """SPAM beats CATEGORY_PROMOTIONS."""
        assert (
            label_for_message(["CATEGORY_PROMOTIONS", "SPAM"], promotions_as="ignore")
            == "spam"
        )

    def test_promotions_with_inbox_no_spam(self) -> None:
        """CATEGORY_PROMOTIONS + INBOX without SPAM → controlled by promotions_as."""
        assert (
            label_for_message(
                ["INBOX", "CATEGORY_PROMOTIONS"], promotions_as="promotional"
            )
            == "promotional"
        )


class TestIsRepliedInThread:
    def test_replied_when_later_sent_exists(self) -> None:
        msg_date = 1_000_000
        thread_sent = [("reply_id", 2_000_000)]  # later than msg_date
        assert is_replied_in_thread("orig_id", msg_date, thread_sent) is True

    def test_not_replied_when_only_earlier_sent(self) -> None:
        msg_date = 2_000_000
        thread_sent = [("earlier_reply", 1_000_000)]  # earlier — not a reply
        assert is_replied_in_thread("orig_id", msg_date, thread_sent) is False

    def test_not_replied_when_no_sent_messages(self) -> None:
        assert is_replied_in_thread("orig_id", 1_000_000, []) is False

    def test_not_replied_when_internal_date_is_none(self) -> None:
        assert is_replied_in_thread("orig_id", None, [("reply", 2_000_000)]) is False

    def test_same_message_id_not_counted(self) -> None:
        """The message itself appearing in the sent list should not count."""
        msg_date = 1_000_000
        # Same ID, later date — should still be False.
        thread_sent = [("orig_id", 2_000_000)]
        assert is_replied_in_thread("orig_id", msg_date, thread_sent) is False

    def test_multiple_sent_one_later(self) -> None:
        msg_date = 1_500_000
        thread_sent = [
            ("earlier", 1_000_000),   # before — doesn't count
            ("later", 2_000_000),     # after — counts
        ]
        assert is_replied_in_thread("orig_id", msg_date, thread_sent) is True

    def test_equal_date_not_counted(self) -> None:
        """Strictly later is required; equal dates don't count as a reply."""
        msg_date = 1_000_000
        thread_sent = [("reply", 1_000_000)]  # same date
        assert is_replied_in_thread("orig_id", msg_date, thread_sent) is False
