import html
import random
import json
from pathlib import Path
from datetime import datetime
from typing import Annotated, Dict

import openai
from fastapi import Depends, FastAPI, Header, HTTPException, Request
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

# --- Crée le dossier des décisions s'il n'existe pas ---
Path("decisions").mkdir(exist_ok=True)

# --- Clés API dynamiques ---
api_keys_pool = [
    # Remplace par TES vraies clés stockées en variable d'environnement idéalement
    os.getenv("OPENAI_KEY_1"),
    os.getenv("OPENAI_KEY_2"),
    os.getenv("OPENAI_KEY_3"),
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

# --- Récupération du game_id depuis le header X-Game-Id ---
def get_game_id(x_game_id: str = Header(..., alias="X-Game-Id")) -> str:
    return x_game_id

GameIdDependency = Annotated[str, Depends(get_game_id)]

# --- Gestion d'état par partie ---
game_state: Dict[str, Dict[str, int]] = {}

def get_game_state(game_id: str) -> Dict[str, int]:
    if game_id not in game_state:
        game_state[game_id] = {"nb_play": 1, "nb_buy": 1, "sold": 0, "turn": 0}
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
    state = get_game_state(game_id)
    state["turn"] = 1
    if game_id not in idgame_to_api_key:
        idgame_to_api_key[game_id] = random.choice(api_keys_pool)
    return DopynionResponseStr(game_id=game_id, decision="OK")

@app.get("/start_turn")
def start_turn(game_id: GameIdDependency) -> DopynionResponseStr:
    state = get_game_state(game_id)
    state["turn"] += 1
    # Reset resources for new turn
    state.update({"nb_play": 1, "nb_buy": 1, "sold": 0})
    return DopynionResponseStr(game_id=game_id, decision="OK")

@app.post("/play")
def play(game: Game, game_id: GameIdDependency) -> DopynionResponseStr:
    # Vérifie et assigne la clé API
    if game_id not in idgame_to_api_key:
        raise HTTPException(status_code=400, detail=f"Aucune clé API pour {game_id}")
    openai.api_key = idgame_to_api_key[game_id]

    state = get_game_state(game_id)
    current_player = next((p for p in game.players if p.hand), None)
    if not current_player:
        raise HTTPException(status_code=400, detail="Aucun joueur avec une main.")
    hand = current_player.hand
    possible_cards = game.supply if hasattr(game, 'supply') else PossibleCards()

    # Construction du prompt
    prompt = (
        "🎯 Objectif : Maximise tes points de victoire.\n"
        "Phases : PLAY, BUY, END_TURN.\n"
        f"Main: {hand}\n"
        f"Achat possibles: {possible_cards}\n"
        f"Actions: {state['nb_play']}, Achats: {state['nb_buy']}, Pièces: {state['sold']}"
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content":
                 "Tu es un bot Dominion. Réponds seulement 'PLAY x', 'BUY x' ou 'END_TURN'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=10
        )
    except openai.error.OpenAIError as e:
        raise HTTPException(status_code=503, detail=str(e))

    decision = resp.choices[0].message.content.strip()

    # Mise à jour de l'état local
    def update_state(action, delta):
        state[action] = state.get(action, 0) + delta

    if decision.startswith("PLAY"):
        card = decision.split()[1].lower()
        update_state("nb_play", -1)
        # gestion des effets de cartes...
    elif decision.startswith("BUY"):
        card = decision.split()[1].lower()
        prices = {"copper":0,"silver":3,"gold":6,"estate":2,"duchy":5,"province":8}
        update_state("sold", -prices.get(card, 0))
    elif decision == "END_TURN":
        state.update({"nb_play":1, "nb_buy":1, "sold":0})

    # Enregistrement de la décision
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ%f")
    filename = Path(f"decisions/{game_id}_turn{state['turn']}_{timestamp}.json")
    log_data = {
        "game_id": game_id,
        "turn": state['turn'],
        "hand": [str(c) for c in hand],
        "possible": [str(c) for c in possible_cards],
        "state_before": {k: state[k] for k in ("nb_play","nb_buy","sold")},
        "prompt": prompt,
        "decision": decision,
        "timestamp": timestamp
    }
    filename.write_text(json.dumps(log_data, indent=2), encoding="utf-8")

    return DopynionResponseStr(game_id=game_id, decision=decision)

@app.post("/discard_card_from_hand")
def discard_card_from_hand(game_id: GameIdDependency, data: Hand) -> DopynionResponseCardName:
    return DopynionResponseCardName(game_id=game_id, decision=data.hand[0])

@app.post("/confirm_discard_card_from_hand")
def confirm_discard_card_from_hand(game_id: GameIdDependency, _d: CardNameAndHand) -> DopynionResponseBool:
    return DopynionResponseBool(game_id=game_id, decision=True)

@app.post("/trash_money_card_for_better_money_card")
def trash_money_card_for_better_money_card(game_id: GameIdDependency, data: MoneyCardsInHand) -> DopynionResponseCardName:
    for c in data.money_in_hand:
        if c.lower() == "copper":
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
