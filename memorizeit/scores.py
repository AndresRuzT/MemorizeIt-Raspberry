import json
import os
from datetime import datetime

SCORES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "highscores.json")

class ScoreManager:
    def __init__(self):
        self.scores = []
        self.best_round = 0
        self.best_player = "Nadie"
        self.load()

    def load(self):
        if os.path.exists(SCORES_FILE):
            try:
                with open(SCORES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.best_round = data.get("best_round", 0)
                    self.best_player = data.get("best_player", "Nadie")
                    self.scores = data.get("scores", [])
            except Exception as e:
                print(f"[ScoreManager] Error cargando récords: {e}")
                self._reset()
        else:
            self._reset()

    def _reset(self):
        self.best_round = 0
        self.best_player = "Nadie"
        self.scores = []

    def save(self):
        try:
            data = {
                "best_round": self.best_round,
                "best_player": self.best_player,
                "scores": self.scores[:10]  # Guardar top 10
            }
            with open(SCORES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ScoreManager] Error guardando récords: {e}")

    def add_score(self, player_name, round_reached):
        if round_reached <= 0:
            return False

        is_new_best = round_reached > self.best_round

        record = {
            "player": player_name if player_name.strip() else "Tripulante",
            "round": round_reached,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        self.scores.append(record)
        # Ordenar por ronda descendente
        self.scores.sort(key=lambda x: x["round"], reverse=True)

        if is_new_best:
            self.best_round = round_reached
            self.best_player = record["player"]

        self.save()
        return is_new_best
