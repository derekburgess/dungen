import os
import yaml
import argparse
import pandas as pd
import json
from dataclasses import dataclass, field
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from openai import OpenAI
import transformers
import torch
import requests


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
        
        system_prompt_base = model_parameters["system_prompt_base"]
        narrative_prompt = game_parameters["system_prompt"]
        self.narrative_prompt = narrative_prompt
        self.system_prompt = f"{narrative_prompt}\n\n{system_prompt_base}"
        
        game_settings = game_parameters.get("game_settings", {})
        self.message_history_limit = game_settings.get("message_history_limit", 10)
        self.recent_encounters_limit = game_settings.get("recent_encounters_limit", 5)

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


def render_intro_panel(title: str, message: str, console: Console) -> Panel:
    width = console.size.width
    return Panel(Text(message, justify="left"), title=f"{title}", border_style="white", width=width)


def render_info_panel(title: str, message: str, console: Console) -> Panel:
    width = console.size.width
    return Panel(Text(message, justify="center"), title=f"{title}", border_style="yellow", width=width)


def render_input_panel(title: str, message: str, console: Console) -> Panel:
    width = console.size.width
    return Panel(Text(message, justify="center"), title=f"{title}", border_style="blue", width=width)


def render_response_panel(title: str, message: str, console: Console) -> Panel:
    width = console.size.width
    return Panel(Text(message, justify="left"), title=f"{title}", border_style="green", width=width)


def render_status_panel(title: str, message: str, console: Console) -> Panel:
    width = console.size.width
    return Panel(Text(message, justify="left"), title=f"{title}", border_style="yellow", width=width)


def render_end_panel(title: str, message: str, console: Console) -> Panel:
    width = console.size.width
    return Panel(Text(message, justify="center"), title=f"{title}", border_style="red", width=width)


class Game:
    def __init__(self, inference_config_path: str = "config.yaml", game_settings_path: str = None, remote_inference: bool = False) -> None:
        self._device_pipeline = None
        self.remote_inference = remote_inference
        self.request_key = os.getenv("REQUEST_KEY")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        self.console = Console()

        self.config = Config(inference_config_path, game_settings_path)
        self.player = self.config.player
        self.turn = 0
        self.encounter_log: List[EncounterEntry] = []

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
        system_prompt = ("You support a game called DUNGEN! which is a generative zork-like dungeon explorer. You will be provided a log of past turns and your task is to summarize the events into a short chapter summary as if recounting events in a book. Do not include any titles such as 'Chapter 1', 'Chapter 2', or ### Chapter Summary:, etc. Do not include any follow up or list of choices at the end, just return the summary.")
        prompt = (f"Summarize the following turn logs into a short chapter as if recounting events in a book:\n{text}")

        response = self.client.chat.completions.create(
            model=self.config.assistant_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        #self.console.print(render_intro_panel("DEBUG [INPUT]", f"[SYSTEM PROMPT]\n{system_prompt}\n\n[PROMPT]\n{prompt}", self.console))
        #self.console.print(render_intro_panel("DEBUG [SUMMARY]", response.choices[0].message.content.strip(), self.console))
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

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        output = result.get("output")
        
        tokens = output[0]["choices"][0]["tokens"]
        response_text = " ".join(map(str, tokens))
        
        if response_text.endswith("<|im_end|>"):
            response_text = response_text[:-10].strip()
            
        return response_text


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
        self.console.print(render_info_panel("DUNGEN MASTER", "Generating narrative...", self.console))

        device_input = f"<|im_start|>system\n{self.config.system_prompt}<|im_end|>\n"

        for message in self.messages[1:]:
            if message["role"] == "system":
                device_input += f"<|im_start|>system\n{message['content']}<|im_end|>\n"
            elif message["role"] == "user":
                device_input += f"<|im_start|>user\n{message['content']}<|im_end|>\n"
            elif message["role"] == "assistant":
                device_input += f"<|im_start|>assistant\n{message['content']}<|im_end|>\n"
        
        device_input += f"<|im_start|>assistant\n"
        #self.console.print(render_intro_panel("DEBUG [INPUT]", device_input, self.console))

        if self.remote_inference:
            content = self.vllm_pipeline(device_input)
        else:
            content = self.device_pipeline(device_input)

        self.messages.append({"role": "assistant", "content": content})
        limit = self.config.message_history_limit
        if limit and len(self.messages) > limit:
            summary = self.summarize_chapter()
            self.save_chapter(summary)
            self.console.print(render_intro_panel("CHAPTER", summary, self.console))
            self.messages = [
                self.messages[0],
                {"role": "system", "content": f"Once upon a time...\n{summary}"},
            ]
        return content
    

    def check_response(self, input: str) -> str:
        system_prompt = """You support a game called DUNGEN! which is a generative zork-like dungeon explorer. You will be given a response from the DUNGEN! master and your task is to convert it to the JSON format expected by the game."""
        response = self.client.chat.completions.create(
            model=self.config.assistant_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "dungen_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "narrative": {
                                "description": "1-2 paragraphs describing the events of the turn using the game state and player's reaction",
                                "type": "string"
                            },
                            "next_reaction": {
                                "description": "List of 3 recommended next actions the player could take.",
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            },
                            "game_status": {
                                "description": "Game state changes and metadata",
                                "type": "object",
                                "properties": {
                                    "player_health_change": {
                                        "description": "Change in player health (can be negative), e.g., -10 (damage) or +10 (heal)",
                                        "type": "integer"
                                    },
                                    "player_stamina_change": {
                                        "description": "Change in player stamina (can be negative), e.g., -10 (damage) or +10 (heal)",
                                        "type": "integer"
                                    },
                                    "inventory_update": {
                                        "description": "List of inventory items to add/remove",
                                        "type": "array",
                                        "items": {
                                            "type": "string"
                                        }
                                    },
                                    "npc": {
                                        "description": "Name of NPC encountered",
                                        "type": "string"
                                    },
                                    "npc_health": {
                                        "description": "Health of NPC (null if not applicable)",
                                        "type": ["integer", "null"]
                                    },
                                    "dialog": {
                                        "description": "Dialog spoken by NPC",
                                        "type": "string"
                                    }
                                },
                                "additionalProperties": False
                            }
                        },
                        "required": ["narrative", "next_reaction", "game_status"],
                        "additionalProperties": False
                    }
                }
            }
        )
        #self.console.print(render_intro_panel("DEBUG [INPUT]", f"[SYSTEM PROMPT]\n{system_prompt}\n\n[INPUT]\n{input}", self.console))
        #self.console.print(render_intro_panel("DEBUG [JSON]", response.choices[0].message.content.strip(), self.console))
        return response.choices[0].message.content.strip()


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
        self.player.health += meta.get("player_health_change", 0)
        self.player.stamina += meta.get("player_stamina_change", 0)

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
                damage=-meta.get("player_health_change", 0),
                dialog=dialog,
            )
            self.encounter_log.append(entry)


    def play_turn(self, input: str):
        turn_input = self.turn_context(input)
        content = self.generate_narrative(turn_input)
        json_content = self.check_response(content)
        narrative, meta = self.parse_response(json_content)
        self.apply_metadata(meta)
        self.console.print(render_response_panel("DUNGEN MASTER", narrative, self.console))
        
        status_lines = []
        if isinstance(meta, dict):
            health_change = meta.get("player_health_change", 0)
            stamina_change = meta.get("player_stamina_change", 0)
            inventory_update = meta.get("inventory_update", "")
            npc = meta.get("npc", "")
            npc_health = meta.get("npc_health")
            dialog = meta.get("dialog", "")
            
            if health_change != 0:
                status_lines.append(f"Health: {health_change:+d}")
            if stamina_change != 0:
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
            self.console.print(render_status_panel(f"TURN {self.turn}", status_text, self.console))
        
        character_info = f"{self.player.health} HP | {self.player.stamina} STA"
        self.console.print(render_info_panel("CHARACTER", character_info, self.console))
        
        if self.player.health <= 0:
            self.console.print(render_end_panel("DUNGEN MASTER", "muhahahaha... You have perished in the dungeon!", self.console))
            return False
        return True


    def start(self):
        model_info = f"{self.config.narrative_model} (Narrative) | {self.config.assistant_model} (Assistant)"
        self.console.print(render_info_panel("INFERENCE", model_info, self.console))
        
        if self.remote_inference:
            settings_passed = f"{self.config.game_settings_path} | Remote vLLM (RunPod)"
        else:
            settings_passed = f"{self.config.game_settings_path} | Local Device Inference"
        narrative_prompt = f"{self.config.narrative_prompt}"
        self.console.print(render_info_panel("SETTINGS", settings_passed, self.console))
        self.console.print(render_status_panel("SYSTEM PROMPT", narrative_prompt, self.console))

        character_info = (
            f"NAME: {self.player.name} | AGE: {self.player.age} | GENDER: {self.player.gender}\n"
            f"RACE: {self.player.race} | ROLE: {self.player.role} | ALIGNMENT: {self.player.alignment}\n"
            f"HEALTH: {self.player.health} | STAMINA: {self.player.stamina}"
        )
        self.console.print(render_info_panel("CHARACTER", character_info, self.console))
        
        if self.last_chapter:
            self.console.print(render_intro_panel("ONCE UPON A TIME...", self.last_chapter, self.console))

        starting_input = self.turn_context("So it begins...")
        intro_content = self.generate_narrative(starting_input)
        intro_json = self.check_response(intro_content)
        narrative, meta = self.parse_response(intro_json)

        self.console.print(render_response_panel("DUNGEN MASTER", narrative, self.console))
        self.apply_metadata(meta)

        character_info = f"{self.player.health} HP | {self.player.stamina} STA"
        self.console.print(render_info_panel("CHARACTER", character_info, self.console))

        while self.player.health > 0:
            self.turn += 1
            action = self.console.input("\nREACT! >>>  ")
            if action.lower().strip() in {"quit", "exit", "run away"}:
                self.console.print(
                    render_info_panel(
                        "DUNGEN MASTER", "Farewell, adventurer!", self.console
                    )
                )
                break
            if not self.play_turn(action):
                break


def main():
    parser = argparse.ArgumentParser(description="Play DUNGEN!")
    parser.add_argument("--inference", default="config.yaml", help="Path to model configuration YAML file")
    parser.add_argument("--settings", help="Path to game configuration YAML file (e.g., cyberpunk.yaml, fantasy.yaml)")
    parser.add_argument("--vllm", action="store_true", help="Use vLLM endpoint(RunPod) for narrative generation")
    args = parser.parse_args()
    console = Console()
    
    if not args.settings:
        console.print(render_end_panel("ERROR", "--settings is required. Please specify a game settings file (e.g., cyberpunk.yaml, fantasy.yaml)", console))
        console.print(render_info_panel("TIP", "You can also copy one of the demo settings files and modify it to your liking.", console))
        return
        
    Game(inference_config_path=args.inference, game_settings_path=args.settings, remote_inference=args.vllm).start()

if __name__ == "__main__":
    main()