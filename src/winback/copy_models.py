"""Copywriter output contract: an email draft with {{placeholders}} instead of values."""

from winback.rules_engine import Strict


class EmailDraft(Strict):
    subject: str
    body: str
