import os
import io
import time
import yaml
import argparse
import pandas as pd
import json
import base64
from dataclasses import dataclass, field
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from openai import OpenAI
import transformers
import torch
import requests
import random
from PIL import Image


@dataclass
class Player:
    name: str
    age: int
    gender: str
    race: str
    role: str
    alignment: str
    health: int
    stamina: int
    inventory: List[str] = field(default_factory=list)


@dataclass
class EncounterEntry:
    turn: int
    npc: str
    npc_health: int
    damage: int
    dialog: str


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


class Game:
    def __init__(self, inference_config_path: str = "config.yaml", game_settings_path: str = None, map_generation: bool = False, remote_inference: bool = False, webui: bool = False) -> None:
        self._device_pipeline = None
        self.remote_inference = remote_inference
        self.request_key = os.getenv("REQUEST_KEY")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        self.console = Console()
        self.webui = webui

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

    def render_debug_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style="bright_black")


    def render_info_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="center"), title=f"{title}", border_style="bright_black")


    def render_status_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style=self.config.status_panel_color)


    def render_char_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="center"), title=f"{title}", border_style=self.config.character_panel_color)


    def render_response_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style="green")


    def render_map_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style=self.config.map_panel_color)


    def render_end_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="center"), title=f"{title}", border_style="red")


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
        text = "\n".join(f"{message['role']}: {message['content']}" for message in self.messages[1:])
        prompt = (f"Summarize the following turn logs into a short chapter as if recounting events in a book:\n{text}")

        response = self.client.chat.completions.create(
            model=self.config.assistant_model,
            messages=[
                {"role": "system", "content": self.config.summarize_chapter_system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        #self.console.print(self.render_debug_panel("DEBUG [INPUT]", f"[SYSTEM PROMPT]\n{self.config.summarize_chapter_system_prompt}\n\n[PROMPT]\n{prompt}"))
        #self.console.print(self.render_debug_panel("DEBUG [SUMMARY]", response.choices[0].message.content.strip()))
        return response.choices[0].message.content.strip()


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


    def vllm_pipeline(self, input: str) -> str:
        url = f"https://api.runpod.ai/v2/{self.config.endpoint_id}/runsync"
        headers = {
            "Authorization": f"Bearer {self.request_key}",
            "Content-Type": "application/json"
        }

        data = {
            "input": {
                "prompt": input,
                "sampling_params": {
                    "max_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                    "repetition_penalty": self.config.repetition_penalty,
                    "min_p": self.config.min_p
                }
            }
        }

        for _ in range(3):
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            output = response.json().get("output")
            if output:
                try:
                    tokens = output[0]["choices"][0]["tokens"]
                    text = " ".join(map(str, tokens))
                    return text.rstrip("<|im_end|>").strip()
                except Exception:
                    pass
            time.sleep(2)

        raise RuntimeError("Failed to get valid output from vLLM after retries.")


    def device_pipeline(self, input: str) -> str:
        if self._device_pipeline is None:
            self._device_pipeline = transformers.pipeline(
                "text-generation",
                model=self.config.narrative_model,
                model_kwargs={"torch_dtype": torch.bfloat16},
                device_map="auto",
            )
        
        outputs = self._device_pipeline(
            input,
            max_new_tokens=self.config.max_tokens,
            do_sample=True,
            temperature=self.config.temperature,
            repetition_penalty=self.config.repetition_penalty,
            min_p=self.config.min_p
        )
        
        response = outputs[0]["generated_text"]
        response_text = response[len(input):].strip()
        
        if response_text.endswith("<|im_end|>"):
            response_text = response_text[:-10].strip()
        
        return response_text


    def generate_narrative(self, input: str) -> str:
        self.messages.append({"role": "user", "content": input})

        dm_waiting_strings = [
            "You notice something different…",
            "There's a shift in the atmosphere…",
            "Your surroundings begin to change…",
            "You become aware of something new…",
            "Something catches your attention…"
        ]
        self.console.print(self.render_info_panel("DUNGEN MASTER", f"{self.config.narrative_model} | {random.choice(dm_waiting_strings)}"))

        device_input = f"<|im_start|>system\n{self.config.system_prompt}<|im_end|>\n"

        for message in self.messages[1:]:
            if message["role"] == "system":
                device_input += f"<|im_start|>system\n{message['content']}<|im_end|>\n"
            elif message["role"] == "user":
                device_input += f"<|im_start|>user\n{message['content']}<|im_end|>\n"
            elif message["role"] == "assistant":
                device_input += f"<|im_start|>assistant\n{message['content']}<|im_end|>\n"
        
        device_input += f"<|im_start|>assistant\n"
        #self.console.print(self.render_debug_panel("DEBUG [INPUT]", device_input))

        if self.remote_inference:
            content = self.vllm_pipeline(device_input)
        else:
            content = self.device_pipeline(device_input)

        self.messages.append({"role": "assistant", "content": content})
        limit = self.config.message_history_limit
        if limit and len(self.messages) > limit:
            summary = self.summarize_chapter()
            self.save_chapter(summary)
            self.console.print(self.render_response_panel("CHAPTER", summary))
            self.messages = [
                self.messages[0],
                {"role": "system", "content": f"Once upon a time...\n{summary}"},
            ]
        return content
    

    def check_response(self, input: str) -> str:
        response = self.client.chat.completions.create(
            model=self.config.assistant_model,
            messages=[
                {"role": "system", "content": self.config.response_assistant_system_prompt},
                {"role": "user", "content": input},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": self.config.response_json_schema
            }
        )
        #self.console.print(self.render_debug_panel("DEBUG [INPUT]", f"[SYSTEM PROMPT]\n{self.config.response_assistant_system_prompt}\n\n[INPUT]\n{input}"))
        #self.console.print(self.render_debug_panel("DEBUG [JSON]", response.choices[0].message.content.strip()))
        return response.choices[0].message.content.strip()
    

    def update_map(self, input: str) -> str:
        if self.webui:
            self.console.print(self.render_info_panel("MAPGEN", f"{self.config.image_model} | One moment while I generate the map tile..."))
            prompt = f"{self.config.tile_generation_system_prompt}\n\n{input}"
            save_dir = os.path.join("assets", "mini-map")
            os.makedirs(save_dir, exist_ok=True)
            img = self.client.images.generate(
                model=self.config.image_model,
                prompt=prompt,
                n=1,
                size="1024x1024",
            )

            image_bytes = base64.b64decode(img.data[0].b64_json)
            image = Image.open(io.BytesIO(image_bytes))
            resized_image = image.resize((128, 128), Image.Resampling.LANCZOS)
            save_path = os.path.join(save_dir, f"tile_{self.turn}.png")
            resized_image.save(save_path)
            self.console.print(self.render_info_panel("MAPGEN", f"{self.config.image_model} | Done! Ready for next turn..."))
        else:
            self.console.print(self.render_info_panel("MAPGEN", f"{self.config.reasoning_model} | One moment while I update the game map..."))
            response = self.client.chat.completions.create(
                model=self.config.reasoning_model,
                messages=[
                    {"role": "system", "content": self.config.map_generator_system_prompt},
                    {"role": "user", "content": input},
                ],
            )
            #self.console.print(self.render_debug_panel("DEBUG [INPUT]", f"[SYSTEM PROMPT]\n{self.config.map_generator_system_prompt}\n\n[INPUT]\n{input}"))
            #self.console.print(self.render_debug_panel("DEBUG [MAP]", response.choices[0].message.content.strip()))
            
            content = response.choices[0].message.content.strip()
            
            if content.startswith("```") and content.endswith("```"):
                content = content[3:-3].strip()
            elif content.startswith("`") and content.endswith("`"):
                content = content[1:-1].strip()
            
            return content


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
        
        self.player.health += health_change if health_change is not None else 0
        self.player.stamina += stamina_change if stamina_change is not None else 0

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
            entry = EncounterEntry(
                turn=self.turn,
                npc=npc,
                npc_health=meta.get("npc_health"),
                damage=-(health_change if health_change is not None else 0),
                dialog=dialog,
            )
            self.encounter_log.append(entry)


    def play_turn(self, input: str):
        turn_input = self.turn_context(input)
        content = self.generate_narrative(turn_input)
        json_content = self.check_response(content)
        narrative, meta = self.parse_response(json_content)
        self.apply_metadata(meta)
        self.console.print(self.render_response_panel("DUNGEN MASTER", narrative))
        
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
            self.console.print(self.render_status_panel(f"TURN {self.turn}", status_text))
        
        character_info = f"{self.player.health} HP | {self.player.stamina} STA"
        self.console.print(self.render_char_panel("CHARACTER", character_info))

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
                self.console.print(self.render_map_panel("MAP", updated_map))
                self.current_map = updated_map
        
        if self.player.health <= 0:
            self.console.print(self.render_end_panel("DUNGEN MASTER", "muhahahaha... You have perished in the DUNGEN!"))
            return False
        return True


    def start(self):
        if self.map_generation:
            model_info = f"{self.config.narrative_model} (Dungen Master) | {self.config.assistant_model} (Assistant) | {self.config.reasoning_model} (MapGen)"
        else:
            model_info = f"{self.config.narrative_model} (Dungen Master) | {self.config.assistant_model} (Assistant)"
        self.console.print(self.render_info_panel("INFERENCE", model_info))
        
        if self.remote_inference:
            settings_filename = os.path.basename(self.config.game_settings_path) if self.config.game_settings_path else "None"
            settings_passed = f"{settings_filename} | Remote vLLM (RunPod)"
        else:
            settings_filename = os.path.basename(self.config.game_settings_path) if self.config.game_settings_path else "None"
            settings_passed = f"{settings_filename} | Local Device Inference"
        narrative_prompt = f"{self.config.narrative_prompt}"
        self.console.print(self.render_info_panel("SETTINGS", settings_passed))
        self.console.print(self.render_debug_panel("SYSTEM PROMPT", narrative_prompt))

        character_info = (
            f"NAME: {self.player.name} | AGE: {self.player.age} | GENDER: {self.player.gender}\n"
            f"RACE: {self.player.race} | ROLE: {self.player.role} | ALIGNMENT: {self.player.alignment}\n"
            f"HEALTH: {self.player.health} | STAMINA: {self.player.stamina}"
        )
        self.console.print(self.render_char_panel("CHARACTER", character_info))
        
        if self.last_chapter:
            self.console.print(self.render_response_panel("ONCE UPON A TIME...", self.last_chapter))

        starting_input = self.turn_context("So it begins...")
        intro_content = self.generate_narrative(starting_input)
        intro_json = self.check_response(intro_content)
        narrative, meta = self.parse_response(intro_json)

        self.console.print(self.render_response_panel("DUNGEN MASTER", narrative))
        self.apply_metadata(meta)

        character_info = f"{self.player.health} HP | {self.player.stamina} STA"
        self.console.print(self.render_char_panel("CHARACTER", character_info))

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
                self.console.print(self.render_map_panel("MAP", updated_map))
                self.current_map = updated_map

        while self.player.health > 0:
            self.turn += 1
            if self.webui:
                action = input()
            else:
                action = self.console.input("\nREACT! >>>  ")
            if action.lower().strip() in {"quit", "exit", "run away"}:
                self.console.print(self.render_info_panel("DUNGEN MASTER", "Farewell and til next time, adventurer!"))
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