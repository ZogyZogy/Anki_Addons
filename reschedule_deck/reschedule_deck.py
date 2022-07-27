from typing import (
    List, Dict, )

from PyQt5 import QtWidgets
from anki.cards import Card
from anki.cards import CardId
from anki.decks import DeckId, DeckDict
from aqt import mw
from aqt.utils import showInfo

# --- EXTERNAL VARIABLES ---#

NAME_OF_DECK_TO_REORDER = "JP - Kanji 2k RTK"
MAX_INTERVAL = 21
DUE_ABOVE_WHICH_CARD_IS_SUSPENDED = 1_000_000_000


# --- INTERNAL VARIABLES ---#


# --- BEGINNING of ReorderDeck Class --- #

def range1(start, end):
    return range(start, end + 1)


class RescheduleDeck:
    # --- Variables for current statistics --- #
    max_interval: int
    date_of_today: int
    cards: List[Card]
    deck: DeckDict
    cards_by_interval: Dict[int, List[Card]] = dict()
    cards_by_interval_by_due_date: Dict[int, Dict[int, List[Card]]] = dict()
    average_number_across_due_days: Dict[int, float] = dict()
    difference_of_cards: Dict[int, Dict[int, int]] = dict()

    # --- Variables used only in the algorithm to reschedule cards
    modified_cards_by_interval_by_due_date: Dict[int, Dict[int, List[Card]]]
    cards_with_new_intervals: Dict[Card, int] = dict()

    def __init__(self, cards: List[Card], deck: DeckDict) -> None:
        self.max_due = DUE_ABOVE_WHICH_CARD_IS_SUSPENDED
        self.max_interval = MAX_INTERVAL
        self.init_dict_of_cards(self.cards_by_interval)
        self.init_dict_of_dict_of_cards(self.cards_by_interval_by_due_date)
        self.cards = cards
        self.deck = deck
        self.date_of_today = self.retrieve_date_of_today(deck)
        self.exclude_irrelevant_cards()
        self.sort_cards_by_interval()
        self.sort_cards_by_interval_by_due_date()
        self.calculate_average_number_across_due_days_by_interval()
        self.calculate_difference_between_current_and_average_by_interval_by_due_day()

        self.print_cards_by_interval()
        self.print_cards_by_interval_by_due_date()
        self.print_average()
        self.print_difference()

    # self.reschedule_cards_according_to_average()

    # --- Init Functions of ReorderDeck Class --- #

    def init_cards(self) -> None:
        self.cards = list(get_cards())

    def init_dict_of_cards(self, dict_of_cards: Dict[int, List[Card]]) -> None:
        for interval in range1(1, self.max_interval):
            dict_of_cards[interval]: List[Card] = list()

    def init_dict_of_dict_of_cards(self, dict_of_dict_of_cards: Dict[int, Dict[int, List[Card]]]) -> None:
        for interval in range1(1, self.max_interval):
            dict_of_dict_of_cards[interval]: Dict[int, List[Card]] = dict()
            for due_day in range1(0, interval):
                dict_of_dict_of_cards[interval][due_day]: List[Card] = list()

    @staticmethod
    def retrieve_date_of_today(deck) -> int:
        return deck.pop("timeToday")[0]

    def exclude_irrelevant_cards(self) -> None:
        cards_to_remove: List[Card] = list()
        for card in self.cards:
            # If card is new (interval = 0), we don't keep it
            if card.ivl == 0:
                cards_to_remove.append(card)
            # If card is suspended (due > max_due), we don't keep it
            if card.due > self.max_due:
                cards_to_remove.append(card)
        new_card_list: List[Card] = [card for card in self.cards if card not in cards_to_remove]
        self.cards = list(new_card_list)

    def sort_cards_by_interval(self) -> None:
        for card in self.cards:
            if card.ivl not in range1(1, self.max_interval):
                self.print_vars_obj(card)
                self.print_vars_obj(card.note())
                exit(1)
            self.cards_by_interval[card.ivl].append(card)

    def sort_cards_by_interval_by_due_date(self) -> None:
        for interval in range1(1, self.max_interval):
            cards_for_given_interval: List[Card] = self.cards_by_interval[interval]
            for card in cards_for_given_interval:
                due_day: int = self.get_due_day(card)
                self.cards_by_interval_by_due_date[interval][due_day].append(card)

    def get_due_day(self, card: Card) -> int:
        due_day = card.due - self.date_of_today
        # We set cards past overdue to due today for practical reasons
        if due_day < 1:
            return 0
        if due_day > self.max_interval:
            RescheduleDeck.print_vars_obj(card)
            RescheduleDeck.print_vars_obj(card.note())
            exit()
        return due_day

    # --- Computing Functions of ReorderDeck Class --- #

    def calculate_average_number_across_due_days_by_interval(self):
        for interval in range1(1, self.max_interval):
            total_cards: int = 0
            cards_by_due_day: Dict[int, List[Card]] = self.cards_by_interval_by_due_date[interval]
            for due_day in range1(1, interval):
                total_cards += len(cards_by_due_day[due_day])
            self.average_number_across_due_days[interval] = round(100 * total_cards / interval) / 100

    def calculate_difference_between_current_and_average_by_interval_by_due_day(self):
        for interval in range1(1, self.max_interval):
            self.difference_of_cards[interval]: Dict[int, int] = dict()
            cards_by_due_day: Dict[int, List[Card]] = self.cards_by_interval_by_due_date[interval]
            for due_day in range1(1, interval):
                self.difference_of_cards[interval][due_day] = \
                    round(len(cards_by_due_day[due_day]) - self.average_number_across_due_days[interval])

    def reschedule_cards_according_to_average(self):
        # (careful, maybe (more than maybe) need deep copy of dictionary)
        self.modified_cards_by_interval_by_due_date = dict(self.cards_by_interval_by_due_date)
        text_to_print = "Starting rescheduling"
        for interval in range1(1, self.max_interval):
            iteration = 1
            while iteration < (interval * interval):
                (due_day, max_difference) = self.find_highest_difference_for_given_interval(interval)
                # If highest difference between current and average for every due_day is +- 1, then nothing to reschedule
                if abs(max_difference) <= 1:
                    break
                if due_day == 1:
                    self.move_cards(interval, original_day=1, target_day=2, number=max_difference)
                elif due_day == interval:
                    self.move_cards(interval, original_day=interval, target_day=interval - 1, number=max_difference)
                else:
                    nb_1 = int(max_difference / 2)
                    nb_2 = int(max_difference / 2) + max_difference % 1
                    self.move_cards(interval, original_day=due_day, target_day=due_day - 1, number=nb_1)
                    self.move_cards(interval, original_day=due_day, target_day=due_day + 1, number=nb_2)
                iteration += 1
            text_to_print += f"\n Number of iterations to finish rescheduling for interval = {interval} : "
            text_to_print += f"{iteration} - should be (a lot) lower than {interval * interval}"
        text_to_print += "End of Rescheduling"
        showInfo(text_to_print)

    # needs to use "modified_cards_by_interval_by_due_date" (careful, maybe need deep copy of dictionary)
    def find_highest_difference_for_given_interval(self, interval: int) -> (int, int):
        due_day = 0
        highest_difference = 0
        return due_day, highest_difference

    # needs to use "cards_by_interval_by_due_date", "modified_cards_by_interval_by_due_date",
    # and maybe "cards_with_new_intervals"
    def move_cards(self, interval, original_day, target_day, number):
        pass

    # --- Print Functions of ReorderDeck Class --- #

    @staticmethod
    def print_vars_obj(object):
        showInfo(f"{object.__class__} : {str(vars(object))}")

    def print_cards_by_interval(self):
        text = "Nb of Cards for each interval"
        for interval in range1(1, self.max_interval):
            text += f"\n Nb of Cards for interval {interval} = "
            text += f"{str(len(self.cards_by_interval[interval]))}"
        showInfo(text)

    def print_cards_by_interval_by_due_date(self):
        text = "Nb of Cards for each interval and each due date"
        for interval in range1(1, self.max_interval):
            text += f"\n\n Nb of Cards for each due date in interval = {interval} :"
            for due_day in range1(0, interval):
                text += f"\n Nb of Cards for interval = {interval} and due date = {due_day} : "
                text += f"{str(len(self.cards_by_interval_by_due_date[interval][due_day]))}"
        showInfo(text)

    def print_average(self):
        text = "Computed average number of cards by interval and due_date"
        for interval in range1(1, self.max_interval):
            text += f"\n Average nb of cards for interval {interval} = "
            text += f"{self.average_number_across_due_days[interval]}"
        showInfo(text)

    def print_difference(self):
        text = "Computed difference number of cards between current and average by interval and due_date"
        for interval in range1(1, self.max_interval):
            text += f"\n\n For interval = {interval} "
            for due_day in range1(1, interval):
                text += f"\n Difference for interval '{interval}' and due_date '{due_day}' = "
                text += f"{self.difference_of_cards[interval][due_day]}"
        showInfo(text)


# --- END of ReorderDeck Class --- #

# --- FUNCTIONS ---#

def get_cards() -> List[Card]:
    deck_id: DeckId = mw.col.decks.id_for_name(NAME_OF_DECK_TO_REORDER)
    card_ids: List[CardId] = mw.col.decks.cids(deck_id, children=True)
    return [mw.col.get_card(card_id) for card_id in card_ids]
    # card: Card = mw.col.get_card(card_ids[0])
    # showInfo("card = mw.col.get_card(card_ids[0]) = " + str(vars(card))
    #          + "\n\n" + str(dir(card)))


def get_deck() -> DeckDict:
    return mw.col.decks.by_name(NAME_OF_DECK_TO_REORDER)


def print_incoming_modifications(cards_with_new_intervals: Dict[Card, int]) -> None:
    showInfo("cards_with_new_intervals" + str(cards_with_new_intervals))
    pass


def reorder_cards(cards_with_new_intervals: Dict[Card, int]) -> None:
    pass


def main_function() -> None:
    reorder_deck = RescheduleDeck(get_cards(), get_deck())
    # print_incoming_modifications(reorder_deck.cards_with_new_intervals)
    reorder_cards(reorder_deck.cards_with_new_intervals)


# def sort_cards_by_function(function: Callable[[Card], int],
#                            cards: List[Card],
#                            dict: Dict[int, List[Card]]) -> None:
#     for card in cards:
#         card_interval = function(card)
#         dict[card_interval].append(card)


action = QtWidgets.QAction("Reorder Deck", mw)
action.triggered.connect(main_function)
mw.form.menuTools.addAction(action)
# TODO: Necessary ? Look at AddonManager.configAction()
# TODO: Understand (and refactor the addons.py file)
mw.addonManager.setConfigAction(__name__, main_function)
