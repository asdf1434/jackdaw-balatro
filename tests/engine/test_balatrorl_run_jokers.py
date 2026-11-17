"""Game-loop fixes for the 21 jokers that act on the run (BalatroRL stage 5).

Each expectation is read from the vanilla 1.0.1o source (file and line in the
test) and agrees with the Balatro wiki.  jackdaw's joker handlers mostly
returned the right signals; these tests pin what the game loop does with them.
"""

from __future__ import annotations

import pytest

from jackdaw.engine.actions import (
    BuyCard,
    CashOut,
    NextRound,
    PlayHand,
    Reroll,
    SelectBlind,
    SellCard,
)
from jackdaw.engine.blind import Blind
from jackdaw.engine.card_factory import create_consumable, create_joker
from jackdaw.engine.game import IllegalActionError, _add_joker, step
from jackdaw.engine.jokers import GameSnapshot, on_end_of_round
from jackdaw.engine.run_init import initialize_run


def _run(seed: str = "RUN", *keys: str) -> dict:
    gs = initialize_run("b_red", 1, seed)
    for k in keys:
        _add_joker(gs, create_joker(k))
    return gs


def _win_blind(gs: dict) -> None:
    """Select the blind on deck and win it with five played cards (The Psychic)."""
    step(gs, SelectBlind())
    gs["blind"].chips = 1
    step(gs, PlayHand(card_indices=(0, 1, 2, 3, 4)))


def _to_shop(gs: dict) -> None:
    _win_blind(gs)
    step(gs, CashOut())


def _offer(gs: dict, key: str) -> int:
    """Put *key* in the shop's first card slot; return its index."""
    card = create_joker(key)
    gs["shop_cards"].insert(0, card)
    return 0


def _keys(gs: dict) -> list[str]:
    return [j.center_key for j in gs["jokers"]]


# --- end of round: money ------------------------------------------------------


def test_joker_dollars_are_paid_once_and_not_counted_toward_interest():
    # state_events.lua:1176 and 1192: calculate_dollar_bonus and interest are
    # both computed in evaluate_round from G.GAME.dollars before any payout.
    gs = _run("ONCE", "j_golden")
    gs["dollars"] = 20
    _win_blind(gs)
    assert gs["dollars"] == 20  # nothing paid before cash out
    earnings = gs["round_earnings"]
    assert earnings.joker_dollars == 4
    assert earnings.interest == 4  # floor(20 / 5), not floor(24 / 5)
    step(gs, CashOut())
    assert gs["dollars"] == 20 + earnings.total


def test_cloud_9_pays_per_nine_in_the_full_deck():
    # card.lua:4192 (nine_tally) and 1661; a standard deck has four 9s.
    gs = _run("NINE", "j_cloud_9")
    _win_blind(gs)
    assert gs["round_earnings"].joker_dollars == 4


def test_satellite_pays_per_distinct_planet_used_this_run():
    # card.lua:1669 counts keys of G.GAME.consumeable_usage with set Planet.
    from jackdaw.engine.game import _use_consumable_card

    gs = _run("SAT", "j_satellite")
    for key in ("c_mercury", "c_venus", "c_mercury"):
        _use_consumable_card(gs, create_consumable(key))
    _win_blind(gs)
    assert gs["round_earnings"].joker_dollars == 2


def test_rocket_grows_at_a_boss_and_pays_the_new_amount_that_round():
    # card.lua:2896 fires in end_round, before evaluate_round pays (1666).
    rocket = create_joker("j_rocket")
    boss = Blind.create("bl_hook", 1)
    out = on_end_of_round([rocket], GameSnapshot(), None, blind=boss)
    assert out["dollars_earned"] == 3
    small = Blind.create("bl_small", 1)
    assert on_end_of_round([rocket], GameSnapshot(), None, blind=small)["dollars_earned"] == 3


def test_campfire_resets_at_a_boss_only():
    # card.lua:2889.
    fire = create_joker("j_campfire")
    fire.ability["x_mult"] = 2.0
    on_end_of_round([fire], GameSnapshot(), None, blind=Blind.create("bl_small", 1))
    assert fire.ability["x_mult"] == 2.0
    on_end_of_round([fire], GameSnapshot(), None, blind=Blind.create("bl_hook", 1))
    assert fire.ability["x_mult"] == 1


# --- end of round: values and destruction --------------------------------------


def test_egg_and_gift_card_raise_sell_values():
    # card.lua:2984 and 2992: extra_value, then set_cost.  Gift Card adds to
    # every joker, itself included.
    gs = _run("SELL", "j_egg", "j_gift", "j_joker")
    before = {j.center_key: j.sell_cost for j in gs["jokers"]}
    _win_blind(gs)
    after = {j.center_key: j.sell_cost for j in gs["jokers"]}
    assert after["j_egg"] == before["j_egg"] + 3 + 1
    assert after["j_gift"] == before["j_gift"] + 1
    assert after["j_joker"] == before["j_joker"] + 1


def test_popcorn_scores_20_16_12_8_4_and_is_eaten_after_the_fifth_round():
    # card.lua:2950: destroyed when mult - 4 <= 0.
    gs = _run("CORN", "j_popcorn")
    seen = []
    for _ in range(5):
        seen.append(gs["jokers"][0].ability.get("mult", 20) if gs["jokers"] else None)
        _to_shop(gs)
        step(gs, NextRound())
    assert seen == [20, 16, 12, 8, 4]
    assert "j_popcorn" not in _keys(gs)


def test_gros_michel_extinction_sets_the_pool_flag():
    # card.lua:3037; game.lua:407 and 432 gate Gros Michel and Cavendish on it.
    gs = _run("BANANA", "j_gros_michel")
    gs["jokers"][0].ability["extra"]["odds"] = 1  # always dies
    _win_blind(gs)
    assert "j_gros_michel" not in _keys(gs)
    assert gs["pool_flags"].get("gros_michel_extinct") is True


def test_invisible_joker_counts_rounds():
    gs = _run("INVIS", "j_invisible")
    _to_shop(gs)
    step(gs, NextRound())
    _to_shop(gs)
    assert gs["jokers"][0].ability["invis_rounds"] == 2


# --- blind select ---------------------------------------------------------------


def _select(gs: dict) -> None:
    step(gs, SelectBlind())


def test_ceremonial_dagger_destroys_its_right_neighbour_for_twice_its_sell_value():
    # card.lua:2561.
    gs = _run("DAGGER", "j_ceremonial", "j_egg")
    egg_sell = gs["jokers"][1].sell_cost
    _select(gs)
    assert _keys(gs) == ["j_ceremonial"]
    assert gs["jokers"][0].ability["mult"] == 2 * egg_sell


def test_rightmost_ceremonial_dagger_destroys_nothing():
    gs = _run("DAGGER2", "j_egg", "j_ceremonial")
    _select(gs)
    assert _keys(gs) == ["j_egg", "j_ceremonial"]
    assert gs["jokers"][1].ability.get("mult", 0) == 0


def test_madness_destroys_another_joker_never_itself():
    # card.lua:2503: candidates exclude self, eternal and already-sliced jokers.
    # The old code excluded the leftmost joker, so here it destroyed Madness.
    for seed in ("M1", "M2", "M3", "M4"):
        gs = _run(seed, "j_joker", "j_madness")
        _select(gs)
        assert _keys(gs) == ["j_madness"]
        assert gs["jokers"][0].ability["x_mult"] == 1.5


def test_madness_gains_with_nothing_to_destroy_and_skips_bosses():
    gs = _run("MALONE", "j_madness")
    _select(gs)
    assert gs["jokers"][0].ability["x_mult"] == 1.5


def test_madness_does_not_pick_the_dagger_victim():
    # Dagger to the left marks its neighbour first; Madness picks among the
    # rest, and may pick the Dagger itself, which has already fired.
    victims = set()
    for seed in ("MD1", "MD2", "MD3", "MD4", "MD5", "MD6"):
        gs = _run(seed, "j_ceremonial", "j_egg", "j_madness", "j_joker")
        _select(gs)
        keys = _keys(gs)
        assert "j_egg" not in keys and "j_madness" in keys and len(keys) == 2
        victims.update({"j_ceremonial", "j_joker"} - set(keys))
    assert victims == {"j_ceremonial", "j_joker"}


def test_dagger_left_of_riff_raff_stops_it_from_firing():
    # A sliced joker does not fire (card.lua:2491, `not self.getting_sliced`).
    gs = _run("DR", "j_ceremonial", "j_riff_raff")
    _select(gs)
    assert _keys(gs) == ["j_ceremonial"]


def test_dagger_frees_a_slot_for_riff_raff_to_its_right():
    # Dagger lowers joker_buffer at once; Riff-raff reads it (card.lua:2529).
    gs = _run("FULL", "j_ceremonial", "j_egg", "j_joker", "j_golden", "j_riff_raff")
    _select(gs)
    assert len(gs["jokers"]) == 5
    assert "j_egg" not in _keys(gs)


def test_madness_kill_does_not_free_a_slot_for_riff_raff():
    # Madness does not touch joker_buffer, so a full area stays full.
    gs = _run("MFULL", "j_madness", "j_egg", "j_joker", "j_golden", "j_riff_raff")
    _select(gs)
    assert len(gs["jokers"]) == 4


def test_riff_raff_creates_two_commons_from_the_pool():
    # card.lua:2531: create_card('Joker', G.jokers, nil, 0, ..., 'rif').
    from jackdaw.engine.data.prototypes import JOKERS

    made = set()
    for seed in ("R1", "R2", "R3", "R4", "R5"):
        gs = _run(seed, "j_riff_raff")
        _select(gs)
        new = _keys(gs)[1:]
        assert len(new) == 2
        assert all(JOKERS[k].rarity == 1 for k in new)
        assert "j_riff_raff" not in new  # held jokers stay out of the pool
        made.update(new)
    assert len(made) > 2  # the output is not fixed


# --- buying and selling ----------------------------------------------------------


def test_to_the_moon_adds_interest_while_held():
    # card.lua:613 and 670.
    gs = _run("MOON")
    _to_shop(gs)
    gs["dollars"] = 50
    step(gs, BuyCard(shop_index=_offer(gs, "j_to_the_moon")))
    assert gs["interest_amount"] == 2
    step(gs, SellCard(area="jokers", card_index=0))
    assert gs["interest_amount"] == 1


def test_credit_card_allows_twenty_dollars_of_debt():
    # card.lua:594; button_callbacks.lua:97 compares against dollars - bankrupt_at.
    gs = _run("DEBT")
    _to_shop(gs)
    gs["dollars"] = 1
    step(gs, BuyCard(shop_index=_offer(gs, "j_credit_card")))
    assert gs["dollars"] == 0 and gs["bankrupt_at"] == -20
    step(gs, BuyCard(shop_index=_offer(gs, "j_golden")))
    assert gs["dollars"] == -6
    step(gs, SellCard(area="jokers", card_index=_keys(gs).index("j_credit_card")))
    assert gs["bankrupt_at"] == 0
    with pytest.raises(IllegalActionError):
        step(gs, BuyCard(shop_index=_offer(gs, "j_egg")))


def test_chaos_bought_mid_shop_makes_the_next_reroll_free_without_raising_its_price():
    # card.lua:601; calculate_reroll_cost(final_free) skips the increment.
    gs = _run("CHAOS")
    _to_shop(gs)
    gs["dollars"] = 50
    base = gs["current_round"]["reroll_cost"]
    step(gs, BuyCard(shop_index=_offer(gs, "j_chaos")))
    assert gs["current_round"]["reroll_cost"] == 0
    money = gs["dollars"]
    step(gs, Reroll())
    assert gs["dollars"] == money
    assert gs["current_round"]["reroll_cost"] == base
    step(gs, Reroll())
    assert gs["dollars"] == money - base
    assert gs["current_round"]["reroll_cost"] == base + 1


def test_flash_card_gains_per_reroll():
    gs = _run("FLASH", "j_flash")
    _to_shop(gs)
    gs["dollars"] = 50
    step(gs, Reroll())
    step(gs, Reroll())
    assert gs["jokers"][0].ability["mult"] == 4


def test_campfire_gains_when_another_card_is_sold():
    gs = _run("FIRE", "j_campfire", "j_joker")
    _to_shop(gs)
    step(gs, SellCard(area="jokers", card_index=1))
    assert gs["jokers"][0].ability["x_mult"] == 1.25


def test_sold_jokers_return_to_the_pool():
    gs = _run("POOL", "j_joker")
    assert gs["used_jokers"].get("j_joker")
    _to_shop(gs)
    step(gs, SellCard(area="jokers", card_index=0))
    assert not gs["used_jokers"].get("j_joker")


def test_invisible_joker_sold_after_two_rounds_copies_another_joker_with_its_state():
    # card.lua:2370: a random other joker; copy_card keeps the ability table.
    gs = _run("COPY", "j_popcorn", "j_invisible")
    gs["jokers"][0].ability["mult"] = 12
    gs["jokers"][1].ability["invis_rounds"] = 2
    _to_shop(gs)
    step(gs, SellCard(area="jokers", card_index=1))
    assert _keys(gs) == ["j_popcorn", "j_popcorn"]
    assert [j.ability["mult"] for j in gs["jokers"]] == [8, 8]  # after this round's -4
    assert gs["jokers"][0] is not gs["jokers"][1]


def test_invisible_joker_copies_with_a_full_joker_area():
    # The check is #G.jokers.cards <= card_limit while the sold card is held.
    gs = _run("COPY5", "j_joker", "j_egg", "j_golden", "j_popcorn", "j_invisible")
    gs["jokers"][4].ability["invis_rounds"] = 2
    _to_shop(gs)
    step(gs, SellCard(area="jokers", card_index=4))
    assert len(gs["jokers"]) == 5


def test_invisible_joker_before_two_rounds_copies_nothing():
    gs = _run("EARLY", "j_joker", "j_invisible")
    _to_shop(gs)
    step(gs, SellCard(area="jokers", card_index=1))
    assert _keys(gs) == ["j_joker"]


def test_showman_and_astronomer_flags_follow_the_held_jokers():
    gs = _run("FLAGS")
    _to_shop(gs)
    gs["dollars"] = 50
    step(gs, BuyCard(shop_index=_offer(gs, "j_ring_master")))
    assert gs["has_showman"]
    planet = create_consumable("c_pluto")
    planet.set_cost()
    gs["shop_cards"].append(planet)
    assert planet.cost > 0
    step(gs, BuyCard(shop_index=_offer(gs, "j_astronomer")))
    assert gs["has_astronomer"] and planet.cost == 0
    step(gs, SellCard(area="jokers", card_index=_keys(gs).index("j_astronomer")))
    assert not gs["has_astronomer"] and planet.cost > 0


# --- BalatroRL stage 6: copies at blind select ----------------------------------


def test_blueprint_copies_riff_raff_at_blind_select():
    # card.lua:2529: Riff-raff has no ``not context.blueprint`` guard, and each
    # firing takes min(2, slots - (jokers + joker_buffer)).  Blueprint fires
    # first and makes two; Riff-raff then has room for one.
    gs = _run("BPRIF", "j_blueprint", "j_riff_raff")
    step(gs, SelectBlind())
    assert len(gs["jokers"]) == 5


def test_blueprint_does_not_copy_madness_or_the_dagger():
    # card.lua:2503, 2561: both are guarded by ``not context.blueprint``.
    gs = _run("BPMAD", "j_blueprint", "j_madness")
    step(gs, SelectBlind())
    madness = next(j for j in gs["jokers"] if j.center_key == "j_madness")
    assert madness.ability["x_mult"] == 1.5
    gs = _run("BPDAG", "j_blueprint", "j_ceremonial", "j_joker")
    step(gs, SelectBlind())
    assert _keys(gs) == ["j_blueprint", "j_ceremonial"]
