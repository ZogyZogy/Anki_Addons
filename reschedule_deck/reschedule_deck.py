from typing import (
    List, Dict, Sequence, )

from PyQt5 import QtWidgets
from anki.cards import Card
from anki.cards import CardId
from anki.decks import DeckId, DeckDict
from aqt import mw
from aqt.utils import showInfo

# --- EXTERNAL VARIABLES ---#

NAME_OF_DECK_TO_REORDER = "JP - Kanji 2k RTK::JP - Kanji - Subdeck 2"
MAX_INTERVAL = 21

# --- INTERNAL VARIABLES ---#
DUE_ATTRIBUTE_OF_CARD_ABOVE_WHICH_CARD_IS_SUSPENDED = 1_000_000_000


# --- BEGINNING of ReorderDeck Class --- #

def range1(start, end):
    return range(start, end + 1)


# This class only contain the logic of the rescheduling.
# It does NOT modify cards (only adds new fields for simplicity, but even that could be avoided) !
# NO DATABASE ACCESS !
class RescheduleDeck:
    # --- Variables not modified by the algorithm --- #
    max_interval: int
    date_of_today: int
    cards: List[Card]
    deck: DeckDict
    cards_by_interval: Dict[int, List[Card]] = dict()
    due_date_first_original_by_card: Dict[Card, int] = dict()
    average_number_across_due_days: Dict[int, float] = dict()

    # --- Variables modified by the algorithm --- #
    cards_by_interval_by_due_date: Dict[int, Dict[int, List[Card]]] = dict()
    difference_of_cards_by_interval_by_due_date: Dict[int, Dict[int, int]] = dict()

    # --- Variables used after the algorithm is run --- #
    due_date_new_by_card: Dict[Card, int]
    cards_with_new_due_date: Dict[Card, int]

    # TODO: improve comment
    def __init__(self, cards: List[Card], deck: DeckDict) -> None:
        self.max_due = DUE_ATTRIBUTE_OF_CARD_ABOVE_WHICH_CARD_IS_SUSPENDED
        self.max_interval = MAX_INTERVAL
        self.cards = cards
        self.deck = deck
        self.date_of_today = self.retrieve_date_of_today(deck)
        self.exclude_irrelevant_cards()
        self.cards_by_interval = RescheduleDeck.init_dict_of_cards(range1(1, self.max_interval))
        self.sort_cards_by_interval()
        self.cards_by_interval_by_due_date = RescheduleDeck.init_dict_of_dict_of_cards(range1(1, self.max_interval))
        self.sort_cards_by_interval_by_due_date_and_saves_original_due_date()
        self.calculate_average_number_across_due_days_by_interval()
        self.calculate_difference_between_current_and_average_by_interval_by_due_day()

        # self.print_cards_by_interval()
        # self.print_cards_by_interval_by_due_date()
        # self.print_average()
        self.print_difference()

        # Algorithm
        self.reschedule_cards_according_to_average()

        # After algorithm
        self.due_date_new_by_card = self.determine_due_date_new_by_card()
        self.cards_with_new_due_date = self.determine_cards_with_new_intervals()
        self.print_distribution_of_cards_rescheduled()

    # --- Init Functions of ReorderDeck Class --- #

    # TODO: improve comment
    def init_cards(self) -> None:
        self.cards = list(get_cards())

    @staticmethod
    def init_dict_of_cards(range_of_integer_keys: Sequence[int]) -> Dict[int, List[Card]]:
        dict_of_cards: Dict[int, List[Card]] = dict()
        for interval in range_of_integer_keys:
            dict_of_cards[interval]: List[Card] = list()
        return dict_of_cards

    @staticmethod
    def init_dict_of_dict_of_cards(range_of_first_integer_keys: Sequence[int],
                                   ) -> Dict[int, Dict[int, List[Card]]]:
        dict_of_dict_of_cards: Dict[int, Dict[int, List[Card]]] = dict()
        for interval in range_of_first_integer_keys:
            dict_of_dict_of_cards[interval] = RescheduleDeck.init_dict_of_cards(range1(1, interval))
        return dict_of_dict_of_cards

    @staticmethod
    # TODO: improve comment
    def retrieve_date_of_today(deck) -> int:
        return deck.pop("timeToday")[0]

    # TODO: improve comment
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

    # TODO: improve comment
    def sort_cards_by_interval(self) -> None:
        for card in self.cards:
            if card.ivl not in range1(1, self.max_interval):
                self.print_vars_obj(card)
                self.print_vars_obj(card.note())
                exit(1)
            self.cards_by_interval[card.ivl].append(card)

    # TODO: improve comment
    def sort_cards_by_interval_by_due_date_and_saves_original_due_date(self) -> None:
        for interval in range1(1, self.max_interval):
            cards_for_given_interval: List[Card] = self.cards_by_interval[interval]
            for card in cards_for_given_interval:
                due_day: int = self.get_due_day(card)
                # we remove the card if due_day = 0 for simplicity
                if due_day == 0:
                    self.cards.remove(card)
                    continue
                self.due_date_first_original_by_card[card] = due_day
                self.cards_by_interval_by_due_date[interval][due_day].append(card)

    # TODO: improve comment
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

    # TODO: improve comment
    def calculate_average_number_across_due_days_by_interval(self):
        for interval in range1(1, self.max_interval):
            total_cards: int = 0
            cards_by_due_day: Dict[int, List[Card]] = self.cards_by_interval_by_due_date[interval]
            for due_day in range1(1, interval):
                total_cards += len(cards_by_due_day[due_day])
            self.average_number_across_due_days[interval] = round(100 * total_cards / interval) / 100

    # TODO: improve comment
    def calculate_difference_between_current_and_average_by_interval_by_due_day(self):
        for interval in range1(1, self.max_interval):
            self.difference_of_cards_by_interval_by_due_date[interval]: Dict[int, int] = dict()
            cards_by_due_day: Dict[int, List[Card]] = self.cards_by_interval_by_due_date[interval]
            for due_day in range1(1, interval):
                self.difference_of_cards_by_interval_by_due_date[interval][due_day] = \
                    round(len(cards_by_due_day[due_day]) - self.average_number_across_due_days[interval])

    # TODO: improve comment
    def reschedule_cards_according_to_average(self):
        # TODO: make nb_of_iteration an attribute of the class with its print function ?
        nb_of_iteration: Dict[int, int] = dict()
        # text_to_print = "Starting rescheduling"
        # text_to_print += f"\n For interval = {interval}, nb of iterations : "
        # text_to_print += f"{iteration} / compare to interval² = {interval * interval}"
        # text_to_print += "\n End of Rescheduling"

        for interval in range1(1, self.max_interval):
            iteration = 1
            while iteration < 3_000:
                (due_max_day, max_alg_difference) = self.find_highest_positive_difference_for_given_interval(interval)
                (due_min_day, min_alg_difference) = self.find_highest_negative_difference_for_given_interval(interval)

                # Condition to stop the algorithm
                if max_alg_difference <= 1 and min_alg_difference >= -1:
                    break
                if (max_alg_difference + min_alg_difference) < 0:
                    self.move_cards_to_due_day(interval, original_day=due_min_day, amount=-min_alg_difference)
                else:
                    self.move_cards_from_due_day(interval, original_day=due_max_day, amount=max_alg_difference)
                iteration += 1
            nb_of_iteration[interval] = iteration

    def find_highest_positive_difference_for_given_interval(self, interval) -> (int, int):
        return self.find_highest_difference_for_given_interval(interval, positive=True)

    def find_highest_negative_difference_for_given_interval(self, interval) -> (int, int):
        return self.find_highest_difference_for_given_interval(interval, positive=False)

    # needs to use "difference_of_cards_by_interval_by_due_date" which will be modified
    def find_highest_difference_for_given_interval(self, interval: int, positive: bool) -> (int, int):
        # We need to recalculate self.difference_of_cards_by_interval_by_due_date
        # TODO: Make it so that we only recalculate for a given interval
        self.calculate_difference_between_current_and_average_by_interval_by_due_day()
        difference_of_cards: Dict[int, int] = self.difference_of_cards_by_interval_by_due_date[interval]
        highest_difference = difference_of_cards[1]
        due_date_for_highest_difference = 1
        for current_due_date in range1(2, interval):
            # According to the value of positive, we search for highest positive or negative difference
            # TODO: create own boolean type for cleaner code
            if (positive and difference_of_cards[current_due_date] > highest_difference) or \
                    (not positive and difference_of_cards[current_due_date] < highest_difference):
                highest_difference = difference_of_cards[current_due_date]
                due_date_for_highest_difference = current_due_date
        return due_date_for_highest_difference, highest_difference

    def move_cards_from_due_day(self, interval: int, original_day: int, amount: int):
        self.move_cards_from_or_to_due_day(interval, original_day, amount, invert=False)

    def move_cards_to_due_day(self, interval: int, original_day: int, amount: int):
        self.move_cards_from_or_to_due_day(interval, original_day, amount, invert=True)

    def move_cards_from_or_to_due_day(self, interval: int, original_day: int, amount: int, invert: bool):
        assert amount > 0
        assert original_day >= 1
        assert original_day <= interval

        if original_day == 1:
            self.move_cards_from_original_to_target_day(interval, invert, amount,
                                                        original_day=1, target_day=2)
        elif original_day == interval:
            self.move_cards_from_original_to_target_day(interval, invert, amount,
                                                        original_day=interval, target_day=interval - 1)
        else:
            nb_1 = int(amount / 2)
            nb_2 = int(amount / 2) + amount % 1
            self.move_cards_from_original_to_target_day(interval, invert, amount=nb_1,
                                                        original_day=original_day, target_day=original_day - 1)
            self.move_cards_from_original_to_target_day(interval, invert, amount=nb_2,
                                                        original_day=original_day, target_day=original_day + 1)

    # TODO: improve comment
    # needs to use "cards_by_interval_by_due_date" which will be modified
    def move_cards_from_original_to_target_day(self, interval: int, invert: bool, amount: int,
                                               original_day: int, target_day: int):

        def move_cards_among_list(cards_to_move: List[Card], amount_to_move: int):
            if amount_to_move < len(cards_to_move):
                # TODO: Add a secondary method of choosing cards instead of just truncating (by ease for example)
                cards_to_move = cards_to_move[:amount_to_move]

            for card in cards_to_move:
                cards_for_original_day.remove(card)
                cards_for_target_day.append(card)

        # We need to find the cards which originally were the closest to target_day
        def get_cards_by_diff_between_target_and_first_original_due_date() -> Dict[int, List[Card]]:
            cards_by_diff_compute: Dict[int, List[Card]] = RescheduleDeck.init_dict_of_cards(range1(0, interval - 1))
            for card in cards_for_original_day:
                diff = abs(target_day - self.due_date_first_original_by_card[card])
                cards_by_diff_compute[diff].append(card)
            return cards_by_diff_compute

        # According to the value of invert, we either move cards to or from original_day
        # TODO: create own boolean type for cleaner code
        if invert:
            temp = original_day
            original_day = target_day
            target_day = temp

        cards_for_original_day: List[Card] = self.cards_by_interval_by_due_date[interval][original_day]
        cards_for_target_day: List[Card] = self.cards_by_interval_by_due_date[interval][target_day]

        if amount > len(cards_for_original_day):
            amount = len(cards_for_original_day)
            if amount == 0:
                # TODO: There are potential cases in which the algorithm can break if we only move cards once,
                # that is if we are on the "sides" of the due_date.
                return

        cards_by_diff: Dict[int, List[Card]] = get_cards_by_diff_between_target_and_first_original_due_date()

        # Find "amount_to_move" cards starting by cards_by_diff[0], then cards_by_diff[1], etc...
        number_of_moved_cards = 0
        iteration = 0
        while number_of_moved_cards != amount and iteration < interval:
            new_number_of_moved_cards = number_of_moved_cards + len(cards_by_diff[iteration])
            if new_number_of_moved_cards >= amount:
                number_of_cards_to_move = amount - number_of_moved_cards
                move_cards_among_list(cards_by_diff[iteration], amount_to_move=number_of_cards_to_move)
                break
            else:
                move_cards_among_list(cards_by_diff[iteration], amount_to_move=len(cards_by_diff[iteration]))
                number_of_moved_cards = new_number_of_moved_cards
            iteration += 1

        if iteration == interval:
            text = "Error, too many iterations in move_cards : "
            text += f"\n interval: {interval}, invert: {invert}, amount: {amount}"
            text += f", original_day: {original_day}, target_day: {target_day}"
            showInfo(text)
            self.print_difference()
            exit(1)

    # We get the new due_date from the modified "cards_by_interval_by_due_date"
    def determine_due_date_new_by_card(self) -> Dict[Card, int]:
        new_due_date_by_card: Dict[Card, int] = dict()
        for interval in range1(1, self.max_interval):
            for due_date in range1(1, interval):
                for card in self.cards_by_interval_by_due_date[interval][due_date]:
                    new_due_date_by_card[card] = due_date
        return new_due_date_by_card

    # We need to compare the due_date of cards in "due_date_first_original_by_card" and "due_date_new_by_card"
    def determine_cards_with_new_intervals(self):
        cards_with_new_intervals: Dict[Card, int] = dict()
        for card in self.cards:
            if self.due_date_first_original_by_card[card] != self.due_date_new_by_card[card]:
                cards_with_new_intervals[card] = self.due_date_new_by_card[card] + self.date_of_today
        return cards_with_new_intervals

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
            text += f"\n\n Nb of Cards for each due date in interval = {interval} "
            text += f", (average = {self.average_number_across_due_days[interval]}) :"
            for due_day in range1(1, interval):
                text += f"\n Nb of Cards for interval = {interval} and due date = {due_day} : "
                text += f"{str(len(self.cards_by_interval_by_due_date[interval][due_day]))}"
        showInfo(text)

    def print_average(self):
        text = "Computed average amount of cards across and due_days for a given interval"
        for interval in range1(1, self.max_interval):
            text += f"\n Average nb of cards for interval {interval} = "
            text += f"{self.average_number_across_due_days[interval]}"
        showInfo(text)

    def print_difference(self):
        text = "Computed difference of cards between current and average by interval and due_date"
        for interval in range1(1, self.max_interval):
            text += f"\n\n For interval = {interval}"
            text += f", total_number = {len(self.cards_by_interval[interval])}"
            text += f", average cards by day = {self.average_number_across_due_days[interval]} :"
            # TODO: add average difference by day
            for due_day in range1(1, interval):
                text += f"\n For interval '{interval}' and due_date '{due_day}'"
                text += f", number_of_cards = {len(self.cards_by_interval_by_due_date[interval][due_day])}"
                text += f", difference = {self.difference_of_cards_by_interval_by_due_date[interval][due_day]}"
        showInfo(text)


    # Access to self.cards_with_new_due_date, self.due_date_first_original_by_card, self.max_interval,
    # self.date_of_today, self.cards
    def print_distribution_of_cards_rescheduled(self):

        if len(self.cards_with_new_due_date) == 0:
            showInfo("No card to reschedule, your deck is perfect ! \\o")
            return

        cards_to_reschedule_by_diff_in_due_date: Dict[int, List[Card]] = RescheduleDeck. \
            init_dict_of_cards(range1(1, self.max_interval - 1))
        for card in self.cards_with_new_due_date:
            original_due_date = self.due_date_first_original_by_card[card]
            new_due_date = self.cards_with_new_due_date[card] - self.date_of_today
            difference = abs(new_due_date - original_due_date)
            assert difference > 0
            cards_to_reschedule_by_diff_in_due_date[difference].append(card)

        average_amount_of_rescheduling = 0
        for interval in range1(1, self.max_interval - 1):
            average_amount_of_rescheduling += interval * len(cards_to_reschedule_by_diff_in_due_date[interval])
        average_amount_of_rescheduling = average_amount_of_rescheduling / len(self.cards_with_new_due_date)
        average_amount_of_rescheduling = round(average_amount_of_rescheduling * 100) / 100
        percentage_of_card_rescheduled = round(len(self.cards_with_new_due_date) / len(self.cards) * 100 * 100) / 100

        text = "Distribution of cards rescheduled : "
        text += f"\n Total amount of cards in deck not new and not suspended = {len(self.cards)}"
        text += f"\n Total amount of cards rescheduled = {len(self.cards_with_new_due_date)}"
        text += f"\n Percentage of cards rescheduled = {percentage_of_card_rescheduled}%"
        text += f"\n Average days of rescheduling = {average_amount_of_rescheduling}"
        for interval in range1(1, self.max_interval - 1):
            if len(cards_to_reschedule_by_diff_in_due_date[interval]) > 0:
                text += f"\n  Amount of cards rescheduled by {interval} days : "
                text += f"{len(cards_to_reschedule_by_diff_in_due_date[interval])}"
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


def reorder_cards(cards_with_new_due_date: Dict[Card, int]) -> None:
    for card in cards_with_new_due_date:
        card.due = cards_with_new_due_date[card]
        card.flush()
    pass


def main_function() -> None:
    reorder_deck = RescheduleDeck(get_cards(), get_deck())
    reorder_cards(reorder_deck.cards_with_new_due_date)
    showInfo("Cards Successfully Rescheduled !!! \\dab")


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
