import os
import pandas as pd
from typing import List
from ..models import EncounterEntry


class GameState:
    def __init__(self, config, game_settings_path=None):
        self.config = config
        self.player = config.player
        self.turn = 0
        self.encounter_log: List[EncounterEntry] = []
        self.current_map = None

        if game_settings_path:
            self.narrative_file = os.path.splitext(game_settings_path)[0] + ".parquet"
        else:
            self.narrative_file = "game.parquet"
            
        if os.path.exists(self.narrative_file):
            dataframe = pd.read_parquet(self.narrative_file)
            self.chapter_index = len(dataframe) + 1
            self.last_chapter = dataframe.iloc[-1]["summary"] if not dataframe.empty else None
        else:
            self.chapter_index = 1
            self.last_chapter = None

        self.messages = [
            {"role": "system", "content": self.config.system_prompt},
        ]
        if self.last_chapter:
            self.messages.append(
                {
                    "role": "assistant",
                    "content": f"Once upon a time...\n{self.last_chapter}",
                }
            )

    def increment_turn(self):
        self.turn += 1

    def is_player_alive(self):
        return self.player.health > 0

    def update_map(self, new_map):
        self.current_map = new_map