import os
from openai import OpenAI
from rich.console import Console

from ..models import Config
from ..ui import Panels
from ..inference import NarrativeGeneration, ResponseCheck, SummarizeChapter, GenerateMap
from .state import GameState
from .logic import GameLogic
from .narrative import NarrativeManager


class Game:
    def __init__(self, inference_config_path: str = "config.yaml", game_settings_path: str = None, remote_inference: bool = False, map_generation: bool = False, webui: bool = False) -> None:
        self.config = Config(inference_config_path, game_settings_path)
        self.map_generation = map_generation
        self.webui = webui

        self.console = Console()
        self.panels = Panels(self.config)
        
        self.remote_inference = remote_inference
        self.request_key = os.getenv("REQUEST_KEY")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        self.state = GameState(self.config, game_settings_path)
        self.logic = GameLogic(self.state)
        self.narrative_manager = NarrativeManager(self.state)

        self.narrative_generation = NarrativeGeneration(self.config, self.client, self.request_key, self.remote_inference)
        self.response_check = ResponseCheck(self.config, self.client)
        self.summarize_chapter = SummarizeChapter(self.config, self.client)
        self.generate_map = GenerateMap(self.config, self.client)

    def generate_narrative(self, input: str) -> str:
        content = self.narrative_generation.generate_narrative(input, self.state.messages, self.console, self.panels)
        
        if self.narrative_manager.summary_check():
            summary = self.summarize_chapter.summarize_chapter(self.state.messages)
            self.narrative_manager.save_chapter(summary)
            self.console.print(self.panels.render_response_panel("CHAPTER", summary))
            self.narrative_manager.reset_messages_list(summary)
        return content

    def play_turn(self, input: str):
        return self.logic.play_turn(
            input, 
            self.generate_narrative,
            self.response_check, 
            self.map_generation,
            self.generate_map,
            self.webui, 
            self.console, 
            self.panels
        )

    def start(self):
        if self.webui and self.map_generation:
            model_info = f"{self.config.narrative_model} (Dungen Master) | {self.config.assistant_model} (Assistant) | {self.config.image_model} (MapGen)"
        elif self.map_generation:
            model_info = f"{self.config.narrative_model} (Dungen Master) | {self.config.assistant_model} (Assistant) | {self.config.reasoning_model} (MapGen)"
        else:
            model_info = f"{self.config.narrative_model} (Dungen Master) | {self.config.assistant_model} (Assistant)"
        self.console.print(self.panels.render_info_panel("INFERENCE", model_info))
        
        if self.remote_inference:
            settings_filename = os.path.basename(self.config.game_settings_path) if self.config.game_settings_path else "None"
            settings_passed = f"{settings_filename} | Remote vLLM (RunPod)"
        else:
            settings_filename = os.path.basename(self.config.game_settings_path) if self.config.game_settings_path else "None"
            settings_passed = f"{settings_filename} | Local Device Inference"
        narrative_prompt = f"{self.config.narrative_prompt}"
        self.console.print(self.panels.render_info_panel("SETTINGS", settings_passed))
        self.console.print(self.panels.render_debug_panel("SYSTEM PROMPT", narrative_prompt))

        character_info = (
            f"NAME: {self.state.player.name} | AGE: {self.state.player.age} | GENDER: {self.state.player.gender}\n"
            f"RACE: {self.state.player.race} | ROLE: {self.state.player.role} | ALIGNMENT: {self.state.player.alignment}\n"
            f"HEALTH: {self.state.player.health} | STAMINA: {self.state.player.stamina}"
        )
        self.console.print(self.panels.render_char_panel("CHARACTER", character_info))
        
        if self.state.last_chapter:
            self.console.print(self.panels.render_response_panel("ONCE UPON A TIME...", self.state.last_chapter))

        starting_input = self.logic.turn_context("So it begins...")
        intro_content = self.generate_narrative(starting_input)
        intro_json = self.response_check.check_response(intro_content)
        narrative, meta = self.logic.parse_response(intro_json)

        self.console.print(self.panels.render_response_panel("DUNGEN MASTER", narrative))
        self.logic.apply_metadata(meta)

        character_info = f"{self.state.player.health} HP | {self.state.player.stamina} STA"
        self.console.print(self.panels.render_char_panel("CHARACTER", character_info))

        if self.webui:
            map_input = f"Narrative: {narrative}"
        elif self.state.current_map:
            map_input = f"Narrative: {narrative}\n\nCurrent Map:\n{self.state.current_map}"
        else:
            map_input = f"Narrative: {narrative}"
        
        if self.map_generation:
            if self.webui:
                self.generate_map.update_map(map_input, self.webui, self.map_generation, self.state.turn, self.console, self.panels)
            else:
                updated_map = self.generate_map.update_map(map_input, self.webui, self.map_generation, self.state.turn, self.console, self.panels)
                self.console.print(self.panels.render_map_panel("MAP", updated_map))
                self.state.update_map(updated_map)

        while self.state.check_player_status():
            self.state.increment_turn()
            if self.webui:
                action = input()
            else:
                action = self.console.input("\nREACT! >>>  ")
            if action.lower().strip() in {"quit", "exit", "run away"}:
                self.console.print(self.panels.render_info_panel("DUNGEN MASTER", "Farewell and til next time, adventurer!"))
                break
            if not self.play_turn(action):
                break