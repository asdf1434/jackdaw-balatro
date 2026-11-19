"""The five jokers that change the hand's size (BalatroRL stage 11, second part).

Juggler, Troubadour, Turtle Bean, Stuntman and Merry Andy, through the game
loop.  Each expectation is read from the vanilla 1.0.1o source (file and line
in the test): the size changes when the joker is added or removed
(``card.lua:586-685``, ``G.hand:change_size``), and Turtle Bean's shrinks by
one when a round ends (``card.lua:2903-2927``).
"""

from __future__ import annotations

from jackdaw.engine.actions import CashOut, NextRound, PlayHand, SelectBlind, SellCard
from jackdaw.engine.card_factory import create_joker
from jackdaw.engine.game import _add_joker, step
from jackdaw.engine.run_init import initialize_run


def _run(seed: str, *keys: str) -> dict:
    gs = initialize_run("b_red", 1, seed)
    for k in keys:
        _add_joker(gs, create_joker(k))
    return gs


def _select(gs: dict) -> tuple[int, int, int]:
    """Select the blind; ``(cards dealt, hands, discards)``."""
    step(gs, SelectBlind())
    cr = gs["current_round"]
    return len(gs["hand"]), cr["hands_left"], cr["discards_left"]


def _win(gs: dict) -> None:
    gs["blind"].chips = 1
    step(gs, PlayHand(card_indices=(0, 1, 2, 3, 4)))
    step(gs, CashOut())
    step(gs, NextRound())


def test_each_joker_sets_the_hand_the_hands_and_the_discards():
    # Red Deck: 4 hands, 4 discards (one more than the plain 3), 8 cards.
    assert _select(_run("PLAIN")) == (8, 4, 4)
    assert _select(_run("JUG", "j_juggler")) == (9, 4, 4)  # h_size = 1
    assert _select(_run("TROUB", "j_troubadour")) == (10, 3, 4)  # card.lua:623
    assert _select(_run("BEAN", "j_turtle_bean")) == (13, 4, 4)  # card.lua:605
    assert _select(_run("STUNT", "j_stuntman")) == (6, 4, 4)  # card.lua:627
    assert _select(_run("ANDY", "j_merry_andy")) == (7, 4, 7)  # d_size = 3, h_size = -1
    assert _select(_run("MOST", "j_juggler", "j_troubadour", "j_turtle_bean")) == (16, 3, 4)
    assert _select(_run("LEAST", "j_stuntman", "j_merry_andy")) == (5, 4, 7)


def test_turtle_bean_shrinks_the_hand_each_round_and_is_eaten_after_the_fifth():
    # card.lua:2903: destroyed when h_size - h_mod <= 0, else the hand loses
    # h_mod cards (card.lua:2927).  The fork's handler changed its own number
    # and left the hand at 13 until the joker was eaten.
    gs = _run("BEAN", "j_turtle_bean")
    dealt = []
    for _ in range(6):
        dealt.append(_select(gs)[0])
        assert gs["hand_size"] == dealt[-1]
        _win(gs)
    assert dealt == [13, 12, 11, 10, 9, 8]
    assert [j.center_key for j in gs["jokers"]] == []
    assert gs["hand_size"] == 8


def test_selling_a_size_joker_restores_the_hand():
    gs = _run("SELL", "j_juggler", "j_turtle_bean", "j_merry_andy", "j_troubadour")
    assert _select(gs) == (15, 3, 7)
    gs["blind"].chips = 1
    step(gs, PlayHand(card_indices=(0, 1, 2, 3, 4)))
    step(gs, CashOut())
    # Turtle Bean now adds 4.  Sell it, then Troubadour and Merry Andy.
    assert gs["hand_size"] == 14
    for key in ("j_turtle_bean", "j_troubadour", "j_merry_andy"):
        at = [j.center_key for j in gs["jokers"]].index(key)
        step(gs, SellCard(area="jokers", card_index=at))
    step(gs, NextRound())
    assert _select(gs) == (9, 4, 4)


def test_a_hand_deals_what_the_deck_has_left():
    # 16 cards, 3 hands and 4 discards of five cards: 16 + 6 * 5 = 46 of 52,
    # and with Burglar's hands the deck runs out.
    gs = _run("OUT", "j_juggler", "j_troubadour", "j_turtle_bean", "j_burglar")
    dealt, hands, discards = _select(gs)
    assert (dealt, hands, discards) == (16, 6, 0)  # card.lua:2522: +3 hands, no discards
    gs["blind"].chips = 10**12
    sizes = []
    for _ in range(5):
        step(gs, PlayHand(card_indices=(0, 1, 2, 3, 4)))
        sizes.append((len(gs["hand"]), len(gs["deck"])))
    # 36 cards left after the deal; each hand draws five until they are gone.
    assert sizes == [(16, 31), (16, 26), (16, 21), (16, 16), (16, 11)]
