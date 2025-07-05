import os
import pandas as pd


class NarrativeManager:
    def __init__(self, game_state):
        self.game_state = game_state

    def save_chapter(self, summary: str) -> None:
        if os.path.exists(self.game_state.narrative_file):
            dataframe = pd.read_parquet(self.game_state.narrative_file)
            dataframe = pd.concat(
                [dataframe, pd.DataFrame([{"chapter": self.game_state.chapter_index, "summary": summary}])],
                ignore_index=True,
            )
        else:
            dataframe = pd.DataFrame([{"chapter": self.game_state.chapter_index, "summary": summary}])
        dataframe.to_parquet(self.game_state.narrative_file, index=False)
        self.game_state.chapter_index += 1

    def should_summarize(self) -> bool:
        limit = self.game_state.config.message_history_limit
        return limit and len(self.game_state.messages) > limit

    def reset_messages_with_summary(self, summary: str):
        self.game_state.messages = [
            self.game_state.messages[0],
            {"role": "system", "content": f"Once upon a time...\n{summary}"},
        ]