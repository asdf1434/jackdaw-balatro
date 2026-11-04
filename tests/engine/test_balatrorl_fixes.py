"""Fixes made on the asdf1434/jackdaw-balatro fork, branch balatrorl-fixes.

BalatroRL checks its scorer against jackdaw; these four bugs changed what
Swashbuckler, The Idol and Card Sharp score.
"""

from __future__ import annotations

from jackdaw.engine.actions import CashOut, NextRound, PlayHand, SelectBlind
from jackdaw.engine.card_factory import create_joker
from jackdaw.engine.game import step
from jackdaw.engine.run_init import initialize_run

_RANK_IDS = {"Jack": 11, "Queen": 12, "King": 13, "Ace": 14}


def test_create_joker_sets_cost_and_sell_value():
    # Card:init calls set_cost; Swashbuckler sums the other jokers' sell_cost.
    for key, cost in (("j_joker", 2), ("j_swashbuckler", 4), ("j_baseball", 8)):
        joker = create_joker(key)
        assert joker.cost == cost
        assert joker.sell_cost == max(1, cost // 2)


def test_idol_card_has_the_id_its_handler_reads():
    gs = initialize_run("b_red", 1, "IDOL")
    step(gs, SelectBlind())
    idol = gs["current_round"]["idol_card"]
    assert idol["id"] == _RANK_IDS.get(idol["rank"], None) or idol["id"] == int(idol["rank"])


def test_a_play_is_recorded_once():
    gs = initialize_run("b_red", 1, "ONCE")
    step(gs, SelectBlind())
    gs["blind"].chips = 10**9
    step(gs, PlayHand(card_indices=(0,)))
    hands = gs["hand_levels"]._hands.values()
    assert sum(h.played for h in hands) == 1
    assert sum(h.played_this_round for h in hands) == 1


def test_played_this_round_resets_at_the_next_blind():
    gs = initialize_run("b_red", 1, "RESET")
    step(gs, SelectBlind())
    gs["blind"].chips = 1
    step(gs, PlayHand(card_indices=(0, 1, 2, 3, 4)))
    step(gs, CashOut())
    step(gs, NextRound())
    step(gs, SelectBlind())
    hands = gs["hand_levels"]._hands.values()
    assert sum(h.played for h in hands) == 1
    assert sum(h.played_this_round for h in hands) == 0
