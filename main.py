import html
from pathlib import Path
from typing import Annotated, Dict

from dopynion.data_model import (
    CardName,
    CardNameAndHand,
    Game,
    Hand,
    MoneyCardsInHand,
    PossibleCards,
    Cards,
    Player,
)
from fastapi import Depends, FastAPI, Header, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field


app = FastAPI()

#####################################################
# Gestion des numéros de tour par partie
#####################################################

# Dictionnaire pour stocker le numéro de tour pour chaque GameID
game_turn_numbers: Dict[str, int] = {}
# Dictionnaire pour suivre si un achat et une action ont été fait ce tour pour chaque partie
purchases_possible_this_turn: Dict[str, int] = {}
action_possible_this_turn: Dict[str, int] = {}

#####################################################
# Data model for responses
#####################################################


class DopynionResponseBool(BaseModel):
    game_id: str
    decision: bool


class DopynionResponseCardName(BaseModel):
    game_id: str
    decision: CardName


class DopynionResponseStr(BaseModel):
    game_id: str
    decision: str


#####################################################
# Getter for the game identifier
#####################################################

# --- Définition des valeurs monétaires des cartes ---
MONEY_CARD_VALUES = {
    "copper": 1,
    "silver": 2,
    "gold": 3,
    "platinum": 5,
    #"cursedgold": 3,
    # Ajoutez ici d'autres cartes d'argent si votre jeu en contient
}

def get_game_id(x_game_id: str = Header(description="ID of the game")) -> str:
    return x_game_id


GameIdDependency = Annotated[str, Depends(get_game_id)]


#####################################################
# error management
#####################################################


@app.exception_handler(Exception)
def unknown_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    print(f"ERREUR INCONNUE: {exc.__class__.__name__} - Détail: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "message": "Oops!",
            "detail": str(exc),
            "name": exc.__class__.__name__,
        },
    )


#####################################################
# Template extra bonus
#####################################################


# The root of the website shows the code of the website
@app.get("/", response_class=HTMLResponse)
def root() -> str:
    header = (
        "<html><head><title>Dopynion template</title></head><body>"
        "<h1>Dopynion documentation</h1>"
        "<h2>API documentation</h2>"
        '<p><a href="/docs">Read the documentation.</a></p>'
        "<h2>Code template</h2>"
        "<p>The code of this website is:</p>"
        "<pre>"
    )
    footer = "</pre></body></html>"
    return header + html.escape(Path(__file__).read_text(encoding="utf-8")) + footer


#####################################################
# The code of the strategy
#####################################################


@app.get("/name")
def name() -> str:
    return "Les Variables 2"


@app.get("/start_game")
def start_game(game_id: GameIdDependency) -> DopynionResponseStr:
    # Initialise le numéro de tour pour cette partie à 0
    game_turn_numbers[game_id] = 0
    print(f"Game ID: {game_id} - DÉBUT PARTIE : Numéro de tour initialisé à 0. Achat réinitialisé.")
    return DopynionResponseStr(game_id=game_id, decision="OK")


@app.get("/start_turn")
def start_turn(game_id: GameIdDependency) -> DopynionResponseStr:
    # Incrémente le numéro de tour pour cette partie
    game_turn_numbers[game_id] = game_turn_numbers.get(game_id, 0) + 1
    current_turn = game_turn_numbers[game_id]
    # Réinitialise l'état d'achat pour le nouveau tour
    purchases_possible_this_turn[game_id] = 1
    action_possible_this_turn[game_id] = 1
    print(f"Game ID: {game_id} - TOUR {current_turn} - START_TURN: Arbitre a envoyé pour start_turn. Achat réinitialisé pour ce tour.")
    return DopynionResponseStr(game_id=game_id, decision="OK")


def count_money_in_cards(cards: Cards) -> int:
    total_money = 0
    for card_name, quantity in cards.quantities.items():
        if card_name in MONEY_CARD_VALUES:
            total_money += MONEY_CARD_VALUES[card_name] * quantity
    return total_money

def card_in_deck(deck_cards_object: Cards, card_choice: str) -> bool:
    if not deck_cards_object or not deck_cards_object.quantities:
        return False
    # Parcourt les cartes dans l'objet Cards
    for card_name_in_deck, quantity in deck_cards_object.quantities.items():
        # Comparaison directe du nom de la carte et de la quantité
        if str(card_name_in_deck) == card_choice and quantity > 0:
            return True
    return False
    
@app.post("/play")
def play(_game: Game, game_id: GameIdDependency) -> DopynionResponseStr:
    current_turn = game_turn_numbers.get(game_id, 0) 

    # Trouver le joueur courant (celui qui a une main non nulle)
    current_player = next((p for p in _game.players if p.hand is not None), None)
    if not current_player:
        print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - AVERTISSEMENT: Aucun joueur actif avec une main.")
        raise HTTPException(status_code=400, detail="Aucun joueur actif avec une main.")
    else:
        # Accéder aux cartes de la main (c'est un objet Cards)
        hand = current_player.hand 
        print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - Main du joueur actuel: {hand.quantities} - SCORE = {current_player.score}")
        
        # Accéder aux quantités directement avec la chaîne "Copper"
        nb_copper = hand.quantities.get("copper", 0) 
        
        # Compte l'argent disponible UNIQUEMENT dans la main du joueur
        money_in_hand = count_money_in_cards(hand) 
        print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - Argent disponible dans la main du joueur : {money_in_hand}") # Affiche ici
        
        decision = "END_TURN" # Décision par défaut si aucun achat n'est fait

        # --- Logique pour la contrainte d'un achat par tour ---
        if action_possible_this_turn.get(game_id, 0) >= 1:
            if card_in_deck(hand, "fairgrounds") == True: # Exemple : si pas assez de copper pour Gold, achète un Silver si possible
                decision = "ACTION fairgrounds"
                action_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY EFFECTUÉ: {decision} - ACHAT ")            
            elif card_in_deck(hand, "smithy"):
                decision = "ACTION smithy"
                action_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY EFFECTUÉ: {decision} - ACHAT ")
            elif card_in_deck(hand, "magpie") == True: 
                decision = "ACTION magpie"
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY EFFECTUÉ: {decision} - ACHAT ")
        elif purchases_possible_this_turn.get(game_id, 0) >= 1: # Vérifie si un achat peut être fait ce tour
            if money_in_hand >= 11 and card_in_deck(_game.stock, "colony") == True: # Exemple : si pas assez de copper pour Colonnie, achète un Silver si possible
                decision = "BUY colony"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")
            elif money_in_hand >= 9 and card_in_deck(_game.stock, "platinum") == True: # Exemple : si pas assez de copper pour Platine, achète un Silver si possible
                decision = "BUY platinum"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")
            elif money_in_hand >= 8 and card_in_deck(_game.stock, "province") == True: # Exemple : si pas assez de copper pour Province, achète un Silver si possible
                decision = "BUY province"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")
            elif money_in_hand >= 7 and card_in_deck(_game.stock, "fairgrounds") == True: # Exemple : si pas assez de copper pour Gold, achète un Silver si possible
                decision = "BUY fairgrounds"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")            
            elif money_in_hand >= 6 and card_in_deck(_game.stock, "gold") == True: # Exemple : si pas assez de copper pour Gold, achète un Silver si possible
                decision = "BUY gold"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")
            elif money_in_hand >= 5 and card_in_deck(_game.stock, "magpie") == True: # Exemple : si pas assez de copper pour Duchy, achète un Silver si possible
                decision = "BUY magpie"
                purchases_possible_this_turn[game_id] -= 1            
            elif money_in_hand >= 4 and card_in_deck(_game.stock, "smithy") == True: # Exemple : si pas assez de copper pour Duchy, achète un Silver si possible
                decision = "BUY smithy"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")
            elif money_in_hand >= 3 and card_in_deck(_game.stock, "silver") == True: # Exemple : si pas assez de copper pour Estate, achète un Silver si possible
                decision = "BUY silver"
                purchases_possible_this_turn[game_id] -= 1
                print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - ACHAT EFFECTUÉ: {decision}")
            else:
                decision = "END_TURN"
        else:
            print(f"Game ID: {game_id} - TOUR {current_turn} - PLAY - Un achat a déjà été effectué ce tour. Décision: {decision}")
            decision = "END_TURN"
        # -----------------------------------------------------------------

        return DopynionResponseStr(game_id=game_id, decision=decision)


@app.get("/end_game")
def end_game(game_id: GameIdDependency) -> DopynionResponseStr:
    # Supprime l'entrée du game_id des dictionnaires de suivi des tours et des achats
    current_turn = game_turn_numbers.pop(game_id, 0) 
    purchases_possible_this_turn.pop(game_id, None) # Nettoie l'état d'achat pour cette partie
    print(f"Game ID: {game_id} - FIN PARTIE (Dernier tour enregistré: {current_turn}) : Partie terminée. États nettoyés.")
    return DopynionResponseStr(game_id=game_id, decision="OK")


@app.post("/confirm_discard_card_from_hand")
async def confirm_discard_card_from_hand(
    game_id: GameIdDependency,
    _decision_input: CardNameAndHand,
) -> DopynionResponseBool:
    current_turn = game_turn_numbers.get(game_id, 0)
    print(f"Game ID: {game_id} - TOUR {current_turn} - CONFIRM_DISCARD_CARD_FROM_HAND: Décision input: {_decision_input.model_dump_json()}")
    return DopynionResponseBool(game_id=game_id, decision=True)


@app.post("/discard_card_from_hand")
async def discard_card_from_hand(
    game_id: GameIdDependency,
    decision_input: Hand,
) -> DopynionResponseCardName:
    current_turn = game_turn_numbers.get(game_id, 0)
    print(f"Game ID: {game_id} - TOUR {current_turn} - DISCARD_CARD_FROM_HAND: Main reçue: {decision_input.hand}")
    return DopynionResponseCardName(game_id=game_id, decision=decision_input.hand[0])


@app.post("/confirm_discard_deck")
async def confirm_discard_deck(
    game_id: GameIdDependency,
) -> DopynionResponseBool:
    current_turn = game_turn_numbers.get(game_id, 0)
    print(f"Game ID: {game_id} - TOUR {current_turn} - CONFIRM_DISCARD_DECK:")
    return DopynionResponseBool(game_id=game_id, decision=True)


@app.post("/choose_card_to_receive_in_discard")
async def choose_card_to_receive_in_discard(
    game_id: GameIdDependency,
    decision_input: PossibleCards,
) -> DopynionResponseCardName:
    current_turn = game_turn_numbers.get(game_id, 0)
    print(f"Game ID: {game_id} - TOUR {current_turn} - CHOOSE_CARD_TO_RECEIVE_IN_DISCARD: Cartes possibles: {decision_input.possible_cards}")
    return DopynionResponseCardName(
        game_id=game_id,
        decision=decision_input.possible_cards[0],
    )


@app.post("/skip_card_reception_in_hand")
async def skip_card_reception_in_hand(
    game_id: GameIdDependency,
    _decision_input: CardNameAndHand,
) -> DopynionResponseBool:
    current_turn = game_turn_numbers.get(game_id, 0)
    print(f"Game ID: {game_id} - TOUR {current_turn} - SKIP_CARD_RECEPTION_IN_HAND: Décision input: {_decision_input.model_dump_json()}")
    return DopynionResponseBool(game_id=game_id, decision=True)


@app.post("/trash_money_card_for_better_money_card")
async def trash_money_card_for_better_money_card(
    game_id: GameIdDependency,
    decision_input: MoneyCardsInHand,
) -> DopynionResponseCardName:
    current_turn = game_turn_numbers.get(game_id, 0)
    print(f"Game ID: {game_id} - TOUR {current_turn} - TRASH_MONEY_CARD_FOR_BETTER_MONEY_CARD: Cartes monnaie en main: {decision_input.money_in_hand}")
    return DopynionResponseCardName(
        game_id=game_id,
        decision=decision_input.money_in_hand[0],
    )