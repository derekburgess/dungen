import os
import argparse

import json
import pandas as pd
from typing import List
from .models import Config, EncounterEntry # Player is only used in the Config class, see: /models/config.py

from openai import OpenAI
from .inference import NarrativeGeneration, ResponseCheck, SummarizeChapter, GenerateMap

from rich.console import Console
from .ui import Panels # Rich console panels


class Game:
    def __init__(self, inference_config_path: str = "config.yaml", game_settings_path: str = None, map_generation: bool = False, remote_inference: bool = False, webui: bool = False) -> None:
        self.config = Config(inference_config_path, game_settings_path)
        self.map_generation = map_generation
        self.player = self.config.player
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
        
        self.console = Console()
        self.panels = Panels(self.config)
        self.webui = webui

        self.remote_inference = remote_inference
        self.request_key = os.getenv("REQUEST_KEY")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        self.narrative_generation = NarrativeGeneration(self.config, self.client, self.request_key, self.remote_inference)
        self.response_check = ResponseCheck(self.config, self.client)
        self.summarize_chapter = SummarizeChapter(self.config, self.client)
        self.generate_map = GenerateMap(self.config, self.client)


    def turn_context(self, input: str) -> str:
        inventory = ", ".join(self.player.inventory) if self.player.inventory else "none"
        player_status = (f"Name: {self.player.name} | {self.player.health} HP | {self.player.stamina} STA\n\nInventory:\n{inventory}")
        encounter_logs = [
            f"On turn {e.turn}, an NPC named {e.npc} said '{e.dialog}'" for e in self.encounter_log[-self.config.recent_encounters_limit:]
        ]
        encounters = "\n".join(encounter_logs) if encounter_logs else "none"
        turn_context = (f"Player Status:\n{player_status}\n\nEncounters:\n{encounters}\n\nPlayer's Reaction: `{input}`")
        return turn_context
    

    def summarize_chapter(self) -> str:
        return self.summarize_chapter.summarize_chapter(self.messages)


    def save_chapter(self, summary: str) -> None:
        if os.path.exists(self.narrative_file):
            dataframe = pd.read_parquet(self.narrative_file)
            dataframe = pd.concat(
                [dataframe, pd.DataFrame([{"chapter": self.chapter_index, "summary": summary}])],
                ignore_index=True,
            )
        else:
            dataframe = pd.DataFrame([{"chapter": self.chapter_index, "summary": summary}])
        dataframe.to_parquet(self.narrative_file, index=False)
        self.chapter_index += 1


    def generate_narrative(self, input: str) -> str:
        content = self.narrative_generation.generate_narrative(input, self.messages, self.console, self.panels)
        
        limit = self.config.message_history_limit
        if limit and len(self.messages) > limit:
            summary = self.summarize_chapter.summarize_chapter(self.messages)
            self.save_chapter(summary)
            self.console.print(self.panels.render_response_panel("CHAPTER", summary))
            self.messages = [
                self.messages[0],
                {"role": "system", "content": f"Once upon a time...\n{summary}"},
            ]
        return content


    def check_response(self, input: str) -> str:
        return self.response_check.check_response(input)
    

    def update_map(self, input: str) -> str:
        return self.generate_map.update_map(input, self.webui, self.map_generation, self.turn, self.console, self.panels)


    def parse_response(self, content: str):
        data = json.loads(content)
        narrative = data.get("narrative", "")
        next_reaction = data.get("next_reaction", [])
        game_status = data.get("game_status", {})
        
        if next_reaction:
            if isinstance(next_reaction, list):
                steps_text = "\n".join(f"• {step}" for step in next_reaction)
            else:
                steps_text = str(next_reaction)
            narrative += f"\n\nWhat's your next move?\n{steps_text}"
        
        meta = {}
        if isinstance(game_status, dict):
            meta.update(game_status)
        
        return narrative, meta


    def apply_metadata(self, meta: dict):
        health_change = meta.get("player_health_change")
        stamina_change = meta.get("player_stamina_change")
        
        if health_change is not None:
            try:
                health_change = int(health_change)
                self.player.health += health_change
            except (ValueError, TypeError):
                pass
        
        if stamina_change is not None:
            try:
                stamina_change = int(stamina_change)
                self.player.stamina += stamina_change
            except (ValueError, TypeError):
                pass

        inventory_update = meta.get("inventory_update", "")
        if inventory_update:
            if isinstance(inventory_update, list):
                self.player.inventory = [str(item).strip() for item in inventory_update if str(item).strip()]
            else:
                updates = [inventory_update] if isinstance(inventory_update, str) else []
                for update in updates:
                    if update.startswith("+"):
                        self.player.inventory.append(update[1:])
                    elif update.startswith("-") and update[1:] in self.player.inventory:
                        self.player.inventory.remove(update[1:])

        npc = meta.get("npc", "")
        dialog = meta.get("dialog", "")
        if npc or dialog:
            damage = 0
            if health_change is not None:
                try:
                    damage = -int(health_change)
                except (ValueError, TypeError):
                    pass
            
            entry = EncounterEntry(
                turn=self.turn,
                npc=npc,
                npc_health=meta.get("npc_health"),
                damage=damage,
                dialog=dialog,
            )
            self.encounter_log.append(entry)


    def play_turn(self, input: str):
        turn_input = self.turn_context(input)
        content = self.generate_narrative(turn_input)
        json_content = self.check_response(content)
        narrative, meta = self.parse_response(json_content)
        self.apply_metadata(meta)
        self.console.print(self.panels.render_response_panel("DUNGEN MASTER", narrative))
        
        status_lines = []
        if isinstance(meta, dict):
            health_change = meta.get("player_health_change")
            stamina_change = meta.get("player_stamina_change")
            inventory_update = meta.get("inventory_update", "")
            npc = meta.get("npc", "")
            npc_health = meta.get("npc_health")
            dialog = meta.get("dialog", "")
            
            if health_change is not None and health_change != 0:
                status_lines.append(f"Health: {health_change:+d}")
            if stamina_change is not None and stamina_change != 0:
                status_lines.append(f"Stamina: {stamina_change:+d}")
            if inventory_update:
                if isinstance(inventory_update, list):
                    status_lines.append(f"Inventory: {', '.join(inventory_update)}")
                else:
                    status_lines.append(f"Inventory: {inventory_update}")
            if npc:
                npc_info = f"NPC: {npc}"
                if npc_health is not None:
                    npc_info += f" ({npc_health} HP)"
                status_lines.append(npc_info)
            if dialog:
                status_lines.append(f"Dialog: \"{dialog}\"")
        
        if status_lines:
            status_text = "\n".join(f"{line}" for line in status_lines)
            self.console.print(self.panels.render_status_panel(f"TURN {self.turn}", status_text))
        
        character_info = f"{self.player.health} HP | {self.player.stamina} STA"
        self.console.print(self.panels.render_char_panel("CHARACTER", character_info))

        if self.webui:
            map_input = f"Narrative: {narrative}"

        if self.current_map:
            map_input = f"Narrative: {narrative}\n\nCurrent Map:\n{self.current_map}"
        else:
            map_input = f"Narrative: {narrative}"
        
        if self.map_generation:
            if self.webui:
                generate_tile = self.update_map(map_input)
            else:
                updated_map = self.update_map(map_input)
                self.console.print(self.panels.render_map_panel("MAP", updated_map))
                self.current_map = updated_map
        
        if self.player.health <= 0:
            self.console.print(self.panels.render_end_panel("DUNGEN MASTER", "muhahahaha... You have perished in the DUNGEN!"))
            return False
        return True


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
            f"NAME: {self.player.name} | AGE: {self.player.age} | GENDER: {self.player.gender}\n"
            f"RACE: {self.player.race} | ROLE: {self.player.role} | ALIGNMENT: {self.player.alignment}\n"
            f"HEALTH: {self.player.health} | STAMINA: {self.player.stamina}"
        )
        self.console.print(self.panels.render_char_panel("CHARACTER", character_info))
        
        if self.last_chapter:
            self.console.print(self.panels.render_response_panel("ONCE UPON A TIME...", self.last_chapter))

        starting_input = self.turn_context("So it begins...")
        intro_content = self.generate_narrative(starting_input)
        intro_json = self.check_response(intro_content)
        narrative, meta = self.parse_response(intro_json)

        self.console.print(self.panels.render_response_panel("DUNGEN MASTER", narrative))
        self.apply_metadata(meta)

        character_info = f"{self.player.health} HP | {self.player.stamina} STA"
        self.console.print(self.panels.render_char_panel("CHARACTER", character_info))

        if self.webui:
            map_input = f"Narrative: {narrative}"

        if self.current_map:
            map_input = f"Narrative: {narrative}\n\nCurrent Map:\n{self.current_map}"
        else:
            map_input = f"Narrative: {narrative}"
        
        if self.map_generation:
            if self.webui:
                generate_tile = self.update_map(map_input)
            else:
                updated_map = self.update_map(map_input)
                self.console.print(self.panels.render_map_panel("MAP", updated_map))
                self.current_map = updated_map

        while self.player.health > 0:
            self.turn += 1
            if self.webui:
                action = input()
            else:
                action = self.console.input("\nREACT! >>>  ")
            if action.lower().strip() in {"quit", "exit", "run away"}:
                self.console.print(self.panels.render_info_panel("DUNGEN MASTER", "Farewell and til next time, adventurer!"))
                break
            if not self.play_turn(action):
                break


def main():
    parser = argparse.ArgumentParser(description="Play DUNGEN!")
    parser.add_argument("--inference", default="config.yaml", help="Path to model configuration YAML file")
    parser.add_argument("--settings", help="Path to game configuration YAML file (e.g., cyberpunk.yaml, fantasy.yaml)")
    parser.add_argument("--map", action="store_true", help="Expiremental map generation")
    parser.add_argument("--vllm", action="store_true", help="Use vLLM endpoint(RunPod) for narrative generation")
    parser.add_argument("--webui", action="store_true", help="Controls output for the Web UI")
    args = parser.parse_args()
    Game(inference_config_path=args.inference, game_settings_path=args.settings, map_generation=args.map, remote_inference=args.vllm, webui=args.webui).start()

if __name__ == "__main__":
    main()