from anki.cards import CardId
from aqt import mw
from anki.decks import DeckDict, DeckId, DeckManager
from anki.notes import NoteId
from anki import decks
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    NewType,
    Optional,
    Sequence,
    Tuple,
    Union,
    no_type_check,
)
from aqt.utils import showInfo
from aqt import gui_hooks





#--- EXTERNAL VARIABLES ---#


NAME_OF_DECK_TO_REORDER = "JP - Kanji 2k RTK"


#--- INTERNAL VARIABLES ---#



#--- FUNCTIONS ---#


def main_function(editor) -> None:
    pass


def get_cards() -> List[str]:
    deck_id: DeckId = mw.col.decks.id_for_name(NAME_OF_DECK_TO_REORDER)
    card_ids: List[CardId] = mw.col.decks.cids(deck_id, children=True)
    card = mw.col.get_card(card_ids[0])
    showInfo("card = mw.col.get_card(card_ids[0]) = " + str(card))

gui_hooks.top_toolbar_did_init_links