from datetime import date
from typing import (
    List, Dict, Tuple, Callable,
)

import anki.cards
from PyQt5 import QtWidgets
from anki.cards import CardId
from anki.decks import DeckId
from aqt import mw
from aqt.utils import showInfo

# --- EXTERNAL VARIABLES ---#

NAME_OF_DECK_TO_REORDER = "JP - Kanji 2k RTK"
MAX_INTERVAL = 21

# --- INTERNAL VARIABLES ---#


# --- FUNCTIONS ---#


class ReorderDeck:
    max_interval: int
    cards: List[anki.Card]
    cards_by_interval: Dict[int, List[anki.Card]]
    cards_by_interval_by_due_date: Dict[int, Dict[int, List[anki.Card]]]
    cards_with_new_intervals: Dict[anki.Card, int]


    def __init__(self) -> None:
        self.max_interval = MAX_INTERVAL
        self.cards = list()
        self.cards_by_interval = dict()
        self.cards_by_interval_by_due_date = dict()
        self.cards_with_new_intervals = dict()

    def init_cards_by_interval(self)  -> None:
        # We need to start at 0 for cards due today or before, but we won't reorder them
        for interval in range(1, self.max_interval):
            self.cards_by_interval[interval]: List[anki.Card] = list()

    def init_cards_by_interval_by_due_date(self) -> None:
        # We need to start at 0 for cards due today or before, but we won't reorder them
        for interval in range(1, self.max_interval):
            self.cards_by_interval_by_due_date[interval]: List[anki.Card] = list()

    def sort_cards_by_interval(self) -> None:
        for card in self.cards:
            card_interval = card.ivl
            self.cards_by_interval[card_interval].append(card)

    def sort_cards_by_due_day(self, cards_for_a_given_interval: List[anki.Card],
                              cards_by_due_day: Dict[int, List[anki.Card]]) -> None:
        for card in cards_for_a_given_interval:
            due_day: int = self.get_due_day(card)
            cards_by_due_day[due_day].append(card)

    def get_due_day(self, card: anki.Card) -> int:
        due_ordinal = date.fromtimestamp(card.due).toordinal()
        today_ordinal = date.today().toordinal()
        due_day = due_ordinal - today_ordinal
        # We set cards past overdue to due today for practical reasons
        if due_day < 1:
            return 0
        else:
            return due_day

    def get_average_number_of_cards_by_day(self,
            cards_by_due_day: Dict[int, List[anki.Card]]) -> int:
        interval = len(cards_by_due_day) - 1
        total_cards = 0
        # Cards due today or before are not counted
        for due_day in range(1, interval):
            total_cards += cards_by_due_day[due_day]
        average_cards_by_day = round(total_cards / interval)
        return average_cards_by_day

    def reorder_cards_according_to_average(cards_by_due_day: Dict[int, List[anki.Card]],
                                           average_by_day: int):
        pass

    def main_function(editor) -> None:
        cards: List[anki.Card] = get_cards()
        cards_by_interval: Dict[int, List[anki.Card]] = dict()

        init_lists_of_cards_in_dict(cards_by_interval, MAX_INTERVAL)
        sort_cards_by_interval(cards, cards_by_interval)

        for current_interval in range(1, MAX_INTERVAL):
            cards_for_current_interval: List[anki.Card] = cards_by_interval[current_interval]
            cards_by_due_day: Dict[int, List[anki.Card]] = dict()
            init_lists_of_cards_in_dict(cards_by_due_day, max_range=current_interval)
            sort_cards_by_due_day(cards_for_current_interval, cards_by_due_day)
            average_by_day = get_average_number_of_cards_by_day(cards_by_due_day)
            reorder_cards_according_to_average(cards_by_due_day, average_by_day)

    def get_cards() -> List[anki.Card]:
        deck_id: DeckId = mw.col.decks.id_for_name(NAME_OF_DECK_TO_REORDER)
        card_ids: List[CardId] = mw.col.decks.cids(deck_id, children=True)
        return [mw.col.get_card(card_id) for card_id in card_ids]
        # card: anki.Card = mw.col.get_card(card_ids[0])
        # showInfo("card = mw.col.get_card(card_ids[0]) = " + str(vars(card))
        #          + "\n\n" + str(dir(card)))


# def sort_cards_by_function(function: Callable[[anki.Card], int],
#                            cards: List[anki.Card],
#                            dict: Dict[int, List[anki.Card]]) -> None:
#     for card in cards:
#         card_interval = function(card)
#         dict[card_interval].append(card)





action = QtWidgets.QAction("Reorder Deck", mw)
action.triggered.connect(main_function)
mw.form.menuTools.addAction(action)
# TODO: Necessary ? Look at AddonManager.configAction()
# TODO: Understand (and refactor the addons.py file)
mw.addonManager.setConfigAction(__name__, main_function)
