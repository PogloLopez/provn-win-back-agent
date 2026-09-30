"""Email placeholders: which ones a draft may use, their values, and strict rendering."""

import re

from jinja2 import Environment, StrictUndefined

from winback.business_rules import BusinessRules
from winback.carts import Cart
from winback.offer_models import OfferProposal

PLACEHOLDER = re.compile(r"{{\s*(\w+)\s*}}")
BASE_PLACEHOLDERS = {"section", "seats", "checkout_link"}
REQUIRED_BASE = {"checkout_link"}
CHECKOUT_URL = "https://example.com/checkout/{cart_id}"  # demo stand-in for the real ticketing link

_env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)


def used(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def allowed(proposal: OfferProposal) -> set[str]:
    return BASE_PLACEHOLDERS | {o.type for o in proposal.offers}


def required(proposal: OfferProposal) -> set[str]:
    return REQUIRED_BASE | {o.type for o in proposal.offers}


def values(cart: Cart, proposal: OfferProposal, rules: BusinessRules) -> dict[str, str]:
    out = {
        "section": cart.section,
        "seats": f"{cart.seats} seat" if cart.seats == 1 else f"{cart.seats} seats",
        "checkout_link": CHECKOUT_URL.format(cart_id=cart.cart_id),
    }
    for offer in proposal.offers:
        out[offer.type] = rules.offers[offer.type].phrase.format(value=f"{offer.value:g}")
    return out


def render(template: str, context: dict[str, str]) -> str:
    """Fill placeholders. A placeholder without a value raises instead of rendering blank."""
    return _env.from_string(template).render(context)
