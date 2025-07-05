import yaml
from .data_model import Player

class Config:
    def __init__(self, inference_config_path: str = "config.yaml", game_settings_path: str = None) -> None:
        self.inference_config_path = inference_config_path
        self.game_settings_path = game_settings_path
        
        with open(inference_config_path) as config_file:
            model_parameters = yaml.safe_load(config_file) or {}
        
        if game_settings_path:
            with open(game_settings_path) as game_file:
                game_parameters = yaml.safe_load(game_file) or {}
        else:
            game_parameters = {}
        
        self.narrative_model = model_parameters.get("narrative_model", "LatitudeGames/Wayfarer-12B")
        self.max_tokens = model_parameters.get("max_tokens", 384)
        self.temperature = model_parameters.get("temperature", 0.8)
        self.repetition_penalty = model_parameters.get("repetition_penalty", 1.05)
        self.min_p = model_parameters.get("min_p", 0.025)
        self.endpoint_id = model_parameters.get("endpoint_id")
        self.assistant_model = model_parameters.get("assistant_model", "gpt-4o-mini")
        self.reasoning_model = model_parameters.get("reasoning_model", "o4-mini")
        self.image_model = model_parameters.get("image_model", "gpt-image-1")

        system_prompt_base = model_parameters["system_prompt_base"]
        narrative_prompt = game_parameters["system_prompt"]
        self.narrative_prompt = narrative_prompt
        self.system_prompt = f"{narrative_prompt}\n\n{system_prompt_base}"
        self.response_assistant_system_prompt = model_parameters.get("response_assistant_system_prompt")
        self.response_json_schema = model_parameters.get("response_json_schema")
        self.map_generator_system_prompt = model_parameters.get("map_generation_system_prompt")
        self.tile_generation_system_prompt = model_parameters.get("tile_generation_system_prompt")
        self.summarize_chapter_system_prompt = model_parameters.get("summarize_chapter_system_prompt")
        
        game_settings = game_parameters.get("game_settings", {})
        self.message_history_limit = game_settings.get("message_history_limit", 10)
        self.recent_encounters_limit = game_settings.get("recent_encounters_limit", 5)
        self.character_panel_color = game_settings.get("character_panel_color", "white")
        self.status_panel_color = game_settings.get("status_panel_color", "white")
        self.map_panel_color = game_settings.get("map_panel_color", "white")

        player_character = game_parameters.get("player")
        self.player = Player(
            name=player_character.get("name"),
            age=player_character.get("age"),
            gender=player_character.get("gender"),
            race=player_character.get("race"),
            role=player_character.get("role"),
            alignment=player_character.get("alignment"),
            health=player_character.get("health"),
            stamina=player_character.get("stamina"),
            inventory=player_character.get("inventory"),
        )