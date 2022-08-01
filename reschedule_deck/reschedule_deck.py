from typing import (
    List, Dict, Sequence, Union, )

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
# NAME_OF_DECK_TO_RESCHEDULE = "JP - Kanji 2k RTK::JP - Kanji - Subdeck 2"
# MAX_INTERVAL = 21
# IS_RESCHEDULE_PAST_OVERDUE_CARDS = True
DEFAULT_MIN_VALUE_IN_RANGE = 1
DEFAULT_MAX_VALUE_IN_RANGE = 21
DEFAULT_DRY_RUN = True
DEFAULT_RESCHEDULE_OVERDUE_CARDS = False

# --- INTERNAL VARIABLES ---#
# Custom Classes
Average = Union[int, float]
# ??
DUE_ATTRIBUTE_OF_CARD_ABOVE_WHICH_CARD_IS_SUSPENDED = 1_000_000_000
MAX_ITERATION_IN_MAIN_ALGORITHM = 1_500

# Stuff to simplify Testing
SHOW_EVERY_ITERATION = False
USE_ALGORITHM_1_BY_HIGHEST_DIFFERENCE = True

# --- BEGINNING of ReorderDeck Class --- #


# This class only contain the logic of the rescheduling.
# It does NOT modify cards (only adds new fields for simplicity, but even that could be avoided) !
# NO DATABASE ACCESS !
class RescheduleDeck:
    # --- "External" Variables (passed by arguments or by global variables) (not be modified once initialized) --- #
    deck: DeckDict
    cards: List[Card]
    sequence_of_intervals: Sequence[int]
    is_reschedule_past_overdue_cards: bool
    max_due: int

    # --- Internal Variables needed for the algorithm (not modified once initialized) --- #
    number_of_cards_over_scheduled: int = 0
    number_of_cards_overdue_only_for_reviews_queue_2: int = 0
    number_of_cards_overdue_only_for_learning_queue_1: int = 0
    number_of_cards_overdue_only_for_learning_queue_3: int = 0
    number_of_cards_overdue_only_for_buried_queue_minus_3: int = 0
    max_interval: int
    day_of_today: int
    cards_by_interval: Dict[int, List[Card]] = dict()
    cards_with_first_original_due_day: Dict[Card, int] = dict()
    average_number_of_cards_by_interval: Dict[int, Average] = dict()
    cards_original_by_interval_by_due_day: Dict[int, Dict[int, List[Card]]] = dict()
    difference_original_of_cards_by_interval_by_due_day: Dict[int, Dict[int, int]] = dict()

    # --- Internal Variables modified by the algorithm after their first initialization--- #
    number_of_iterations_of_main_algorithm: Dict[int, int] = dict()
    cards_target_by_interval_by_due_day: Dict[int, Dict[int, List[Card]]] = dict()
    difference_target_of_cards_by_interval_by_due_day: Dict[int, Dict[int, int]] = dict()

    # --- Internal Variables used after the algorithm as a result (not modified once initialized) --- #
    cards_with_only_different_new_due_day: Dict[Card, int]

    def __init__(self, deck: DeckDict, cards: Sequence[Card],
                 sequence_of_intervals: Sequence[int],
                 is_reschedule_overdue_cards: bool) -> None:

        # Initialization of "External" Variables (passed by arguments or by global variables)
        self.deck = deck
        self.cards = list(cards)
        self.sequence_of_intervals = sequence_of_intervals
        self.is_reschedule_past_overdue_cards = is_reschedule_overdue_cards
        self.max_due = DUE_ATTRIBUTE_OF_CARD_ABOVE_WHICH_CARD_IS_SUSPENDED

        # Preparation of Internal Variables for later use by the rescheduling algorithm
        self.max_interval = RescheduleDeck.get_maximum_interval(self.sequence_of_intervals)
        self.day_of_today = self.retrieve_date_of_today(deck)
        self.exclude_irrelevant_cards_and_modify_others()
        self.cards_by_interval = RescheduleDeck.init_dict_of_cards(self.sequence_of_intervals)
        self.sort_cards_by_interval()
        self.cards_original_by_interval_by_due_day = RescheduleDeck.init_dict_of_dict_of_cards(
            self.sequence_of_intervals)
        self.cards_target_by_interval_by_due_day = RescheduleDeck.init_dict_of_dict_of_cards(self.sequence_of_intervals)
        self.sort_cards_by_interval_by_due_day_and_saves_original_due_day(self.cards_original_by_interval_by_due_day)
        self.sort_cards_by_interval_by_due_day_and_saves_original_due_day(self.cards_target_by_interval_by_due_day)
        self.calculate_average_number_by_due_day()
        self.calculate_difference_between_current_and_average_due_day()
        self.difference_original_of_cards_by_interval_by_due_day = dict(
            self.difference_target_of_cards_by_interval_by_due_day)

        # Algorithm
        if USE_ALGORITHM_1_BY_HIGHEST_DIFFERENCE:
            self.reschedule_cards_algorithm_1_by_highest_difference()
        # else:
        #     self.reschedule_cards_algorithm_2_by_left_to_right()

        # After algorithm
        self.cards_with_only_different_new_due_day = self.determine_cards_with_only_different_new_due_day()

        # self.print_cards_by_interval()
        # self.print_cards_by_interval_by_due_day()
        # self.print_average()
        # self.print_difference()
        # self.print_distribution_of_cards_rescheduled()

    # --- Initialization Functions of ReorderDeck Class --- #

    @staticmethod
    def get_maximum_interval(sequence_of_intervals: Sequence[int]) -> int:
        max_interval = sequence_of_intervals[0]
        for interval in sequence_of_intervals:
            if interval >= max_interval:
                max_interval = interval
        return max_interval

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
        return deck.get("timeToday")[0]

    # queue = integer
    # -- -3=user buried(In scheduler 2),
    # -- -2=sched buried (In scheduler 2),
    # -- -2=buried(In scheduler 1),
    # -- -1=suspended,
    # -- 0=new, 1=learning, 2=review (as for type)
    # -- 3=in learning, next rev in at least a day after the previous review
    # -- 4=preview

    # type = integer -- 0 = new, 1 = learning, 2 = review, 3 = relearning
    # Exclude
    def exclude_irrelevant_cards_and_modify_others(self) -> None:
        cards_to_remove: List[Card] = list()
        for card in self.cards:
            # If card not in the desired intervals, we don't keep it
            # (This includes cards considered as new because they don't have an interval yet)
            card_interval: int = RescheduleDeck.get_interval(card)
            card_due_day: int = self.get_due_day(card)
            card_queue: int = card.queue
            card_type: int = card.type

            try:
                # Make assertions on the state of the card for the algorithm to be able to work
                if card_queue == -3:
                    assert card_due_day > self.max_due
                    pass
                if card_queue == -2:
                    assert card_due_day > 0
                    assert card_due_day <= card_interval
                if card_queue == 0:
                    assert card_type == 0
                if card_queue == 1:
                    assert card_type in (1, 3)
                    assert card_due_day > self.max_due
                if card_queue == 2:
                    assert card_type == 2
                    assert card_due_day >= -self.day_of_today
                    assert card_due_day < self.max_due
                if card_queue == 3:
                    assert card_type in (1, 3)
                    assert card_due_day < self.max_due
                if card_queue == 4:
                    # ??
                    pass
            except AssertionError as error:
                showInfo(f"Unexpected {error=}")
                self.show_card_and_note_info(card)
                raise

            # If card is suspended or new, we don't keep it
            if card_queue in (-1, 0):
                cards_to_remove.append(card)
                continue

            # If card is review or relearn, and card_interval not in the desired range of values, we don't keep it
            if card_queue in (2, 3) and card_interval not in self.sequence_of_intervals:
                cards_to_remove.append(card)
                continue

            if card_queue == 2 and card_due_day <= 0:
                self.number_of_cards_overdue_only_for_reviews_queue_2 += 1

            if card_queue == 1:
                self.number_of_cards_overdue_only_for_learning_queue_1 += 1

            if card_queue == 3 and card_due_day <= 0:
                self.number_of_cards_overdue_only_for_learning_queue_3 += 1

            if card_queue == -3:
                self.number_of_cards_overdue_only_for_buried_queue_minus_3 += 1

            # If card is past overdue and we don't want to reschedule the latter, we don't keep it
            if not self.is_reschedule_past_overdue_cards:
                if (card_queue in (2, 3) and card_due_day <= 0) or card_queue in (-3, 1):
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

    # TODO: split this method in two, one for updating and saving original_due_day, another for the sort
    def sort_cards_by_interval_by_due_day_and_saves_original_due_day(self,
                                                                     cards: Dict[int, Dict[int, List[Card]]]) -> None:
        number_of_cards_over_scheduled = 0
        for interval in self.sequence_of_intervals:
            cards_for_given_interval: List[Card] = self.cards_by_interval[interval]
            for card in cards_for_given_interval:
                due_day = 0  # IDE whines because of the "except" clause and due_day being potentially not defined
                try:
                    card_queue: int = card.queue
                    due_day: int = self.get_due_day(card)

                    # If card is learning, or card is review and past overdue,
                    # => we set its original due_day to today and reschedule it to tomorrow
                    if card_queue == 1 or (card_queue == 2 and due_day <= 0):
                        self.cards_with_first_original_due_day[card] = 0
                        cards[interval][1].append(card)

                    # If card is over-scheduled
                    # => we set its original due_day to "interval" and reschedule it to "interval" days
                    # TODO: set original due_day to "interval + 1" (similar to past overdue cards), and modify the appropriate ranges in dictionaries
                    elif due_day > interval:
                        # TODO : There seems to be a bug in my deck where this condition is true while it shouldn't (and the browser window says it's not)
                        # TODO: Look at the way the browser retrieves the due day
                        self.cards_with_first_original_due_day[card] = interval
                        cards[interval][interval].append(card)
                        # TODO: Save those cards somewhere and show them
                        number_of_cards_over_scheduled += 1

                    else:
                        self.cards_with_first_original_due_day[card] = due_day
                        cards[interval][due_day].append(card)

                except KeyError:
                    showInfo(f"interval = {interval}, due_day = {due_day}, today = {self.day_of_today}")
                    self.show_card_and_note_info(card)
                    self.cards.remove(card)

    def get_due_day(self, card: Card) -> int:
        return card.due - self.day_of_today

    # --- "Algorithm" Functions of ReorderDeck Class --- #

    def calculate_average_number_by_due_day(self):
        for interval in self.sequence_of_intervals:
            total_cards: int = 0
            cards_by_due_day: Dict[int, List[Card]] = self.cards_original_by_interval_by_due_day[interval]
            for due_day in range1(1, interval):
                total_cards += len(cards_by_due_day[due_day])
            if total_cards % interval == 0:
                self.average_number_of_cards_by_interval[interval] = total_cards // interval
            else:
                self.average_number_of_cards_by_interval[interval] = round(total_cards / interval, 2)

    @staticmethod
    def is_average_between_0_excluded_and_point_5_excluded(average_: Average) -> bool:
        return not RescheduleDeck.is_integer(average_) and RescheduleDeck.is_between_0_included_and_point_5_excluded(
            average_)

    @staticmethod
    def is_integer(average_: Average) -> bool:
        return isinstance(average_, int)

    @staticmethod
    def is_between_0_included_and_point_5_excluded(average_: Average) -> bool:
        return int(average_) == round(average_)

    @staticmethod
    def is_between_point5_included_and_one_excluded(average_: Average) -> bool:
        return int(average_) != round(average_)

    # TODO: Make it so that we only recalculate for a given interval
    def calculate_difference_between_current_and_average_due_day(self):

        # If DIFFERENCE > 0
        # If decimal part of average is between 0.5 (included) and 1.0 (included),
        # we need to move cards when max_alg_difference >= 1 until max_alg_difference <= 0,
        # else if average decimal part between 0.0 (not included) and 0.5 (not included),
        # we need to move cards when max_alg_difference >= 2 until max_alg_difference <= 1,
        # In other words, in the second case, we can decrease max_alg_difference by 1,
        # so that in both cases we only need to move the cards when
        # max_alg_difference >= 1 until max_alg_difference = 0,
        def is_difference_to_be_decreased_when_pos(average_: Average) -> bool:
            return RescheduleDeck.is_average_between_0_excluded_and_point_5_excluded(average_)

        # Opposite if difference < 0
        # TODO: SOMETHING SEEMS TO BE WRONG FOR 0.5 VALUES OF AVERAGE
        #  (if average = 2.5, if nb_cards = 4 then diff = 2, but if nb_cards = 1 then diff = -1 and not -2 ??
        def is_difference_to_be_increased_when_neg(average_: Average) -> bool:
            return RescheduleDeck.is_between_point5_included_and_one_excluded(average_)

        for interval in self.sequence_of_intervals:
            self.difference_target_of_cards_by_interval_by_due_day[interval]: Dict[int, int] = dict()
            cards_by_due_day: Dict[int, List[Card]] = self.cards_target_by_interval_by_due_day[interval]
            average: Average = self.average_number_of_cards_by_interval[interval]
            is_difference_to_be_decreased_when_positive = is_difference_to_be_decreased_when_pos(average)
            is_difference_to_be_increased_when_negative = is_difference_to_be_increased_when_neg(average)
            for due_day in range1(1, interval):
                difference = round(len(cards_by_due_day[due_day]) - self.average_number_of_cards_by_interval[interval])
                if difference > 0 and is_difference_to_be_decreased_when_positive:
                    difference -= 1
                if difference < 0 and is_difference_to_be_increased_when_negative:
                    difference += 1
                self.difference_target_of_cards_by_interval_by_due_day[interval][due_day] = difference

    # Core function of the Algorithm number 2 (by sides) for rescheduling cards
    def reschedule_cards_algorithm_2_by_left_to_right(self):
        for interval in self.sequence_of_intervals:
            difference_of_cards_by_due_day: Dict[int, int] = self.difference_target_of_cards_by_interval_by_due_day[
                interval]
            average = self.average_number_of_cards_by_interval[interval]
            is_average_floor = round(average) == int(average)
            # If is_average_floor true, then break condition is difference = 0 or 1
            # Else break condition is difference = -1 or 0
            for due_day in range1(1, interval - 1):
                difference = difference_of_cards_by_due_day[due_day]

                # We fine-tune difference so that we don't move cards with a difference closer to average than 1
                if (difference > 0 and is_average_floor):
                    difference -= 1
                if (difference < 0 and not is_average_floor):
                    difference += 1

                if (difference > 0):
                    # In this case, we only need to move cards from the current to the next due_day
                    self.move_cards_from_original_to_target_day(interval, amount=difference,
                                                                original_day=due_day, target_day=due_day + 1)
                elif difference < 0:
                    # In this case, we need to move cards from the superior due_days to the current due_day until enough have been moved
                    difference = abs(difference)
                    number_of_moved_cards = 0
                    next_due_day = due_day + 1
                    while next_due_day < interval:
                        next_difference = abs(difference_of_cards_by_due_day[due_day])
                        next_number_of_moved_cards = number_of_moved_cards + next_difference
                        if (next_number_of_moved_cards >= difference):
                            number_of_cards_to_move = difference - number_of_moved_cards
                            self.move_cards_from_original_to_target_day(interval, amount=number_of_cards_to_move,
                                                                        original_day=next_due_day, target_day=due_day)
                            break
                        else:
                            self.move_cards_from_original_to_target_day(interval, amount=next_difference,
                                                                        original_day=next_due_day, target_day=due_day)
                            number_of_moved_cards = next_number_of_moved_cards
                            next_due_day += 1
                    if (next_due_day == interval):
                        text = f"Error, we can't find enough cards in the following due_days to move to "
                        text += f" the current due day {due_day} in interval {interval}"
                        showInfo(text)
                        self.show_both_original_and_target_cards_by_interval_by_due_day()
                        raise

    # Core function of the Algorithm number 1 (by highest difference) for rescheduling cards
    def reschedule_cards_algorithm_1_by_highest_difference(self):

        # --- Internal Methods of the Core Algorithm --- #

        def find_highest_positive_absolute_difference() -> (int, int):
            return find_highest_absolute_difference(positive=True)

        def find_highest_negative_absolute_difference() -> (int, int):
            return find_highest_absolute_difference(positive=False)

        # needs to use "difference_target_of_cards_by_interval_by_due_day" which is modified at each iteration of the main algorithm
        def find_highest_absolute_difference(positive: bool) -> (int, int):
            difference_of_cards: Dict[int, int] = self.difference_target_of_cards_by_interval_by_due_day[interval]
            due_day_for_highest_difference = 1
            highest_difference = difference_of_cards[1]
            for current_due_day in range1(2, interval):
                # According to the value of positive, we search for highest positive or negative difference
                # TODO: create own boolean type for cleaner code
                if (positive and difference_of_cards[current_due_day] > highest_difference) or \
                        (not positive and difference_of_cards[current_due_day] < highest_difference):
                    due_day_for_highest_difference = current_due_day
                    highest_difference = difference_of_cards[current_due_day]
            return due_day_for_highest_difference, highest_difference

        def find_highest_negative_algebraic_difference() -> int:
            average = self.average_number_of_cards_by_interval[interval]
            cards_by_due_day: Dict[int, List[Card]] = self.cards_target_by_interval_by_due_day[interval]
            min_due_day = 1
            highest_difference = len(cards_by_due_day[1]) - average
            for current_due_day in range1(2, interval):
                current_difference = len(cards_by_due_day[current_due_day]) - average
                if current_difference < highest_difference:
                    min_due_day = current_due_day
                    highest_difference = current_difference
            return min_due_day

        def find_highest_positive_algebraic_difference_closest_to_min_value(min_due_day: int) -> int:
            average = self.average_number_of_cards_by_interval[interval]
            cards_by_due_day: Dict[int, List[Card]] = self.cards_target_by_interval_by_due_day[interval]
            max_due_day = 1
            highest_difference = len(cards_by_due_day[1]) - average
            closest_distance = abs(max_due_day - min_due_day)
            for current_due_day in range1(2, interval):
                current_difference = len(cards_by_due_day[current_due_day]) - average
                current_distance = abs(current_due_day - min_due_day)
                condition_for_highest: bool = (current_difference > highest_difference)
                condition_for_closest: bool = (current_difference == highest_difference and
                                               current_distance < closest_distance)
                if condition_for_highest or condition_for_closest:
                    max_due_day = current_due_day
                    highest_difference = current_difference
                    closest_distance = current_distance
            assert max_due_day != min_due_day
            return max_due_day

        # Is moving from max_due_day to min_due_day moving towards increasing due_days ?
        def is_move_right(max_due_day, min_due_day) -> bool:
            assert max_due_day != min_due_day
            if max_due_day < min_due_day:
                return True
            else:
                return False

        # TODO: add comment
        def move_cards_from_due_day(original_day: int, amount: int):

            assert original_day >= 1
            assert original_day <= interval
            assert amount > 0

            if amount == 1:
                showInfo(f"Trying to move only 1 card : we shouldn't use the current method + {__name__}")
                self.show_both_original_and_target_difference()
                exit(1)

            if original_day == 1:
                self.move_cards_from_original_to_target_day(interval, amount,
                                                            original_day=1, target_day=2)
            elif original_day == interval:
                self.move_cards_from_original_to_target_day(interval, amount,
                                                            original_day=interval, target_day=interval - 1)
            else:
                absolute_half = int(amount / 2)
                self.move_cards_from_original_to_target_day(interval, amount=absolute_half,
                                                            original_day=original_day, target_day=original_day - 1)
                self.move_cards_from_original_to_target_day(interval, amount=absolute_half,
                                                            original_day=original_day, target_day=original_day + 1)

        def show_error_message_of_main_algorithm_and_exits():
            text = "Problem in main algorithm : limit of expected maximum iterations broken through"
            for interval_2 in self.sequence_of_intervals:
                text += f"\n Number of iterations for interval {interval_2} : "
                text += f"{self.number_of_iterations_of_main_algorithm[interval_2]}"
            showInfo(text)
            self.show_both_original_and_target_difference()
            exit(1)

        # --- Actual Beginning of the Core Algorithm --- #

        # TODO: find a formula for max number of iterations possible (use worst case scenario)
        for interval in self.sequence_of_intervals:
            self.number_of_iterations_of_main_algorithm[interval] = 0

        for interval in self.sequence_of_intervals:
            iteration = 1

            max_iteration_for_current_range = MAX_ITERATION_IN_MAIN_ALGORITHM
            # TODO: add comment about how the main algorithm works
            while iteration < max_iteration_for_current_range:

                if SHOW_EVERY_ITERATION:
                    showInfo(self.print_difference_target())

                (due_max_day, max_alg_difference) = find_highest_positive_absolute_difference()
                (due_min_day, min_alg_difference) = find_highest_negative_absolute_difference()

                # Determine if we need to stop the main algorithm (= rescheduling finished)
                if max_alg_difference == 0 and min_alg_difference == 0:
                    break

                # Determine if we move only 1 card or more
                if max_alg_difference == 1 or (max_alg_difference == 0 and min_alg_difference < 0):
                    # If only one card needs to be moved, we need to move it towards the highest negative difference
                    # First we need to find one of the highest negative difference (without rounding),
                    # Then find the highest positive difference (without rounding) closest to it,
                    # Then move the positive difference towards the negative one.
                    due_min_day = find_highest_negative_algebraic_difference()
                    due_max_day = find_highest_positive_algebraic_difference_closest_to_min_value(due_min_day)
                    if is_move_right(due_max_day, due_min_day):
                        self.move_cards_from_original_to_target_day(interval, amount=1, original_day=due_max_day,
                                                                    target_day=due_max_day + 1)
                    else:
                        self.move_cards_from_original_to_target_day(interval, amount=1, original_day=due_max_day,
                                                                    target_day=due_max_day - 1)
                else:
                    move_cards_from_due_day(original_day=due_max_day, amount=max_alg_difference)

                # After moving cards, we need to recalculate the new difference
                self.calculate_difference_between_current_and_average_due_day()
                iteration += 1

            self.number_of_iterations_of_main_algorithm[interval] = iteration
            if iteration == max_iteration_for_current_range:
                show_error_message_of_main_algorithm_and_exits()

    # Algorithm to select and move cards from original to target day while minimizing the amount of rescheduling
    def move_cards_from_original_to_target_day(self, interval: int, amount: int,
                                               original_day: int, target_day: int):

        # --- Internal Methods of the Move Card Algorithm --- #

        # Find the cards which were originally the closest to first_original_due_day
        def get_cards_by_diff_between_target_and_first_original_due_day() -> Dict[int, List[Card]]:
            cards_by_diff_compute: Dict[int, List[Card]] = RescheduleDeck.init_dict_of_cards(range1(0, interval))
            for card in cards_for_original_day:
                diff = abs(target_day - cards_with_their_due_day[card])
                cards_by_diff_compute[diff].append(card)
            return cards_by_diff_compute

        # Select cards to move if there are more candidates than needed
        # Note: Potential second algorithm for this selection
        def select_cards_to_move(cards_to_move: List[Card], amount_of_cards_to_move: int) -> List[Card]:
            if amount_of_cards_to_move < len(cards_to_move):
                # TODO: Add a secondary mechanism for choosing cards instead of just truncating (by ease for example)
                return cards_to_move[:amount_of_cards_to_move]
            else:
                return cards_to_move

        # Select and move cards from original_day to target_day
        def move_cards_among_list(cards_to_move: List[Card], nb_of_cards_to_move: int):
            cards_to_move_selected: List[Card] = select_cards_to_move(cards_to_move, nb_of_cards_to_move)
            for card in cards_to_move_selected:
                cards_for_original_day.remove(card)
                cards_for_target_day.append(card)

        def show_error_message_of_move_algorithm_and_exits() -> None:
            text = "Error, too many iterations in move_cards : "
            text += f"\n interval: {interval}, amount: {amount}"
            text += f", original_day: {original_day}, target_day: {target_day}"
            showInfo(text)
            self.show_both_original_and_target_difference()
            exit(1)

        # First algorithm of selection
        # We want to reschedule cards so that the difference between their original_due_day and their target_due_day
        # is minimized, so that we limit at the maximum the dispersion of cards due to rescheduling
        def move_card_algorithm() -> None:
            cards_by_diff: Dict[int, List[Card]] = get_cards_by_diff_between_target_and_first_original_due_day()
            number_of_moved_cards = 0
            iteration = 0
            while number_of_moved_cards != amount and iteration < interval:
                next_number_of_moved_cards = number_of_moved_cards + len(cards_by_diff[iteration])
                if next_number_of_moved_cards >= amount:
                    number_of_cards_to_move = amount - number_of_moved_cards
                    move_cards_among_list(cards_by_diff[iteration], nb_of_cards_to_move=number_of_cards_to_move)
                    break
                else:
                    move_cards_among_list(cards_by_diff[iteration], nb_of_cards_to_move=len(cards_by_diff[iteration]))
                    number_of_moved_cards = next_number_of_moved_cards
                iteration += 1

            if iteration == interval:
                show_error_message_of_move_algorithm_and_exits()

        # --- Actual Beginning of the Move Card Algorithm --- #

        # Class attributes used in the method
        cards_for_original_day: List[Card] = self.cards_target_by_interval_by_due_day[interval][original_day]
        cards_for_target_day: List[Card] = self.cards_target_by_interval_by_due_day[interval][target_day]
        cards_with_their_due_day: Dict[Card, int] = self.cards_with_first_original_due_day

        # Check potential restriction to the algorithm, and modifies the amount of cards to move if necessary
        if amount > len(cards_for_original_day):
            amount = len(cards_for_original_day)
            if amount == 0:
                # If there are no cards to move from original_day, we stop the method (note: this can only happen if invert equals true)
                # TODO: There may be potential cases in which the algorithm can break, in the case when we only move cards once,
                # TODO: that is if target_due_day is on the "sides". If we move cards twice and the second move happens, then it's fine.
                return

        move_card_algorithm()

    # --- "Result" Functions of ReorderDeck Class --- #

    # Determines the cards which need to be rescheduled by comparing their original and latest due_day
    def determine_cards_with_only_different_new_due_day(self):

        # Determines the new due_day from the attribute "cards_by_interval_by_due_day" modified by the algorithm
        # Note: this method is inside another one because we want to avoid adding a new class attribute (arguable)
        def determine_new_due_day_for_all_cards() -> Dict[Card, int]:
            new_due_day_by_card: Dict[Card, int] = dict()
            for interval in self.sequence_of_intervals:
                for due_day in range1(1, interval):
                    for card_2 in self.cards_target_by_interval_by_due_day[interval][due_day]:
                        new_due_day_by_card[card_2] = due_day
            return new_due_day_by_card

        cards_with_new_due_day: Dict[Card, int] = determine_new_due_day_for_all_cards()
        cards_with_only_different_new_due_day: Dict[Card, int] = dict()
        for card in self.cards:
            if self.cards_with_first_original_due_day[card] != cards_with_new_due_day[card]:
                cards_with_only_different_new_due_day[card] = cards_with_new_due_day[card] + self.day_of_today
        return cards_with_only_different_new_due_day

    # --- Print Functions of ReorderDeck Class (they all return strings) --- #
    # TODO: refactor (and maybe comment) them a bit

    @staticmethod
    def print_vars_obj(object) -> str:
        return f"{object.__class__} : {str(vars(object))}"

    def print_cards_by_interval(self) -> str:
        text = "Nb of Cards for each interval"
        for interval in self.sequence_of_intervals:
            text += f"\n Nb of Cards for interval {interval} = "
            text += f"{str(len(self.cards_by_interval[interval]))}"
        return text

    def print_cards_by_interval_by_due_day_original(self) -> str:
        return self.print_cards_by_interval_by_due_day(self.cards_original_by_interval_by_due_day)

    def print_cards_by_interval_by_due_day_target(self) -> str:
        return self.print_cards_by_interval_by_due_day(self.cards_original_by_interval_by_due_day)

    def print_cards_by_interval_by_due_day(self, cards: Dict[int, Dict[int, List]]) -> str:
        text = "Nb of Cards for each interval and each due day"
        for interval in self.sequence_of_intervals:
            text += f"\n\n Nb of Cards for each due day in interval = {interval} "
            text += f", (average = {self.average_number_of_cards_by_interval[interval]}) :"
            for due_day in range1(1, interval):
                text += f"\n Nb of Cards for interval = {interval} and due day = {due_day} : "
                text += f"{str(len(cards[interval][due_day]))}"
        return text

    def print_difference_original(self) -> str:
        return self.print_difference(self.cards_original_by_interval_by_due_day,
                                     self.difference_original_of_cards_by_interval_by_due_day)

    def print_difference_target(self) -> str:
        return self.print_difference(self.cards_target_by_interval_by_due_day,
                                     self.difference_target_of_cards_by_interval_by_due_day)

    def print_difference(self, cards: Dict[int, Dict[int, List]], differences: Dict[int, Dict[int, int]]) -> str:
        text = "Computed difference of cards between current and average by interval and due_day"
        for interval in self.sequence_of_intervals:
            text += f"\n\n For interval = {interval}"
            text += f", total_number = {len(self.cards_by_interval[interval])}"
            text += f", average cards by day = {self.average_number_of_cards_by_interval[interval]} :"
            # TODO: add average difference by day
            for due_day in range1(1, interval):
                text += f"\n For interval '{interval}' and due_day '{due_day}'"
                text += f", nb_of_cards = {len(cards[interval][due_day])}"
                text += f", difference = {differences[interval][due_day]}"
        return text

    # TODO: REFACTOR
    # TODO: DIFFERENTIATE TEXT IF RESCHEDULING PAST OVERDUE CARDS OR NOT
    # Access to self.cards_with_only_different_new_due_day, self.cards_with_first_original_due_day, self.max_interval,
    # self.day_of_today, self.cards
    def print_distribution_of_cards_rescheduled(self) -> str:

        if len(self.cards_with_only_different_new_due_day) == 0:
            return "Your deck doesn't need to be rescheduled ! \\o"

        range_for_absolute_difference = range1(0, self.max_interval)
        range_for_algebraic_difference = range1(-self.max_interval, self.max_interval)

        cards_to_reschedule_by_absolute_diff_in_due_day: Dict[int, List[Card]] = RescheduleDeck. \
            init_dict_of_cards(range_for_absolute_difference)

        cards_to_reschedule_by_algebraic_diff_in_due_day: Dict[int, List[Card]] = RescheduleDeck. \
            init_dict_of_cards(range_for_algebraic_difference)
        for card in self.cards_with_only_different_new_due_day:
            original_due_day = self.cards_with_first_original_due_day[card]
            new_due_day = self.cards_with_only_different_new_due_day[card] - self.day_of_today
            absolute_difference = abs(new_due_day - original_due_day)
            algebraic_difference = (new_due_day - original_due_day)
            assert absolute_difference > 0
            cards_to_reschedule_by_absolute_diff_in_due_day[absolute_difference].append(card)
            cards_to_reschedule_by_algebraic_diff_in_due_day[algebraic_difference].append(card)

        total_amount_of_rescheduling = 0
        for interval in range_for_absolute_difference:
            total_amount_of_rescheduling += interval * len(cards_to_reschedule_by_absolute_diff_in_due_day[interval])
        average_amount_of_rescheduling = total_amount_of_rescheduling / len(self.cards_with_only_different_new_due_day)
        average_amount_of_rescheduling = round(average_amount_of_rescheduling * 100) / 100
        percentage_of_card_rescheduled = round(
            len(self.cards_with_only_different_new_due_day) / len(self.cards) * 100 * 100) / 100

        total_amount_of_push_forward = 0
        for interval in range_for_algebraic_difference:
            total_amount_of_push_forward += interval * len(cards_to_reschedule_by_algebraic_diff_in_due_day[interval])
        average_amount_of_push_forward = total_amount_of_push_forward / len(self.cards_with_only_different_new_due_day)
        average_amount_of_push_forward = round(average_amount_of_push_forward * 100) / 100
        average_amount_of_all_push_forward = total_amount_of_push_forward / len(self.cards)
        average_amount_of_all_push_forward = round(average_amount_of_all_push_forward * 100) / 100

        # self.show_deck_info(self.deck)
        # parent_decks: List[DeckDict] = mw.col.decks.parents_by_name(self.deck["name"])
        # text_for_deck_parents = f"\n Parents decks for current deck  = "
        # text_for_deck_parents += f"{[deck['name'] for deck in parent_decks]}"
        # showInfo(text_for_deck_parents)

        text = "Distribution of cards to reschedule : "
        text += f"\n Today's date for current deck = {self.retrieve_date_of_today(self.deck)}"
        text += f"\n    Nb of cards overdue (in review status / queue = 0) = {self.number_of_cards_overdue_only_for_reviews_queue_2}"
        text += f"\n    Nb of cards overdue (in learning status with original_due < 1 day / queue = 1) = {self.number_of_cards_overdue_only_for_learning_queue_1}"
        text += f"\n    Nb of cards overdue (in learning status with original_due > 1 day / queue = 3) = {self.number_of_cards_overdue_only_for_learning_queue_3}"
        text += f"\n    Nb of cards overdue (in buried status / queue = - 3) = {self.number_of_cards_overdue_only_for_buried_queue_minus_3}"
        text += f"\n    Nb of cards over-scheduled (in review status with due > interval) = {self.number_of_cards_over_scheduled}"
        text += f"\n Nb of cards in deck not new, not suspended, in required interval range and overdue range= {len(self.cards)}"
        text += f"\n Nb of cards to reschedule = {len(self.cards_with_only_different_new_due_day)}"
        text += f"\n    Percentage of cards to reschedule = {percentage_of_card_rescheduled}%"
        text += f"\n    Average amount by which cards are rescheduled (absolute diff among rescheduled cards)"
        text += f" = {average_amount_of_rescheduling} days"
        text += f"\n    Average amount by which cards are pushed forward (algebraic diff among rescheduled cards)"
        text += f" = {average_amount_of_push_forward} days"
        text += f"\n    Average amount by which all cards are pushed forward (algebraic diff among all cards)"
        text += f" = {average_amount_of_all_push_forward} days"
        for interval in range_for_absolute_difference:
            if len(cards_to_reschedule_by_absolute_diff_in_due_day[interval]) > 0:
                text += f"\n       Amount of cards to reschedule by +- {interval} days : "
                text += f"{len(cards_to_reschedule_by_absolute_diff_in_due_day[interval])}"
        text += f"\n\n Iterations of main algorithm : "
        total_iterations = 0
        for interval in self.sequence_of_intervals:
            if self.number_of_iterations_of_main_algorithm[interval] > 0:
                total_iterations += self.number_of_iterations_of_main_algorithm[interval]
                text += f"\n    For interval = {interval}, nb of iterations = "
                text += f"{self.number_of_iterations_of_main_algorithm[interval]}"
        text += f"\n Total number of iterations of main algorithm : {total_iterations}"

        text += f"\n"
        return text

    def show_both_original_and_target_cards_by_interval_by_due_day(self):
        showInfo(self.print_cards_by_interval_by_due_day_original())
        showInfo(self.print_cards_by_interval_by_due_day_target())

    def show_both_original_and_target_difference(self):
        showInfo(self.print_difference_original())
        showInfo(self.print_difference_target())

    @staticmethod
    def show_card_and_note_info(card: Card):
        showInfo(RescheduleDeck.print_vars_obj(card))
        showInfo(RescheduleDeck.print_vars_obj(card.note()))

    @staticmethod
    def show_deck_info(deck: DeckDict):
        showInfo(f"Deck = {deck} ")


# --- END of ReorderDeck Class --- #


# Horizontal separation line
class QHSeparationLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(1)
        self.setFixedHeight(20)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)


# --- BEGINNING of DialogRescheduleDeck Class --- #


# TODO: ADD comment
class DialogRescheduleDeck(QDialog):
    deck_name: str
    min_interval: int
    max_interval: int
    is_reschedule_overdue_cards: bool
    is_dry_run: bool

    def __init__(self, parent=mw):
        super(DialogRescheduleDeck, self).__init__(parent)

        self.setWindowTitle("Reschedule Deck")
        self.setWindowFlags(Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint)

        self._box_deck_chooser = QComboBox()
        self._box_deck_chooser.addItems(sorted(mw.col.decks.allNames()))
        current_deck_id = mw.col.conf['curDeck']
        current_deck_name = mw.col.decks.get(current_deck_id)['name']
        self._box_deck_chooser.setCurrentText(current_deck_name)
        self._box_deck_chooser.activated.connect(self._changed)

        hint_text_for_min_interval = "1 is the minimum value possible"
        self._box_min_interval = self._spinbox(DEFAULT_MIN_VALUE_IN_RANGE, hint_text_for_min_interval)
        self._box_min_interval.valueChanged.connect(self._changed)

        hint_text_for_max_interval = "21 is the default value for which cards are considered"
        hint_text_for_max_interval += " mature (author's max interval value in their own decks)"
        self._box_max_interval = self._spinbox(DEFAULT_MAX_VALUE_IN_RANGE, hint_text_for_max_interval)
        self._box_max_interval.valueChanged.connect(self._changed)

        self._box_is_reschedule_overdue_cards = QCheckBox()
        self._box_is_reschedule_overdue_cards.setChecked(DEFAULT_RESCHEDULE_OVERDUE_CARDS)
        self._box_is_reschedule_overdue_cards.stateChanged.connect(self._changed)

        self._box_is_dry_run = QCheckBox()
        self._box_is_dry_run.setChecked(DEFAULT_DRY_RUN)
        self._box_is_dry_run.stateChanged.connect(self._changed)

        self._label_parameters_summary = QLabel()
        self._label_parameters_summary.setWordWrap(True)

        self._label_rescheduling_information = QLabel()
        self._label_rescheduling_information.setWordWrap(True)

        text_for_dry_run = "\n<font color=orange>Dry-run activated : the deck will NOT be rescheduled" \
                           ", this will only display a preview of the schedule performed. Disable dry-run to actually reschedule cards.</font>"
        self._label_warning_dry_run = QLabel(text_for_dry_run)
        self._label_warning_dry_run.setWordWrap(True)
        text_for_actual_run = "\n<font color=red>dry-run disactivated : the deck will be rescheduled - THIS ACTION CANNOT BE UNDONE.</font>"
        self._label_warning_actual_run = QLabel(text_for_actual_run)
        self._label_warning_actual_run.setWordWrap(True)

        # First initialization of internal variables (for use outside)
        self._changed()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._run_algorithm)
        button_box.rejected.connect(self.reject)

        layout = QGridLayout()
        layout.addWidget(self._label('Deck: '), 0, 0)
        layout.addWidget(self._box_deck_chooser, 0, 1)
        layout.addWidget(self._label('Minimum interval: '), 1, 0)
        layout.addWidget(self._box_min_interval, 1, 1)
        layout.addWidget(self._label('Maximum interval: '), 2, 0)
        layout.addWidget(self._box_max_interval, 2, 1)
        layout.addWidget(self._label('Reschedule overdue cards: '), 3, 0)
        layout.addWidget(self._box_is_reschedule_overdue_cards, 3, 1)
        layout.addWidget(self._label('Dry-run (do not actually reschedule): '), 4, 0)
        layout.addWidget(self._box_is_dry_run, 4, 1)

        layout.addWidget(QHSeparationLine(), 5, 0, 1, 2)
        layout.addWidget(self._label_parameters_summary, 6, 0, 1, 2)
        layout.addWidget(self._label_rescheduling_information, 7, 0, 1, 2)

        layout.addWidget(self._label_warning_dry_run, 8, 0, 1, 2)
        layout.addWidget(self._label_warning_actual_run, 8, 0, 1, 2)
        layout.addWidget(QHSeparationLine(), 10, 0, 1, 2)
        layout.addWidget(button_box, 11, 0, 1, 2)
        self.setLayout(layout)

    @staticmethod
    def _spinbox(value, tooltip):
        spinbox = QSpinBox()
        spinbox.setRange(1, 9_999)
        spinbox.setValue(value)
        spinbox.setSingleStep(1)
        spinbox.setToolTip(tooltip)
        return spinbox

    @staticmethod
    def _label(text):
        label = QLabel(text)
        # label.setFixedWidth(70)
        return label

    def _changed(self):
        # If state changed, update internal variables
        self.deck_name = self._box_deck_chooser.currentText()
        self.min_interval = self._box_min_interval.value()
        self.max_interval = self._box_max_interval.value()
        self.is_dry_run = self._box_is_dry_run.isChecked()
        self.is_reschedule_overdue_cards = self._box_is_reschedule_overdue_cards.isChecked()

        # If state changed, update displayed text
        self._label_parameters_summary.setText(self._print_parameters())
        if self.is_dry_run:
            self._label_warning_dry_run.show()
            self._label_warning_actual_run.hide()
        else:
            self._label_warning_dry_run.hide()
            self._label_warning_actual_run.show()

    def _print_parameters(self) -> str:
        text = f"Deck = {self.deck_name}"
        text += f"\nRange = {range1(self.min_interval, self.max_interval)}"
        text += f"\nIs dry-run = {self.is_dry_run}"
        text += f"\nIs reschedule overdue cards = {self.is_reschedule_overdue_cards}"
        return text

    def _run_algorithm(self):
        deck: DeckDict = get_deck(self.deck_name)
        cards: List[Card] = get_cards(self.deck_name)
        range_of_intervals = range1(self.min_interval, self.max_interval)

        reorder_deck = RescheduleDeck(deck, cards, range_of_intervals, self.is_reschedule_overdue_cards)
        self._label_rescheduling_information.setText(reorder_deck.print_distribution_of_cards_rescheduled())
        if not self.is_dry_run:
            # TODO: Add a confirmation pop-up
            reschedule_cards_in_database(reorder_deck.cards_with_only_different_new_due_day)
            # TODO: Add a success window (with some kind of internal check to ensure the rescheduling went okay!!!)


# --- END of DialogRescheduleDeck Class --- #


# --- GLOBAL FUNCTIONS ---#


def range1(start, end):
    return range(start, end + 1)


def get_cards(deckname: str) -> List[Card]:
    deck_id: DeckId = mw.col.decks.id_for_name(deckname)
    card_ids: List[CardId] = mw.col.decks.cids(deck_id, children=True)
    return [mw.col.get_card(card_id) for card_id in card_ids]


def get_deck(deckname: str) -> DeckDict:
    return mw.col.decks.by_name(deckname)


def reschedule_cards_in_database(cards_with_new_due_day: Dict[Card, int]) -> None:
    for card in cards_with_new_due_day:
        card.due = cards_with_new_due_day[card]
        card.flush()
    pass


def main_function() -> None:
    reschedule_dialog = DialogRescheduleDeck()
    reschedule_dialog.exec()


action = QtWidgets.QAction("Reorder Deck", mw)
action.triggered.connect(main_function)
mw.form.menuTools.addAction(action)
# TODO: Necessary ? Look at AddonManager.configAction()
# TODO: Understand (and refactor the addons.py file)
mw.addonManager.setConfigAction(__name__, main_function)
