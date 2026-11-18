"""Fixes made on the asdf1434/jackdaw-balatro fork, branch balatrorl-fixes.

BalatroRL checks its scorer against jackdaw; these four bugs changed what
Swashbuckler, The Idol and Card Sharp score.  The tests at the end are joker
plan stage 10's: the dollar buffer Bull and Bootstraps read, To Do List's hand,
Burnt Joker's context and Delayed Gratification's condition.
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


# --- joker plan stage 10: blind actions that earn hand levels or money -------


def _score(played, jokers, money=0, held=()):
    from jackdaw.engine.blind import Blind
    from jackdaw.engine.hand_levels import HandLevels
    from jackdaw.engine.rng import PseudoRandom
    from jackdaw.engine.scoring import score_hand

    return score_hand(list(played), list(held), jokers, HandLevels(),
                      Blind.create("bl_small", ante=1), PseudoRandom("BUFFER"),
                      game_state={"money": money})


def test_bull_and_bootstraps_read_the_hands_dollar_buffer():
    # card.lua:3936 and 4046 read G.GAME.dollars + G.GAME.dollar_buffer, and
    # Rough Gem adds $1 to the buffer per scoring Diamond (card.lua:3224).
    from jackdaw.engine.card_factory import create_playing_card
    from jackdaw.engine.data.enums import Rank, Suit

    pair = [create_playing_card(Suit.DIAMONDS, Rank.KING), create_playing_card(Suit.DIAMONDS, Rank.KING)]
    plain = _score(pair, [create_joker("j_bull")], money=3)
    gem = _score(pair, [create_joker("j_rough_gem"), create_joker("j_bull")], money=3)
    assert gem.dollars_earned == 2
    # Bull: +2 chips per dollar, so $2 more in the buffer is 4 more chips.
    assert gem.chips == plain.chips + 4
    boot = _score(pair, [create_joker("j_rough_gem"), create_joker("j_bootstraps")], money=3)
    assert boot.mult == _score(pair, [create_joker("j_bootstraps")], money=5).mult


def test_to_do_list_pays_only_bull_to_its_right():
    from jackdaw.engine.card_factory import create_playing_card
    from jackdaw.engine.data.enums import Rank, Suit

    pair = [create_playing_card(Suit.SPADES, Rank.KING), create_playing_card(Suit.HEARTS, Rank.KING)]
    todo = create_joker("j_todo_list")
    todo.ability["to_do_poker_hand"] = "Pair"
    left = _score(pair, [todo, create_joker("j_bull")], money=1)
    right = _score(pair, [create_joker("j_bull"), todo], money=1)
    assert left.dollars_earned == right.dollars_earned == 4
    assert left.chips == right.chips + 8


def test_to_do_list_has_a_hand_and_redraws_another_each_round():
    from jackdaw.engine.jokers import GameSnapshot, on_end_of_round
    from jackdaw.engine.rng import PseudoRandom

    todo = create_joker("j_todo_list", rng=PseudoRandom("TODO"))
    first = todo.ability["to_do_poker_hand"]
    assert first
    rng = PseudoRandom("TODO2")
    seen = set()
    for _ in range(40):
        before = todo.ability["to_do_poker_hand"]
        on_end_of_round([todo], GameSnapshot(), rng)
        assert todo.ability["to_do_poker_hand"] != before
        seen.add(todo.ability["to_do_poker_hand"])
    assert len(seen) > 4 and "Flush Five" not in seen


def test_burnt_joker_levels_before_the_discard_and_a_copy_levels_again():
    # card.lua:2749: pre_discard, no blueprint guard.
    gs = initialize_run("b_red", 1, "BURNT")
    step(gs, SelectBlind())
    gs["jokers"] = [create_joker("j_blueprint"), create_joker("j_burnt")]
    from jackdaw.engine.actions import Discard

    step(gs, Discard(card_indices=(0,)))
    levels = [h.level for h in gs["hand_levels"]._hands.values()]
    assert sum(levels) == len(levels) + 2
    step(gs, Discard(card_indices=(0,)))
    assert sum(h.level for h in gs["hand_levels"]._hands.values()) == len(levels) + 2


def test_delayed_gratification_pays_only_without_a_discard():
    from jackdaw.engine.actions import Discard

    earned = {}
    for discard in (False, True):
        gs = initialize_run("b_red", 1, "DELAY")
        step(gs, SelectBlind())
        gs["jokers"] = [create_joker("j_delayed_grat")]
        if discard:
            step(gs, Discard(card_indices=(0,)))
        gs["blind"].chips = 1
        discards = gs["current_round"]["discards_left"]
        step(gs, PlayHand(card_indices=(0, 1, 2, 3, 4)))
        earned[discard] = gs["round_earnings"].joker_dollars
    # The Red Deck starts with four discards: $2 for each one left.
    assert earned == {False: 2 * (discards + 1), True: 0}
