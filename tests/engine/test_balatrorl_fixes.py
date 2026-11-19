"""Fixes made on the asdf1434/jackdaw-balatro fork, branch balatrorl-fixes.

BalatroRL checks its scorer against jackdaw; these four bugs changed what
Swashbuckler, The Idol and Card Sharp score.  The tests at the end are joker
plan stage 10's: the dollar buffer Bull and Bootstraps read, To Do List's hand,
Burnt Joker's context and Delayed Gratification's condition.  The last group is
stage 11's: the jokers that change the rules.
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


# --- joker plan stage 11: the jokers that change the rules ---------------------


def _cards(spec):
    from jackdaw.engine.card_factory import create_playing_card
    from jackdaw.engine.data.enums import Rank, Suit

    ranks = {"2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR, "5": Rank.FIVE, "6": Rank.SIX,
             "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE, "T": Rank.TEN, "J": Rank.JACK,
             "Q": Rank.QUEEN, "K": Rank.KING, "A": Rank.ACE}
    suits = {"H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS, "S": Suit.SPADES}
    return [create_playing_card(suits[c[1]], ranks[c[0]]) for c in spec.split()]


def _hand(spec, *keys, **gs):
    from jackdaw.engine.blind import Blind
    from jackdaw.engine.hand_levels import HandLevels
    from jackdaw.engine.rng import PseudoRandom
    from jackdaw.engine.scoring import score_hand

    return score_hand(_cards(spec), [], [create_joker(k) for k in keys], HandLevels(),
                      Blind.create("bl_small", ante=1), PseudoRandom("RULES"), game_state=gs)


def test_score_hand_reads_four_fingers_shortcut_and_smeared():
    # misc_functions.lua:522-590: find_joker inside get_flush and get_straight.
    assert _hand("2H 5H 9H KH 3S").hand_type == "High Card"
    four = _hand("2H 5H 9H KH 3S", "j_four_fingers")
    assert four.hand_type == "Flush" and len(four.scoring_cards) == 4
    assert _hand("2H 4S 6D 8C TH", "j_shortcut").hand_type == "Straight"
    assert _hand("2H 4S 6D 8C TH").hand_type == "High Card"
    assert _hand("2H 5D 9H KD 3H", "j_smeared").hand_type == "Flush"
    # The four flush cards and the four straight cards need not be the same four.
    both = _hand("2H 3H 4H 5S 9H", "j_four_fingers")
    assert both.hand_type == "Straight Flush" and len(both.scoring_cards) == 5


def test_smeared_reaches_flower_pot_and_seeing_double():
    # card.lua:3807-3862 go through Card:is_suit, which asks for Smeared Joker.
    plain = _hand("2H 3H 5S 9S KS", "j_flower_pot")
    smeared = _hand("2H 3H 5S 9S KS", "j_flower_pot", "j_smeared")
    assert smeared.hand_type == plain.hand_type == "High Card"
    assert _hand("2H 2D 5S 5C", "j_flower_pot").mult == 2 * 3
    assert _hand("2H 2H 5S 5S", "j_flower_pot").mult == 2
    assert _hand("2H 2H 5S 5S", "j_smeared", "j_flower_pot").mult == 2 * 3
    # A black card is a Club and a Spade at once, so Seeing Double always fires on one.
    assert _hand("5S 5S", "j_seeing_double").mult == 2
    assert _hand("5S 5S", "j_smeared", "j_seeing_double").mult == 2 * 2
    assert _hand("5H 5D", "j_smeared", "j_seeing_double").mult == 2


def test_pareidolia_reaches_ride_the_bus():
    # card.lua:3528: is_face, so every scoring card resets the count.
    bus = create_joker("j_ride_the_bus")
    bus.ability["mult"] = 5
    from jackdaw.engine.blind import Blind
    from jackdaw.engine.hand_levels import HandLevels
    from jackdaw.engine.rng import PseudoRandom
    from jackdaw.engine.scoring import score_hand

    score_hand(_cards("2H 2S"), [], [bus, create_joker("j_pareidolia")], HandLevels(),
               Blind.create("bl_small", ante=1), PseudoRandom("BUS"))
    assert bus.ability["mult"] == 0


def test_burglar_adds_hands_after_the_round_resets_them():
    # card.lua:2522 is an event: it runs after new_round set hands and discards.
    gs = initialize_run("b_red", 1, "BURGLAR")
    gs["jokers"] = [create_joker("j_blueprint"), create_joker("j_burglar")]
    step(gs, SelectBlind())
    cr = gs["current_round"]
    assert (cr["hands_left"], cr["discards_left"]) == (4 + 3 + 3, 0)


def test_oops_doubles_the_probability_the_game_loop_reads():
    gs = initialize_run("b_red", 1, "OOPS")
    first, second = create_joker("j_oops"), create_joker("j_oops")
    first.add_to_deck(gs)
    assert gs["probabilities"]["normal"] == 2
    second.add_to_deck(gs)
    assert gs["probabilities"]["normal"] == 4
    first.remove_from_deck(gs)
    assert gs["probabilities"]["normal"] == 2


def test_mr_bones_saves_the_round_once_and_the_blind_pays_nothing():
    gs = initialize_run("b_red", 1, "BONES")
    step(gs, SelectBlind())
    gs["jokers"] = [create_joker("j_mr_bones"), create_joker("j_mr_bones")]
    gs["current_round"]["hands_left"] = 1
    gs["blind"].chips = 20
    step(gs, PlayHand(card_indices=(0,)))
    assert 5 <= gs["chips"] < 20
    assert gs["phase"].name == "ROUND_EVAL"
    assert [j.center_key for j in gs["jokers"]] == ["j_mr_bones"]
    assert gs["round_earnings"].blind_reward == 0


def test_a_discard_reads_pareidolia_smeared_and_the_hand_rules():
    from jackdaw.engine.actions import Discard

    # Faceless Joker: three face cards, and under Pareidolia every card is one.
    for keys, paid in ((["j_faceless"], False), (["j_faceless", "j_pareidolia"], True)):
        gs = initialize_run("b_red", 1, "FACES")
        step(gs, SelectBlind())
        gs["jokers"] = [create_joker(k) for k in keys]
        gs["hand"] = _cards("2H 3S 4D 5C 9H 9S 9D 9C")
        before = gs["dollars"]
        step(gs, Discard(card_indices=(0, 1, 2)))
        assert (gs["dollars"] - before == 5) is paid
    # Castle counts the round's suit; under Smeared Joker, its colour.
    for keys, gained in ((["j_castle"], 1), (["j_castle", "j_smeared"], 2)):
        gs = initialize_run("b_red", 1, "CASTLE")
        step(gs, SelectBlind())
        gs["jokers"] = [create_joker(k) for k in keys]
        gs["current_round"]["castle_card"] = {"suit": "Hearts"}
        gs["hand"] = _cards("2H 3D 4S 5C 9H 9S 9D 9C")
        step(gs, Discard(card_indices=(0, 1, 2)))
        assert gs["jokers"][0].ability["extra"]["chips"] == 3 * gained
    # Burnt Joker levels the hand the discarded cards make under the rules.
    gs = initialize_run("b_red", 1, "BURNT4")
    step(gs, SelectBlind())
    gs["jokers"] = [create_joker("j_burnt"), create_joker("j_four_fingers")]
    gs["hand"] = _cards("2H 5H 9H KH 3S 9S 9D 9C")
    step(gs, Discard(card_indices=(0, 1, 2, 3)))
    assert gs["hand_levels"]["Flush"].level == 2


def test_oops_reaches_gros_michel_at_the_end_of_the_round():
    from jackdaw.engine.jokers import GameSnapshot, on_end_of_round
    from jackdaw.engine.rng import PseudoRandom

    died = {}
    for normal in (1, 2, 4, 8):
        gone = 0
        for i in range(600):
            out = on_end_of_round([create_joker("j_gros_michel")],
                                  GameSnapshot(probabilities_normal=normal),
                                  PseudoRandom(f"GM{i}"))
            gone += len(out.get("jokers_removed", []))
        died[normal] = gone
    assert died[8] == 600 and died[1] < died[2] < died[4] < 600
    assert abs(died[1] / 600 - 1 / 6) < 0.05 and abs(died[2] / 600 - 2 / 6) < 0.06
