import html
import random
from pathlib import Path
from typing import Annotated, Dict

import openai
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from dopynion.data_model import (
    CardName,
    CardNameAndHand,
    Game,
    Hand,
    MoneyCardsInHand,
    PossibleCards,
)

app = FastAPI()

# --- Clés API dynamiques ---
api_keys_pool = [
    "sk-key1",  # Remplace par tes vraies clés
    "sk-key2",
    "sk-key3"
]
idgame_to_api_key: Dict[str, str] = {}

# --- Modèles de réponse ---
class DopynionResponseBool(BaseModel):
    game_id: str
    decision: bool

class DopynionResponseCardName(BaseModel):
    game_id: str
    decision: CardName

class DopynionResponseStr(BaseModel):
    game_id: str
    decision: str

# --- Récupération du game_id ---
def get_game_id(x_game_id: str = Header(description="ID of the game")) -> str:
    return x_game_id

GameIdDependency = Annotated[str, Depends(get_game_id)]

# --- Gestion d'état par partie ---
game_state: Dict[str, Dict[str, int]] = {}

def get_game_state(game_id: str) -> Dict[str, int]:
    if game_id not in game_state:
        game_state[game_id] = {"nb_play": 1, "nb_buy": 1, "sold": 0}
    return game_state[game_id]

# --- Handler d'erreurs ---
@app.exception_handler(Exception)
def unknown_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"message": "Oops!", "detail": str(exc), "name": exc.__class__.__name__},
    )

@app.get("/", response_class=HTMLResponse)
def root() -> str:
    header = (
        "<html><head><title>Dopynion with GPT</title></head><body>"
        "<h1>GPT-driven Dominion Bot</h1><p><a href='/docs'>API Docs</a></p><pre>"
    )
    footer = "</pre></body></html>"
    return header + html.escape(Path(__file__).read_text(encoding="utf-8")) + footer

@app.get("/name")
def name() -> str:
    return "Les variables"

@app.get("/start_game")
def start_game(game_id: GameIdDependency) -> DopynionResponseStr:
    get_game_state(game_id)
    if game_id not in idgame_to_api_key:
        idgame_to_api_key[game_id] = random.choice(api_keys_pool)
    return DopynionResponseStr(game_id=game_id, decision="OK")

@app.get("/start_turn")
def start_turn(game_id: GameIdDependency) -> DopynionResponseStr:
    return DopynionResponseStr(game_id=game_id, decision="OK")

@app.post("/play")
def play(game: Game, game_id: GameIdDependency) -> DopynionResponseStr:
    if game_id not in idgame_to_api_key:
        raise ValueError(f"Aucune clé API trouvée pour l'idgame {game_id}")
    openai.api_key = idgame_to_api_key[game_id]

    state = get_game_state(game_id)
    current_player = next(p for p in game.players if p.hand is not None)
    hand = current_player.hand
    possible_cards = PossibleCards()

    prompt = (
        "🎯 Objectif :\n"
        "Maximise tes points de victoire en optimisant tes tours.\n\n"
        "🧩 Phases :\n"
        "1. PLAY une carte Action\n"
        "2. BUY une carte si tu as l'argent\n"
        "3. END_TURN\n\n"
        f"Main: {hand}\n"
        f"Cartes possibles à l'achat: {possible_cards}\n"
        f"Actions disponibles: {state['nb_play']}, Achats: {state['nb_buy']}, Pièces: {state['sold']}"
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Tu es un bot Dominion. Ne réponds qu'avec les cartes autorisées et les commandes formatées ('PLAY ', 'BUY ', 'END_TURN')."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=10
    )

    decision = response.choices[0].message.content.strip()

    def update_state(action, delta):
        state[action] += delta

    if decision.startswith("PLAY"):
        card = decision[5:].lower()
        update_state("nb_play", -1)
        if card == "village": update_state("nb_play", 2)
        elif card == "market": update_state("nb_buy", 1); update_state("sold", 1)
        elif card == "councilroom": update_state("nb_buy", 1)
        elif card == "festival": update_state("nb_play", 2); update_state("nb_buy", 1); update_state("sold", 2)
        elif card == "chancellor": update_state("sold", 2)
        elif card == "militia": update_state("sold", 2)
        elif card == "woodcutter": update_state("nb_buy", 1); update_state("sold", 2)
    elif decision.startswith("BUY"):
        prices = {
            "copper": 0, "silver": 3, "gold": 6, "estate": 2, "duchy": 5, "province": 8,
            "curse": 0, "village": 3, "smithy": 4, "market": 5, "adventurer": 6,
            "bureaucrat": 4, "cellar": 2, "chancellor": 3, "chapel": 2,
            "councilroom": 5, "feast": 4, "festival": 5, "gardens": 4,
            "laboratory": 5, "library": 5, "militia": 4, "mine": 5,
            "moneylender": 4, "remodel": 4, "witch": 5, "woodcutter": 3,
            "workshop": 3
        }
        card = decision[4:].lower()
        update_state("sold", -prices.get(card, 0))
    elif decision == "END_TURN":
        state["sold"] = 0
        state["nb_play"] = 1
        state["nb_buy"] = 1

    return DopynionResponseStr(game_id=game_id, decision=decision)

@app.post("/discard_card_from_hand")
def discard_card_from_hand(game_id: GameIdDependency, decision_input: Hand) -> DopynionResponseCardName:
    return DopynionResponseCardName(game_id=game_id, decision=decision_input.hand[0])

@app.post("/confirm_discard_card_from_hand")
def confirm_discard_card_from_hand(game_id: GameIdDependency, _d: CardNameAndHand) -> DopynionResponseBool:
    return DopynionResponseBool(game_id=game_id, decision=True)

@app.post("/trash_money_card_for_better_money_card")
def trash_money_card_for_better_money_card(game_id: GameIdDependency, data: MoneyCardsInHand) -> DopynionResponseCardName:
    for c in data.money_in_hand:
        if c == "Copper":
            return DopynionResponseCardName(game_id=game_id, decision=c)
    return DopynionResponseCardName(game_id=game_id, decision=data.money_in_hand[0])

@app.post("/choose_card_to_receive_in_discard")
def choose_card_to_receive_in_discard(game_id: GameIdDependency, data: PossibleCards) -> DopynionResponseCardName:
    return DopynionResponseCardName(game_id=game_id, decision=data.possible_cards[0])

@app.post("/skip_card_reception_in_hand")
def skip_card_reception_in_hand(game_id: GameIdDependency, _d: CardNameAndHand) -> DopynionResponseBool:
    return DopynionResponseBool(game_id=game_id, decision=True)

@app.post("/confirm_discard_deck")
def confirm_discard_deck(game_id: GameIdDependency) -> DopynionResponseBool:
    return DopynionResponseBool(game_id=game_id, decision=True)

@app.get("/end_game")
def end_game(game_id: GameIdDependency) -> DopynionResponseStr:
    game_state.pop(game_id, None)
    idgame_to_api_key.pop(game_id, None)
    return DopynionResponseStr(game_id=game_id, decision="OK")