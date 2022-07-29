from typing import (
    List, Dict, Sequence, )

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QComboBox, QCheckBox, QGridLayout, QFrame, QSizePolicy, QLabel, QDialogButtonBox, \
    QSpinBox
from anki.cards import Card
from anki.cards import CardId
from anki.decks import DeckId, DeckDict
from aqt import mw
from aqt.utils import showInfo

# --- EXTERNAL VARIABLES ---#
NAME_OF_DECK_TO_RESCHEDULE = "JP - Kanji 2k RTK::JP - Kanji - Subdeck 2"
MAX_INTERVAL = 21
IS_RESCHEDULE_PAST_OVERDUE_CARDS = True

# --- INTERNAL VARIABLES ---#
DUE_ATTRIBUTE_OF_CARD_ABOVE_WHICH_CARD_IS_SUSPENDED = 1_000_000_000


# --- BEGINNING of ReorderDeck Class --- #


def range1(start, end):
    return range(start, end + 1)


# This class only contain the logic of the rescheduling.
# It does NOT modify cards (only adds new fields for simplicity, but even that could be avoided) !
# NO DATABASE ACCESS !
class RescheduleDeck:
    # --- "External" Variables (passed by arguments or by global variables)
    # (should not be modified once initialized) --- #
    cards: List[Card]
    deck: DeckDict
    sequence_of_intervals: Sequence[int]
    max_due: int
    is_reschedule_past_overdue_cards: bool
    # max_interval: int

    # --- Internal Variables not modified once initialized --- #
    date_of_today: int
    cards_by_interval: Dict[int, List[Card]] = dict()
    due_date_first_original_by_card: Dict[Card, int] = dict()
    average_number_of_cards_by_due_day: Dict[int, float] = dict()

    # --- Internal Variables modified by the algorithm --- #
    cards_by_interval_by_due_day: Dict[int, Dict[int, List[Card]]] = dict()
    difference_of_cards_by_interval_by_due_date: Dict[int, Dict[int, int]] = dict()

    # --- Internal Variables used after the algorithm as a result (not modified once initialized) --- #
    due_date_new_by_card: Dict[Card, int]
    cards_with_new_due_date: Dict[Card, int]

    # TODO: improve comment
    def __init__(self, cards: Sequence[Card], deck: DeckDict, sequence_of_intervals: Sequence[int]) -> None:
        # Initialization of "External" Variables
        self.cards = list(cards)
        self.deck = deck
        # self.max_interval = MAX_INTERVAL
        self.sequence_of_intervals = sequence_of_intervals
        self.max_due = DUE_ATTRIBUTE_OF_CARD_ABOVE_WHICH_CARD_IS_SUSPENDED
        self.is_reschedule_past_overdue_cards = IS_RESCHEDULE_PAST_OVERDUE_CARDS

        # Preparation of Internal Variables for later use by the rescheduling algorithm
        self.date_of_today = self.retrieve_date_of_today(deck)
        self.exclude_irrelevant_cards()
        self.cards_by_interval = RescheduleDeck.init_dict_of_cards(self.sequence_of_intervals)
        self.sort_cards_by_interval()
        self.cards_by_interval_by_due_day = RescheduleDeck.init_dict_of_dict_of_cards(self.sequence_of_intervals)
        self.sort_cards_by_interval_by_due_date_and_saves_original_due_date()
        self.calculate_average_number_by_due_day()
        self.calculate_difference_between_current_and_average_due_date()

        # self.print_cards_by_interval()
        # self.print_cards_by_interval_by_due_date()
        # self.print_average()
        # self.print_difference()

        # Algorithm
        self.reschedule_cards_according_to_average()

        # After algorithm
        self.due_date_new_by_card = self.determine_due_date_new_by_card()
        self.cards_with_new_due_date = self.determine_cards_with_new_intervals()
        # self.print_distribution_of_cards_rescheduled()

    # --- Initialization Functions of ReorderDeck Class --- #

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
    def retrieve_date_of_today(deck) -> int:
        return deck.pop("timeToday")[0]

    def exclude_irrelevant_cards(self) -> None:
        cards_to_remove: List[Card] = list()
        for card in self.cards:
            # If card not in the desired intervals, we don't keep it
            # (This includes cards considered as new because they don't have an interval yet)
            card_interval: int = RescheduleDeck.get_interval(card)
            if card_interval not in self.sequence_of_intervals:
                cards_to_remove.append(card)

            # If card suspended (due > max_due), we don't keep it
            # TODO: Check (This apparently includes cards in failed status => ???????)
            if card.due > self.max_due:
                cards_to_remove.append(card)

            # If card past overdue and we don't want to reschedule them, we don't keep it
            due_day: int = self.get_due_day(card)
            if due_day <= 0 and not self.is_reschedule_past_overdue_cards:
                cards_to_remove.append(card)

        new_card_list: List[Card] = [card for card in self.cards if card not in cards_to_remove]
        self.cards = list(new_card_list)

    def sort_cards_by_interval(self) -> None:
        for card in self.cards:
            interval = RescheduleDeck.get_interval(card)
            self.cards_by_interval[interval].append(card)

    @staticmethod
    def get_interval(card: Card):
        return card.ivl

    def sort_cards_by_interval_by_due_date_and_saves_original_due_date(self) -> None:
        for interval in self.sequence_of_intervals:
            cards_for_given_interval: List[Card] = self.cards_by_interval[interval]
            for card in cards_for_given_interval:
                due_day: int = self.get_due_day(card)
                self.due_date_first_original_by_card[card] = due_day
                # If card is past overdue, we automatically reschedule it to due tomorrow
                if due_day <= 0:
                    due_day = 1
                self.cards_by_interval_by_due_day[interval][due_day].append(card)

    def get_due_day(self, card: Card) -> int:
        return card.due - self.date_of_today

    # TODO: improve comment
    def calculate_average_number_by_due_day(self):
        for interval in self.sequence_of_intervals:
            total_cards: int = 0
            cards_by_due_day: Dict[int, List[Card]] = self.cards_by_interval_by_due_day[interval]
            for due_day in range1(1, interval):
                total_cards += len(cards_by_due_day[due_day])
            self.average_number_of_cards_by_due_day[interval] = round(100 * total_cards / interval) / 100

    # TODO: improve comment
    def calculate_difference_between_current_and_average_due_date(self):
        for interval in self.sequence_of_intervals:
            self.difference_of_cards_by_interval_by_due_date[interval]: Dict[int, int] = dict()
            cards_by_due_day: Dict[int, List[Card]] = self.cards_by_interval_by_due_day[interval]
            for due_day in range1(1, interval):
                self.difference_of_cards_by_interval_by_due_date[interval][due_day] = \
                    round(len(cards_by_due_day[due_day]) - self.average_number_of_cards_by_due_day[interval])

    # --- "Algorithm" Functions of ReorderDeck Class --- #

    # Core function of the Algorithm for rescheduling cards
    # TODO: improve comment
    def reschedule_cards_according_to_average(self):
        # TODO: make nb_of_iteration an attribute of the class with its print function ?
        nb_of_iteration: Dict[int, int] = dict()

        for interval in self.sequence_of_intervals:
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

    # TODO: improve comment
    # needs to use "difference_of_cards_by_interval_by_due_date" which will be modified
    def find_highest_difference_for_given_interval(self, interval: int, positive: bool) -> (int, int):
        # We need to recalculate self.difference_of_cards_by_interval_by_due_date
        # TODO: Make it so that we only recalculate for a given interval
        self.calculate_difference_between_current_and_average_due_date()
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

    # TODO: improve comment
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

    # TODO: REFACTOR
    # TODO: improve comment
    # needs to use "cards_by_interval_by_due_day" which will be modified
    def move_cards_from_original_to_target_day(self, interval: int, invert: bool, amount: int,
                                               original_day: int, target_day: int):

        # TODO: improve comment
        def move_cards_among_list(cards_to_move: List[Card], amount_to_move: int):
            if amount_to_move < len(cards_to_move):
                # TODO: Add a secondary method of choosing cards instead of just truncating (by ease for example)
                cards_to_move = cards_to_move[:amount_to_move]

            for card in cards_to_move:
                cards_for_original_day.remove(card)
                cards_for_target_day.append(card)

        # TODO: improve comment
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

        cards_for_original_day: List[Card] = self.cards_by_interval_by_due_day[interval][original_day]
        cards_for_target_day: List[Card] = self.cards_by_interval_by_due_day[interval][target_day]

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

    # --- "Result" Functions of ReorderDeck Class --- #

    # We determine the new due_day from "cards_by_interval_by_due_day" modified by the algorithm
    def determine_due_date_new_by_card(self) -> Dict[Card, int]:
        new_due_date_by_card: Dict[Card, int] = dict()
        for interval in self.sequence_of_intervals:
            for due_day in range1(1, interval):
                for card in self.cards_by_interval_by_due_day[interval][due_day]:
                    new_due_date_by_card[card] = due_day
        return new_due_date_by_card

    # We determine the cards which need to be rescheduled by comparing the original and latest due_day
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

    # TODO: improve comment
    def print_cards_by_interval(self):
        text = "Nb of Cards for each interval"
        for interval in self.sequence_of_intervals:
            text += f"\n Nb of Cards for interval {interval} = "
            text += f"{str(len(self.cards_by_interval[interval]))}"
        showInfo(text)

    # TODO: improve comment
    def print_cards_by_interval_by_due_date(self):
        text = "Nb of Cards for each interval and each due date"
        for interval in self.sequence_of_intervals:
            text += f"\n\n Nb of Cards for each due date in interval = {interval} "
            text += f", (average = {self.average_number_of_cards_by_due_day[interval]}) :"
            for due_day in range1(1, interval):
                text += f"\n Nb of Cards for interval = {interval} and due date = {due_day} : "
                text += f"{str(len(self.cards_by_interval_by_due_day[interval][due_day]))}"
        showInfo(text)

    # TODO: improve comment
    def print_average(self):
        text = "Computed average amount of cards across and due_days for a given interval"
        for interval in self.sequence_of_intervals:
            text += f"\n Average nb of cards for interval {interval} = "
            text += f"{self.average_number_of_cards_by_due_day[interval]}"
        showInfo(text)

    # TODO: improve comment
    def print_difference(self):
        text = "Computed difference of cards between current and average by interval and due_date"
        for interval in self.sequence_of_intervals:
            text += f"\n\n For interval = {interval}"
            text += f", total_number = {len(self.cards_by_interval[interval])}"
            text += f", average cards by day = {self.average_number_of_cards_by_due_day[interval]} :"
            # TODO: add average difference by day
            for due_day in range1(1, interval):
                text += f"\n For interval '{interval}' and due_date '{due_day}'"
                text += f", number_of_cards = {len(self.cards_by_interval_by_due_day[interval][due_day])}"
                text += f", difference = {self.difference_of_cards_by_interval_by_due_date[interval][due_day]}"
        showInfo(text)

    # Access to self.cards_with_new_due_date, self.due_date_first_original_by_card, self.max_interval,
    # self.date_of_today, self.cards
    # TODO: improve comment
    # TODO: REFACTOR
    def print_distribution_of_cards_rescheduled(self) -> str:

        if len(self.cards_with_new_due_date) == 0:
            return ""

        cards_to_reschedule_by_diff_in_due_date: Dict[int, List[Card]] = RescheduleDeck. \
            init_dict_of_cards(self.sequence_of_intervals)
        for card in self.cards_with_new_due_date:
            original_due_date = self.due_date_first_original_by_card[card]
            new_due_date = self.cards_with_new_due_date[card] - self.date_of_today
            difference = abs(new_due_date - original_due_date)
            assert difference > 0
            cards_to_reschedule_by_diff_in_due_date[difference].append(card)

        average_amount_of_rescheduling = 0
        for interval in self.sequence_of_intervals:
            average_amount_of_rescheduling += interval * len(cards_to_reschedule_by_diff_in_due_date[interval])
        average_amount_of_rescheduling = average_amount_of_rescheduling / len(self.cards_with_new_due_date)
        average_amount_of_rescheduling = round(average_amount_of_rescheduling * 100) / 100
        percentage_of_card_rescheduled = round(len(self.cards_with_new_due_date) / len(self.cards) * 100 * 100) / 100

        text = "Distribution of cards rescheduled : "
        text += f"\n Total amount of cards in deck not new and not suspended = {len(self.cards)}"
        text += f"\n Total amount of cards rescheduled = {len(self.cards_with_new_due_date)}"
        text += f"\n Percentage of cards rescheduled = {percentage_of_card_rescheduled}%"
        text += f"\n Average days of rescheduling = {average_amount_of_rescheduling}"
        for interval in self.sequence_of_intervals:
            if len(cards_to_reschedule_by_diff_in_due_date[interval]) > 0:
                text += f"\n  Amount of cards rescheduled by {interval} days : "
                text += f"{len(cards_to_reschedule_by_diff_in_due_date[interval])}"
        return text

    def print_final_message(self) -> str:
        if (len(self.cards_with_new_due_date)) > 0:
            return "Cards Successfully Rescheduled !!! \\dab"
        else:
            return "No card to reschedule, your deck is perfect ! \\o"


# --- END of ReorderDeck Class --- #

# a horizontal separation line\n
class QHSeparationLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(1)
        self.setFixedHeight(20)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)


class DialogRescheduleDeck(QDialog):
    def __init__(self, parent=mw):
        super(DialogRescheduleDeck, self).__init__(parent)

        self.setWindowTitle("Reschedule Deck")
        self.setWindowFlags(Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint)

        self._deck_chooser = QComboBox()
        self._deck_chooser.addItem('Whole Collection', None)
        decks = {item["name"]: item["id"] for item in mw.col.decks.all()}
        for name in sorted(decks.keys()):
            self._deck_chooser.addItem(name, decks[name])
        self._deck_chooser.activated.connect(self._changed)

        self._min_interval = self._spinbox(1, '1 is the minimum value possible')
        self._max_interval = self._spinbox(21,
                                           '21 is the default value for which cards are considered mature (author\'s max interval value in their deck)')

        self._is_reschedule_overdue_cards = QCheckBox()
        self._is_reschedule_overdue_cards.setChecked(False)

        self._is_dry_run = QCheckBox()
        self._is_dry_run.setChecked(True)

        self._explanation = QLabel()
        self._explanation.setWordWrap(True)
        self._changed()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QGridLayout()
        layout.addWidget(self._label('Deck: '), 0, 0)
        layout.addWidget(self._deck_chooser, 0, 1, 1, 2)
        layout.addWidget(self._label('Minimum interval: '), 1, 0)
        layout.addWidget(self._max_interval, 1, 1)
        layout.addWidget(self._label('Maximum interval: '), 2, 0)
        layout.addWidget(self._min_interval, 2, 1)
        layout.addWidget(self._label('Reschedule overdue cards: '), 3, 0)
        layout.addWidget(self._is_reschedule_overdue_cards, 3, 1)
        layout.addWidget(self._label('Dry run (do not actually reschedule): '), 4, 0)
        layout.addWidget(self._is_dry_run, 4, 1)

        layout.addWidget(QHSeparationLine(), 5, 0, 1, 3)
        layout.addWidget(self._explanation, 6, 0, 1, 3)
        layout.addWidget(QLabel('<font color=red>This action cannot be undone.</font>'), 7, 0, 1, 3)
        layout.addWidget(QHSeparationLine(), 8, 0, 1, 3)
        layout.addWidget(button_box, 9, 0, 1, 3)
        self.setLayout(layout)

    def _spinbox(self, value, tooltip):
        spinbox = QSpinBox()
        spinbox.setRange(1, 9_999)
        spinbox.setValue(value)
        spinbox.setSingleStep(1)
        spinbox.setToolTip(tooltip)
        spinbox.valueChanged.connect(self._changed)
        return spinbox

    def _label(self, text):
        label = QLabel(text)
        label.setFixedWidth(90)
        return label

    def _changed(self):
        # old_ease_specified = self._operator.currentData() is not None
        # (sql, params) = self.sql('count(*)')
        # n = mw.col.db.scalar(sql, *params)
        # d = 'the {0} deck'.format(self._deck_chooser.currentText()) if self._deck_chooser.currentData() else 'any deck'
        # e = 'an ease {0} {1}%'.format(self._operator.currentText(), self._old_ease.value()) if old_ease_specified else 'a different ease'
        # s = 'Press OK to change the ease to {0}% for the {1} cards in {2} which currently have {3}.\n'.format(self.new_ease(), n, d, e)
        # self._explanation.setText(s)
        # self._old_ease.setEnabled(old_ease_specified)
        # self._old_ease.setVisible(old_ease_specified)
        self._explanation.setText("Yoooo")


# --- FUNCTIONS ---#


def get_cards() -> List[Card]:
    deck_id: DeckId = mw.col.decks.id_for_name(NAME_OF_DECK_TO_RESCHEDULE)
    card_ids: List[CardId] = mw.col.decks.cids(deck_id, children=True)
    return [mw.col.get_card(card_id) for card_id in card_ids]


def get_deck() -> DeckDict:
    return mw.col.decks.by_name(NAME_OF_DECK_TO_RESCHEDULE)


def reorder_cards(cards_with_new_due_date: Dict[Card, int]) -> None:
    for card in cards_with_new_due_date:
        card.due = cards_with_new_due_date[card]
        card.flush()
    pass


def main_function() -> None:
    reschedule_dialog = DialogRescheduleDeck()
    if reschedule_dialog.exec():
        reorder_deck = RescheduleDeck(get_cards(), get_deck(), range1(1, MAX_INTERVAL))
        # reorder_cards(reorder_deck.cards_with_new_due_date)
        showInfo(reorder_deck.print_distribution_of_cards_rescheduled())
        showInfo(reorder_deck.print_final_message())
        #reschedule_dialog._explanation.setText(text)
        #reschedule_dialog.ac()

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
