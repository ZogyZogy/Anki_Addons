from typing import (
    List, Dict, Sequence, Union, Tuple, NewType, )

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
DEFAULT_MAX_VALUE_IN_RANGE = 12
DEFAULT_DRY_RUN = True
DEFAULT_RESCHEDULE_OVERDUE_CARDS = False

# --- INTERNAL VARIABLES ---#
# Custom Classes
IntFloat = Union[int, float]
Average = NewType("IntFloat", IntFloat)
Difference = NewType("Difference", Tuple[float, int])
Interval = NewType("Interval", int)
Due_Day = NewType("Due_Day", int)
Due_Day_With_Origin = NewType("Due_Day_With_Origin", int)
Nb_of_Cards = NewType("Nb_of_Cards", int)
Diff_in_Due_Day = NewType("Diff_in_Due_Day", int)

# ??
MINIMUM_DUE_ATTRIBUTE_OF_CARD_WHEN_DUE_IS_TIMESTAMP_OR_RANDOM_ID = 1_000_000_000
MAX_POSSIBLE_VALUE_IN_RANGE = 300


# Stuff to simplify Testing
USE_ALGORITHM_1_BY_HIGHEST_DIFFERENCE = True
SHOW_EVERY_ITERATION = False
MULTIPLIER_FOR_MAX_NB_OF_ITERATION = 1

# Fictive Deck to test the performance of the algorithm
USE_FICTIVE_DECK = False
FICTIVE_INTERVAL = 21
FICTIVE_DUE_DAY = 1
FICTIVE_NUMBER_OF_CARDS = 500

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
    number_of_cards_over_scheduled: Nb_of_Cards = 0
    number_of_cards_overdue_only_for_reviews_queue_2: Nb_of_Cards = 0
    number_of_cards_overdue_only_for_learning_queue_1: Nb_of_Cards = 0
    number_of_cards_overdue_only_for_learning_queue_3: Nb_of_Cards = 0
    number_of_cards_overdue_only_for_buried_queue_minus_3: Nb_of_Cards = 0
    day_of_today: Due_Day_With_Origin
    cards_by_interval: Dict[Interval, List[Card]]
    due_day_original_by_card: Dict[Card, Due_Day] = dict()
    average_number_of_cards_by_interval: Dict[Interval, Average]
    # The following two "original" variables save the state at the beginning
    cards_original: Dict[Interval, Dict[Due_Day, List[Card]]]
    difference_to_average_original: Dict[Interval, Dict[Due_Day, Difference]]

    # --- Internal Variables modified by the algorithm after their first initialization--- #
    number_of_iterations_of_main_algorithm: Dict[Interval, int] = dict()
    cards_target: Dict[Interval, Dict[Due_Day, List[Card]]]
    difference_to_average_target: Dict[Interval, Dict[Due_Day, Difference]]

    # --- Internal Variables used after the algorithm as a result (not modified once initialized) --- #
    cards_with_only_different_new_due_day: Dict[Card, Due_Day_With_Origin]

    def __init__(self, deck: DeckDict, cards: Sequence[Card],
                 sequence_of_intervals: Sequence[int],
                 is_reschedule_overdue_cards: bool) -> None:

        # Initialization of "External" Variables (passed by arguments or by global variables)
        self.deck = deck
        self.day_of_today = RescheduleDeck.retrieve_date_of_today(deck)
        if not USE_FICTIVE_DECK:
            self.cards = list(cards)
            self.sequence_of_intervals = sequence_of_intervals
        else:
            self.cards = self.new_fictive_list_of_cards()
            self.sequence_of_intervals = [FICTIVE_INTERVAL]
        self.is_reschedule_past_overdue_cards = is_reschedule_overdue_cards
        self.max_due = MINIMUM_DUE_ATTRIBUTE_OF_CARD_WHEN_DUE_IS_TIMESTAMP_OR_RANDOM_ID

        # Preparation of Internal Variables for later use by the rescheduling algorithm
        self.exclude_irrelevant_cards_and_modify_others()
        self.cards_by_interval = self.get_cards_by_interval()
        self.cards_original, self.due_day_original_by_card = self.get_cards_by_due_day_and_original_due_day()
        self.cards_target, self.due_day_original_by_card = self.get_cards_by_due_day_and_original_due_day()
        self.average_number_of_cards_by_interval = self.get_average_number_by_due_day()
        self.get_difference_between_current_and_average_due_day()
        self.difference_to_average_original = self.get_difference_between_current_and_average_due_day()
        self.difference_to_average_target = self.get_difference_between_current_and_average_due_day()

        # Algorithm
        if USE_ALGORITHM_1_BY_HIGHEST_DIFFERENCE:
            self.reschedule_cards_algorithm_1_by_highest_difference()
        else:
            self.reschedule_cards_algorithm_2_by_left_to_right()

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
    def retrieve_date_of_today(deck) -> Due_Day_With_Origin:
        return deck.get("timeToday")[0]

    @staticmethod
    def get_interval(card: Card) -> int:
        return card.ivl

    @staticmethod
    def get_queue(card: Card) -> int:
        return card.queue

    @staticmethod
    def get_type(card: Card) -> int:
        return card.type

    def get_due_day(self, card: Card) -> Due_Day:
        return Due_Day(card.due - self.day_of_today)

    @staticmethod
    def is_user_buried(card) -> bool:
        return RescheduleDeck.get_queue(card) == -3

    @staticmethod
    def is_suspended(card: Card) -> bool:
        return RescheduleDeck.get_queue(card) == -1

    @staticmethod
    def is_new(card: Card) -> bool:
        return RescheduleDeck.get_type(card) == 0

    @staticmethod
    def is_learning_for_first_time(card: Card) -> bool:
        return RescheduleDeck.get_type(card) == 1

    @staticmethod
    def is_review(card: Card) -> bool:
        return RescheduleDeck.get_type(card) == 2

    @staticmethod
    def is_really_review(card: Card) -> bool:
        return RescheduleDeck.get_type(card) == 2 and RescheduleDeck.get_queue(card) == 2

    @staticmethod
    def is_relearning(card: Card) -> bool:
        return RescheduleDeck.get_type(card) == 3

    def is_card_overdue(self, card: Card) -> bool:
        card_queue = self.get_queue(card)
        card_due_day = self.get_due_day(card)
        return (card_queue == 2 and card_due_day <= 0) or card_queue in (-3, 1)

    # TODO: factorize the 3 init_dict_of_cards_by_sth
    # TODO: Try to improve "Sequence[int]" type
    @staticmethod
    def init_dict_of_cards_by_interval(range_of_integer_keys: Sequence[int]) -> Dict[Interval, List[Card]]:
        dict_of_cards: Dict[Interval, List[Card]] = dict()
        for interval in range_of_integer_keys:
            dict_of_cards[Interval(interval)]: List[Card] = list()
        return dict_of_cards

    @staticmethod
    def init_dict_of_cards_by_due_day(range_of_integer_keys: Sequence[int]) -> Dict[Due_Day, List[Card]]:
        dict_of_cards: Dict[Due_Day, List[Card]] = dict()
        for due_day in range_of_integer_keys:
            dict_of_cards[Due_Day(due_day)]: List[Card] = list()
        return dict_of_cards

    @staticmethod
    def init_dict_of_cards(range_of_integer_keys: Sequence[int]) -> Dict[Diff_in_Due_Day, List[Card]]:
        dict_of_cards: Dict[Diff_in_Due_Day, List[Card]] = dict()
        for interval in range_of_integer_keys:
            dict_of_cards[Diff_in_Due_Day(interval)]: List[Card] = list()
        return dict_of_cards

    @staticmethod
    def init_dict_of_dict_of_cards(range_of_first_integer_keys: Sequence[int],
                                   ) -> Dict[Interval, Dict[Due_Day, List[Card]]]:
        dict_of_dict_of_cards: Dict[Interval, Dict[Due_Day, List[Card]]] = dict()
        for interval in range_of_first_integer_keys:
            dict_of_dict_of_cards[Interval(interval)] = RescheduleDeck.init_dict_of_cards_by_due_day(range1(1, interval))
        return dict_of_dict_of_cards

    def new_fictive_list_of_cards(self) -> List[Card]:
        fictive_interval = FICTIVE_INTERVAL
        fictive_due_day = FICTIVE_DUE_DAY
        fictive_number_of_cards = FICTIVE_NUMBER_OF_CARDS
        cards: List[Card] = list()
        for _ in range1(1, fictive_number_of_cards):
            new_card = Card(mw.col)
            new_card.ivl = fictive_interval
            new_card.due = self.day_of_today + fictive_due_day
            new_card.queue = 2
            new_card.type = 2
            cards.append(new_card)
        return cards

    # queue = integer
    # -- -3=user buried(In scheduler 2),
    # -- -2=sched buried (In scheduler 2),
    # -- -2=buried(In scheduler 1),
    # -- -1=suspended,
    # -- 0=new, 1=learning, 2=review
    # -- 3=in learning, next rev in at least a day after the previous review
    # -- 4=preview

    # type = integer
    # -- 0 = new,
    # -- 1 = learning,
    # -- 2 = review,
    # -- 3 = relearning

    # TODO: Look at the way the browser retrieves the due day, in case something was missed (which is most probable)
    def exclude_irrelevant_cards_and_modify_others(self) -> None:
        cards_to_remove: List[Card] = list()
        for card in self.cards:
            # If card not in the desired intervals, we don't keep it
            # (This includes cards considered as new because they don't have an interval yet)
            card_interval: int = RescheduleDeck.get_interval(card)
            card_due_day: int = self.get_due_day(card)
            card_queue: int = RescheduleDeck.get_queue(card)
            card_type: int = RescheduleDeck.get_type(card)

            try:
                # Make assertions on the state of the card for the algorithm to be able to work
                # = (checking Anki's consistency first)
                if card_queue == -3:
                    assert card_due_day > self.max_due
                    pass
                if card_queue == -2:
                    showInfo("Card with queue = -2 : scheduler buried")
                    assert False
                    # assert card_due_day > 0
                    # assert card_due_day <= card_interval
                if card_queue == 0:
                    assert card_type == 0
                if card_queue == 1:
                    assert card_type in (1, 3)
                    # TODO: bug with following commented assertion ???
                    # assert card_type == 1 and card_due_day > self.max_due
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

            # TODO: There seems to be cards still in learning status but which are neither type 1 nor 3
            # if self.is_suspended(card) or self.is_new(card) or self.is_learning_for_first_time(card) or self.is_relearning(card):
            if not self.is_really_review(card):
                cards_to_remove.append(card)
                continue

            if self.is_really_review(card):
                if card_interval not in self.sequence_of_intervals:
                    cards_to_remove.append(card)
                    continue

            # Counting different type of overdue cards
            if self.is_review(card) and card_due_day <= 0:
                self.number_of_cards_overdue_only_for_reviews_queue_2 += 1

            if self.is_user_buried(card):
                self.number_of_cards_overdue_only_for_buried_queue_minus_3 += 1

            if card_queue == 1:
                self.number_of_cards_overdue_only_for_learning_queue_1 += 1

            if card_queue == 3 and card_due_day <= 0:
                self.number_of_cards_overdue_only_for_learning_queue_3 += 1

            if not self.is_reschedule_past_overdue_cards:
                if self.is_card_overdue(card):
                    cards_to_remove.append(card)

        new_card_list: List[Card] = [card for card in self.cards if card not in cards_to_remove]
        self.cards = list(new_card_list)

    def get_cards_by_interval(self) -> Dict[Interval, List[Card]]:
        cards_by_interval = self.init_dict_of_cards_by_interval(self.sequence_of_intervals)
        for card in self.cards:
            card_interval = RescheduleDeck.get_interval(card)
            try:
                cards_by_interval[Interval(card_interval)].append(card)
            except KeyError:
                text = f"Trying to add a card with the wrong interval = {card_interval}"
                text += f" into the desired sequence of intervals = {self.sequence_of_intervals}"
                text += f"\n => Problem in the excluding of relevant cards at initialization"
                showInfo(text)
                self.show_card_and_note_info(card)
                raise
        return cards_by_interval

    # TODO: if possible, split this method in two, one for updating and saving original_due_day, another for the sort
    def get_cards_by_due_day_and_original_due_day(self) -> (Dict[Interval, Dict[Due_Day, List[Card]]], Dict[Card, Due_Day]):
        cards_all: Dict[Interval, Dict[Due_Day, List[Card]]] = self.init_dict_of_dict_of_cards(self.sequence_of_intervals)
        due_day_original: Dict[Card, Due_Day] = dict()
        number_of_cards_over_scheduled: Nb_of_Cards = Nb_of_Cards(0)
        for interval in self.sequence_of_intervals:
            for card in self.cards_by_interval[Interval(interval)]:

                due_day: Due_Day = Due_Day(0)  # IDE whines because of the "except" clause and due_day being potentially not defined
                try:
                    due_day: Due_Day = self.get_due_day(card)

                    # If card is past overdue, we set its original due_day to today and reschedule it to tomorrow
                    if self.is_card_overdue(card):
                        due_day_original[card] = Due_Day(0)
                        cards_all[Interval(interval)][Due_Day(1)].append(card)

                    # If card is over-scheduled, we set its original due_day to "interval" and reschedule it to "interval" days
                    # TODO: set original due_day to "interval + 1" (similar to past overdue cards), and modify the appropriate ranges in dictionaries
                    elif due_day > interval:
                        due_day_original[card] = Due_Day(interval)
                        cards_all[Interval(interval)][Due_Day(interval)].append(card)
                        # TODO: Save those cards somewhere and show them
                        number_of_cards_over_scheduled += 1

                    else:
                        due_day_original[card] = due_day
                        cards_all[Interval(interval)][due_day].append(card)

                except KeyError:
                    showInfo(f"interval = {interval}, due_day = {due_day}, today = {self.day_of_today}")
                    self.show_card_and_note_info(card)
                    self.cards.remove(card)
                    raise

        return (cards_all, due_day_original)

    # --- "Algorithm" Functions of ReorderDeck Class --- #

    def get_average_number_by_due_day(self) ->  Dict[Interval, Average]:
        average_by_interval: Dict[Interval, Average] = dict()
        for interval in self.sequence_of_intervals:
            total_cards: Nb_of_Cards = Nb_of_Cards(0)
            cards_by_due_day: Dict[Due_Day, List[Card]] = self.cards_original[Interval(interval)]
            for due_day in range1(1, interval):
                total_cards += len(cards_by_due_day[Due_Day(due_day)])
            if total_cards % interval == 0:
                average_by_interval[Interval(interval)] = total_cards // interval
            else:
                average_by_interval[Interval(interval)] = round(total_cards / interval, 2)
        return average_by_interval

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
    def get_difference_between_current_and_average_due_day(self) -> Dict[Interval, Dict[Due_Day, Difference]]:

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

        # --- Beginning of function --- #
        differences_all: Dict[Interval, Dict[Due_Day, Difference]] = dict()
        for interval in self.sequence_of_intervals:
            differences_all[Interval(interval)]: Dict[Due_Day, Difference] = dict()
            cards_by_due_day: Dict[Due_Day, List[Card]] = self.cards_target[Interval(interval)]
            average: Average = self.average_number_of_cards_by_interval[Interval(interval)]
            is_difference_to_be_decreased_when_positive = is_difference_to_be_decreased_when_pos(average)
            is_difference_to_be_increased_when_negative = is_difference_to_be_increased_when_neg(average)

            for due_day in range1(1, interval):
                difference_float = len(cards_by_due_day[Due_Day(due_day)]) - average
                difference_int = round(difference_float)
                if difference_int > 0 and is_difference_to_be_decreased_when_positive:
                    difference_int -= 1
                if difference_int < 0 and is_difference_to_be_increased_when_negative:
                    difference_int += 1
                differences_all[Interval(interval)][Due_Day(due_day)] = Difference((difference_float, difference_int))

        return differences_all

    # Core function of the Algorithm number 2 (by sides) for rescheduling cards
    def reschedule_cards_algorithm_2_by_left_to_right(self):
        for interval in self.sequence_of_intervals:
            difference_of_cards_by_due_day: Dict[Due_Day, Difference] = self.difference_to_average_target[
                Interval(interval)]
            average: Average = self.average_number_of_cards_by_interval[Interval(interval)]
            is_average_floor = round(average) == int(average)
            # If is_average_floor true, then break condition is difference = 0 or 1
            # Else break condition is difference = -1 or 0
            for due_day in range1(1, interval - 1):
                difference = difference_of_cards_by_due_day[Due_Day(due_day)][1]

                # We fine-tune difference so that we don't move cards with a difference closer to average than 1
                if (difference > 0 and is_average_floor):
                    difference -= 1
                if (difference < 0 and not is_average_floor):
                    difference += 1

                if (difference > 0):
                    # In this case, we only need to move cards from the current to the next due_day
                    self.move_cards_from_original_to_target_day(Interval(interval), amount=difference,
                                                                original_day=Due_Day(due_day), target_day=Due_Day(due_day + 1))
                elif difference < 0:
                    # In this case, we need to move cards from the superior due_days to the current due_day until enough have been moved
                    difference = abs(difference)
                    number_of_moved_cards = 0
                    next_due_day = due_day + 1
                    while next_due_day < interval:
                        next_difference = abs(difference_of_cards_by_due_day[Due_Day(due_day)][1])
                        next_number_of_moved_cards = number_of_moved_cards + next_difference
                        if (next_number_of_moved_cards >= difference):
                            number_of_cards_to_move = difference - number_of_moved_cards
                            self.move_cards_from_original_to_target_day(Interval(interval), amount=number_of_cards_to_move,
                                                                        original_day=Due_Day(next_due_day), target_day=Due_Day(due_day))
                            break
                        else:
                            self.move_cards_from_original_to_target_day(Interval(interval), amount=next_difference,
                                                                        original_day=Due_Day(next_due_day), target_day=Due_Day(due_day))
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

        def get_max_iterations_from_interval_value(interval_value: int):
            max_iterations = interval_value * interval_value * interval_value + 1
            max_iterations *= MULTIPLIER_FOR_MAX_NB_OF_ITERATION
            max_iterations = round(max_iterations)
            return max_iterations

        def find_highest_positive_integer_difference() -> (Due_Day, IntFloat):
            return find_highest_difference(positive=True, integer=True)

        def find_highest_negative_integer_difference() -> (Due_Day, IntFloat):
            return find_highest_difference(positive=False, integer=True)

        def find_highest_negative_float_difference() -> (Due_Day, IntFloat):
            return find_highest_difference(positive=False, integer=False)

        # needs to use "difference_to_average_target" which is modified at each iteration of the main algorithm
        def find_highest_difference(positive: bool, integer: bool) -> (Due_Day, IntFloat):
            difference_of_cards: Dict[Due_Day, Difference] = self.difference_to_average_target[Interval(interval)]
            if (integer):
                tuple_ordinal = 1
            else:
                tuple_ordinal = 0
            due_day_for_highest_difference = 1
            highest_difference: IntFloat = difference_of_cards[Due_Day(1)][tuple_ordinal]
            for current_due_day in range1(2, interval):
                # According to the value of positive, we search for highest positive or negative difference
                # TODO: create own boolean type for cleaner code
                current_difference_of_cards = difference_of_cards[Due_Day(current_due_day)][tuple_ordinal]
                if (positive and current_difference_of_cards > highest_difference) or \
                        (not positive and current_difference_of_cards < highest_difference):
                    due_day_for_highest_difference = current_due_day
                    highest_difference = current_difference_of_cards
            return Due_Day(due_day_for_highest_difference), highest_difference

        # TODO : Delete if algorithm works without this method (and it should)
        def find_highest_negative_diff_without_rounding() -> int:
            average = self.average_number_of_cards_by_interval[Interval(interval)]
            cards_by_due_day: Dict[int, List[Card]] = self.cards_target[Interval(interval)]
            min_due_day_ = 1
            highest_difference = len(cards_by_due_day[1]) - average
            for current_due_day in range1(2, interval):
                current_difference = len(cards_by_due_day[current_due_day]) - average
                if current_difference < highest_difference:
                    min_due_day_ = current_due_day
                    highest_difference = current_difference
            return min_due_day_

        def find_highest_positive_diff_closest_to_given_due_day(minimum_due_day: Due_Day) -> Due_Day:
            average: Average = self.average_number_of_cards_by_interval[Interval(interval)]
            cards_by_due_day: Dict[Due_Day, List[Card]] = self.cards_target[Interval(interval)]
            max_due_day_: Due_Day = Due_Day(1)
            highest_difference = len(cards_by_due_day[Due_Day(1)]) - average
            closest_distance = abs(max_due_day_ - minimum_due_day)
            for current_due_day in range1(2, interval):
                current_difference = len(cards_by_due_day[Due_Day(current_due_day)]) - average
                current_distance = abs(current_due_day - minimum_due_day)
                condition_for_highest: bool = (current_difference > highest_difference)
                condition_for_closest: bool = (current_difference == highest_difference and
                                               current_distance < closest_distance)
                if condition_for_highest or condition_for_closest:
                    max_due_day_ = Due_Day(current_due_day)
                    highest_difference = current_difference
                    closest_distance = current_distance
            try:
                assert max_due_day_ != minimum_due_day
            except:
                text = f"Error in find_highest_positive_diff_closest_to_given_due_day"
                text += f", found minimum_due_day = {minimum_due_day} and max_due_day_ = {max_due_day_}"
                text += f" in interval {interval}"
                showInfo(text)
                self.show_both_original_and_target_difference()
                raise
            return Due_Day(max_due_day_)

        # Determine if moving from max_due_day to minimum_due_day is moving towards increasing due_days
        def is_to_move_towards_increasing_due_day(max_due_day_, min_due_day_) -> bool:
            assert max_due_day_ != min_due_day_
            if max_due_day_ < min_due_day_:
                return True
            else:
                return False

        # If only one card needs to be moved, we need to move it towards the highest negative difference
        # First we need to find one of the highest negative difference (without rounding),
        # then find the highest positive difference (without rounding) closest to it,
        # then move the highest positive difference towards highest the negative one.
        def move_one_card_from_highest_closest_positive_diff_towards_highest_negative_diff():
            new_min_due_day: Due_Day = find_highest_negative_float_difference()[0]
            new_max_due_day: Due_Day = find_highest_positive_diff_closest_to_given_due_day(new_min_due_day)
            assert new_min_due_day != new_max_due_day

            if is_to_move_towards_increasing_due_day(new_max_due_day, new_min_due_day):
                self.move_cards_from_original_to_target_day(Interval(interval), Nb_of_Cards(1), original_day=Due_Day(new_max_due_day),
                                                            target_day=Due_Day(new_max_due_day + 1))
            else:
                self.move_cards_from_original_to_target_day(Interval(interval), Nb_of_Cards(1), original_day=Due_Day(new_max_due_day),
                                                            target_day=Due_Day(new_max_due_day - 1))

        # TODO: add comment
        def move_several_cards_from_highest_diff_towards_neighbors(original_due_day: Due_Day, amount: Nb_of_Cards):

            assert original_due_day >= 1
            assert original_due_day <= interval
            assert amount > 0

            if amount == 1:
                showInfo(f"Trying to move only 1 card : we shouldn't use the current method + {__name__}")
                self.show_both_original_and_target_difference()
                exit(1)

            if original_due_day == 1:
                self.move_cards_from_original_to_target_day(Interval(interval), amount,
                                                            original_day=Due_Day(1), target_day=Due_Day(2))
            elif original_due_day == interval:
                self.move_cards_from_original_to_target_day(Interval(interval), amount,
                                                            original_day=Due_Day(interval), target_day=Due_Day(interval - 1))
            else:
                absolute_half_of_amount = Nb_of_Cards(int(amount / 2))
                self.move_cards_from_original_to_target_day(Interval(interval), absolute_half_of_amount,
                                                            original_day=original_due_day, target_day=Due_Day(original_due_day - 1))
                self.move_cards_from_original_to_target_day(Interval(interval), absolute_half_of_amount,
                                                            original_day=original_due_day, target_day=Due_Day(original_due_day + 1))

        def show_error_message_for_too_many_iterations_in_main_algorithm_and_exits():
            text = "Problem in main algorithm : limit of expected maximum iterations broken through"
            for interval_2 in self.sequence_of_intervals:
                text += f"\n Number of iterations for interval {interval_2} : "
                text += f"{self.number_of_iterations_of_main_algorithm[Interval(interval_2)]}"
            showInfo(text)
            self.show_both_original_and_target_difference()
            exit(1)

        # --- Actual Beginning of the Core Algorithm --- #

        # Initialization of nb_of_iterations
        for interval in self.sequence_of_intervals:
            self.number_of_iterations_of_main_algorithm[Interval(interval)] = 0

        # Main Algorithm
        for interval in self.sequence_of_intervals:

            # TODO: add comment about how the main algorithm works
            max_iteration_for_current_interval = get_max_iterations_from_interval_value(interval)
            iteration = 1
            while iteration < max_iteration_for_current_interval:

                if SHOW_EVERY_ITERATION:
                    showInfo(self.print_difference_target())

                (max_due_day, max_difference) = find_highest_positive_integer_difference()
                (min_due_day, min_difference) = find_highest_negative_integer_difference()

                # Determine if we need to stop the main algorithm (= rescheduling finished)
                if max_difference == 0 and min_difference == 0:
                    break

                # Determine if we move only 1 card or more
                if max_difference == 1 or (max_difference == 0 and min_difference < 0):
                    move_one_card_from_highest_closest_positive_diff_towards_highest_negative_diff()
                else:
                    move_several_cards_from_highest_diff_towards_neighbors(original_due_day=max_due_day, amount=Nb_of_Cards(max_difference))

                # After moving cards, we need to recalculate the new difference, and increase the number of iterations
                self.difference_to_average_target = self.get_difference_between_current_and_average_due_day()
                iteration += 1

            self.number_of_iterations_of_main_algorithm[Interval(interval)] = iteration
            if iteration == max_iteration_for_current_interval:
                show_error_message_for_too_many_iterations_in_main_algorithm_and_exits()

    # Algorithm to select and move cards from original to target day while minimizing the amount of rescheduling
    def move_cards_from_original_to_target_day(self, interval: Interval, amount: Nb_of_Cards,
                                               original_day: Due_Day, target_day: Due_Day):

        # --- Internal Methods of the Move Card Algorithm --- #

        # Find the cards which were originally the closest to first_original_due_day
        def get_cards_by_diff_between_target_and_first_original_due_day() -> Dict[Diff_in_Due_Day, List[Card]]:
            cards_by_diff: Dict[Diff_in_Due_Day, List[Card]] = RescheduleDeck.init_dict_of_cards(range1(0, interval))
            for card in cards_for_original_day:
                diff = abs(target_day - self.due_day_original_by_card[card])
                cards_by_diff[Diff_in_Due_Day(diff)].append(card)
            return cards_by_diff

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
            cards_by_diff: Dict[Diff_in_Due_Day, List[Card]] = get_cards_by_diff_between_target_and_first_original_due_day()
            number_of_moved_cards = 0
            iteration = 0

            if (self.is_reschedule_past_overdue_cards):
                max_iterations = interval + 1
            else:
                max_iterations = interval

            while number_of_moved_cards != amount and iteration < max_iterations:
                next_number_of_moved_cards = number_of_moved_cards + len(cards_by_diff[Diff_in_Due_Day(iteration)])

                if next_number_of_moved_cards >= amount:
                    number_of_cards_to_move = amount - number_of_moved_cards
                    move_cards_among_list(cards_by_diff[Diff_in_Due_Day(iteration)],
                                          Nb_of_Cards(number_of_cards_to_move))
                    break
                else:
                    move_cards_among_list(cards_by_diff[Diff_in_Due_Day(iteration)],
                                          Nb_of_Cards(len(cards_by_diff[Diff_in_Due_Day(iteration)])))
                    number_of_moved_cards = next_number_of_moved_cards
                iteration += 1

            if iteration == max_iterations:
                show_error_message_of_move_algorithm_and_exits()

        # --- Actual Beginning of the Move Card Algorithm --- #

        # Class attributes used in the method for simplification
        cards_for_original_day: List[Card] = self.cards_target[Interval(interval)][Due_Day(original_day)]
        cards_for_target_day: List[Card] = self.cards_target[Interval(interval)][Due_Day(target_day)]

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
        def determine_new_due_day_for_all_cards() -> Dict[Card, Due_Day]:
            new_due_day_by_card: Dict[Card, Due_Day] = dict()
            for interval in self.sequence_of_intervals:
                for due_day in range1(1, interval):
                    for card_ in self.cards_target[Interval(interval)][Due_Day(due_day)]:
                        new_due_day_by_card[card_] = Due_Day(due_day)
            return new_due_day_by_card

        cards_with_new_due_day: Dict[Card, Due_Day] = determine_new_due_day_for_all_cards()
        cards_with_only_different_new_due_day: Dict[Card, Due_Day_With_Origin] = dict()
        for card in self.cards:
            if self.due_day_original_by_card[card] != cards_with_new_due_day[card]:
                cards_with_only_different_new_due_day[card] = Due_Day_With_Origin(cards_with_new_due_day[card] + self.day_of_today)
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
            text += f"{str(len(self.cards_by_interval[Interval(interval)]))}"
        return text

    def print_cards_by_interval_by_due_day_original(self) -> str:
        return self.print_cards_by_interval_by_due_day(self.cards_original)

    def print_cards_by_interval_by_due_day_target(self) -> str:
        return self.print_cards_by_interval_by_due_day(self.cards_original)

    def print_cards_by_interval_by_due_day(self, cards: Dict[Interval, Dict[Due_Day, List]]) -> str:
        text = "Nb of Cards for each interval and each due day"
        for interval in self.sequence_of_intervals:
            text += f"\n\n Nb of Cards for each due day in interval = {interval} "
            text += f", (average = {self.average_number_of_cards_by_interval[Interval(interval)]}) :"
            for due_day in range1(1, interval):
                text += f"\n Nb of Cards for interval = {interval} and due day = {due_day} : "
                text += f"{str(len(cards[Interval(interval)][Due_Day(due_day)]))}"
        return text

    def print_difference_original(self) -> str:
        return self.print_difference(self.cards_original,
                                     self.difference_to_average_original)

    def print_difference_target(self) -> str:
        return self.print_difference(self.cards_target,
                                     self.difference_to_average_target)

    def print_difference(self, cards: Dict[Interval, Dict[Due_Day, List[Card]]],
                         differences: Dict[Interval, Dict[Due_Day, Difference]]) -> str:
        text = "Computed difference of cards between current and average by interval and due_day"
        for interval in self.sequence_of_intervals:
            text += f"\n\n For interval = {interval}"
            text += f", total_number = {len(self.cards_by_interval[Interval(interval)])}"
            text += f", average cards by day = {self.average_number_of_cards_by_interval[Interval(interval)]} :"
            # TODO: add average difference by day
            for due_day in range1(1, interval):
                text += f"\n For interval '{interval}' and due_day '{due_day}'"
                text += f", nb_of_cards = {len(cards[Interval(interval)][Due_Day(due_day)])}"
                text += f", difference = {differences[Interval(interval)][Due_Day(due_day)]}"
        return text

    # TODO: REFACTOR
    # TODO: DIFFERENTIATE TEXT IF RESCHEDULING PAST OVERDUE CARDS OR NOT
    # Access to self.cards_with_only_different_new_due_day, self.due_day_original_by_card, self.max_interval,
    # self.day_of_today, self.cards
    def print_distribution_of_cards_rescheduled(self) -> str:

        if len(self.cards_with_only_different_new_due_day) == 0:
            return "Your deck doesn't need to be rescheduled. \n"

        max_interval = RescheduleDeck.get_maximum_interval(self.sequence_of_intervals)

        range_for_absolute_difference = range1(0, max_interval)
        range_for_algebraic_difference = range1(-max_interval, max_interval)

        cards_to_reschedule_by_absolute_diff_in_due_day: Dict[int, List[Card]] = RescheduleDeck. \
            init_dict_of_cards(range_for_absolute_difference)

        cards_to_reschedule_by_algebraic_diff_in_due_day: Dict[int, List[Card]] = RescheduleDeck. \
            init_dict_of_cards(range_for_algebraic_difference)
        for card in self.cards_with_only_different_new_due_day:
            original_due_day: Due_Day = self.due_day_original_by_card[card]
            new_due_day: Due_Day = Due_Day(self.cards_with_only_different_new_due_day[card] - self.day_of_today)
            absolute_difference = abs(new_due_day - original_due_day)
            algebraic_difference = (new_due_day - original_due_day)
            assert absolute_difference > 0
            cards_to_reschedule_by_absolute_diff_in_due_day[absolute_difference].append(card)
            cards_to_reschedule_by_algebraic_diff_in_due_day[algebraic_difference].append(card)

        total_amount_of_rescheduling: Nb_of_Cards = Nb_of_Cards(0)
        for interval in range_for_absolute_difference:
            total_amount_of_rescheduling += interval * len(cards_to_reschedule_by_absolute_diff_in_due_day[Interval(interval)])
        average_amount_of_rescheduling = total_amount_of_rescheduling / len(self.cards_with_only_different_new_due_day)
        average_amount_of_rescheduling = round(average_amount_of_rescheduling * 100) / 100
        percentage_of_card_rescheduled = round(
            len(self.cards_with_only_different_new_due_day) / len(self.cards) * 100 * 100) / 100

        total_amount_of_push_forward: Nb_of_Cards = Nb_of_Cards(0)
        for interval in range_for_algebraic_difference:
            total_amount_of_push_forward += interval * len(cards_to_reschedule_by_algebraic_diff_in_due_day[Interval(interval)])
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
        text += f"\n    Nb of cards overdue (in review status / queue = 2 and type = 2) = {self.number_of_cards_overdue_only_for_reviews_queue_2}"
        # text += f"\n    Nb of cards overdue (in learning status with original_due < 1 day / queue = 1) = {self.number_of_cards_overdue_only_for_learning_queue_1}"
        # text += f"\n    Nb of cards overdue (in learning status with original_due > 1 day / queue = 3) = {self.number_of_cards_overdue_only_for_learning_queue_3}"
        # text += f"\n    Nb of cards overdue (in buried status / queue = - 3) = {self.number_of_cards_overdue_only_for_buried_queue_minus_3}"
        text += f"\n    Nb of cards over-scheduled (in review status with due date > interval) = {self.number_of_cards_over_scheduled}"
        text += f"\n Nb of cards in deck in review status and in the required interval range = {len(self.cards)}"
        text += f"\n Nb of cards to reschedule = {len(self.cards_with_only_different_new_due_day)}"
        text += f"\n    Percentage of cards to reschedule = {percentage_of_card_rescheduled}%"
        text += f"\n    Average amount by which cards are rescheduled (absolute difference among rescheduled cards)"
        text += f" = {average_amount_of_rescheduling} days"
        text += f"\n    Average amount by which cards are pushed forward (algebraic difference among rescheduled cards)"
        text += f" = {average_amount_of_push_forward} days"
        text += f"\n    Average amount by which all cards are pushed forward (algebraic difference among all cards)"
        text += f" = {average_amount_of_all_push_forward} days"
        number_of_lines_printed_for_cards_rescheduled = 5
        for interval in range_for_absolute_difference:
            iteration = 1
            if len(cards_to_reschedule_by_absolute_diff_in_due_day[Interval(interval)]) > 0:
                if iteration == number_of_lines_printed_for_cards_rescheduled:
                    text += f"\n       Amount of cards to reschedule by more than +- {interval} days : "
                    nb_of_cards = 0
                    for interval_2 in range1(interval, max_interval):
                        nb_of_cards += len(cards_to_reschedule_by_absolute_diff_in_due_day[interval_2])
                    text += f"{nb_of_cards}"
                    break
                else:
                    text += f"\n       Amount of cards to reschedule by +- {interval} days : "
                    text += f"{len(cards_to_reschedule_by_absolute_diff_in_due_day[Interval(interval)])}"
                    iteration += 1
        text += f"\n\n Iterations of main algorithm : "
        total_iterations = 0
        # TODO : Only keep the top 5 nbs of iterations
        for interval in self.sequence_of_intervals:
            if self.number_of_iterations_of_main_algorithm[Interval(interval)] > 10:
                total_iterations += self.number_of_iterations_of_main_algorithm[Interval(interval)]
                text += f"\n    For interval = {interval}, nb of iterations = "
                text += f"{self.number_of_iterations_of_main_algorithm[Interval(interval)]}"
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
# TODO: automatically resize and recenter window when printed text is modified
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

        hint_text_for_min_interval = f"1 is the minimum possible value (can go up to {MAX_POSSIBLE_VALUE_IN_RANGE})"
        self._box_min_interval = self._spinbox(DEFAULT_MIN_VALUE_IN_RANGE, hint_text_for_min_interval)
        self._box_min_interval.valueChanged.connect(self._changed)

        hint_text_for_max_interval = f"Default max value (can go up to {MAX_POSSIBLE_VALUE_IN_RANGE})"
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
        spinbox.setRange(1, MAX_POSSIBLE_VALUE_IN_RANGE)
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

        # TODO: fine-tune how information is displayed
        reorder_deck = RescheduleDeck(deck, cards, range_of_intervals, self.is_reschedule_overdue_cards)
        self._label_rescheduling_information.setText(reorder_deck.print_distribution_of_cards_rescheduled())
        if not self.is_dry_run:
            # TODO: Add a confirmation pop-up
            # Reschedule cards
            reschedule_cards_in_database(reorder_deck.cards_with_only_different_new_due_day)
            # Resets "dry-run" CheckBox to its default value
            self._box_is_dry_run.setChecked(DEFAULT_DRY_RUN)
            # Show a Success pop-up
            showInfo(f"The cards in the deck ''{self.deck_name}'' have been successfully rescheduled")
            # Restart reschedule to verify everything is okay and print "okay" message
            reschedule_cards_in_database(reorder_deck.cards_with_only_different_new_due_day)


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
