import json
from ..models import EncounterEntry


class GameLogic:
    def __init__(self, game_state):
        self.game_state = game_state

    def turn_context(self, input: str) -> str:
        inventory = ", ".join(self.game_state.player.inventory) if self.game_state.player.inventory else "none"
        player_status = (f"Name: {self.game_state.player.name} | {self.game_state.player.health} HP | {self.game_state.player.stamina} STA\n\nInventory:\n{inventory}")
        encounter_logs = [
            f"On turn {e.turn}, an NPC named {e.npc} said '{e.dialog}'" for e in self.game_state.encounter_log[-self.game_state.config.recent_encounters_limit:]
        ]
        encounters = "\n".join(encounter_logs) if encounter_logs else "none"
        turn_context = (f"Player Status:\n{player_status}\n\nEncounters:\n{encounters}\n\nPlayer's Reaction: `{input}`")
        return turn_context

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
                self.game_state.player.health += health_change
            except (ValueError, TypeError):
                pass
        
        if stamina_change is not None:
            try:
                stamina_change = int(stamina_change)
                self.game_state.player.stamina += stamina_change
            except (ValueError, TypeError):
                pass

        inventory_update = meta.get("inventory_update", "")
        if inventory_update:
            if isinstance(inventory_update, list):
                self.game_state.player.inventory = [str(item).strip() for item in inventory_update if str(item).strip()]
            else:
                updates = [inventory_update] if isinstance(inventory_update, str) else []
                for update in updates:
                    if update.startswith("+"):
                        self.game_state.player.inventory.append(update[1:])
                    elif update.startswith("-") and update[1:] in self.game_state.player.inventory:
                        self.game_state.player.inventory.remove(update[1:])

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
                turn=self.game_state.turn,
                npc=npc,
                npc_health=meta.get("npc_health"),
                damage=damage,
                dialog=dialog,
            )
            self.game_state.encounter_log.append(entry)

    def play_turn(self, input: str, generate_narrative_callback, response_check, map_generation, generate_map, webui, console, panels):
        turn_input = self.turn_context(input)
        content = generate_narrative_callback(turn_input)
        
        json_content = response_check.check_response(content)
        narrative, meta = self.parse_response(json_content)
        self.apply_metadata(meta)
        console.print(panels.render_response_panel("DUNGEN MASTER", narrative))
        
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
            console.print(panels.render_status_panel(f"TURN {self.game_state.turn}", status_text))
        
        character_info = f"{self.game_state.player.health} HP | {self.game_state.player.stamina} STA"
        console.print(panels.render_char_panel("CHARACTER", character_info))

        if webui:
            map_input = f"Narrative: {narrative}"
        elif self.game_state.current_map:
            map_input = f"Narrative: {narrative}\n\nCurrent Map:\n{self.game_state.current_map}"
        else:
            map_input = f"Narrative: {narrative}"
        
        if map_generation:
            if webui:
                generate_map.update_map(map_input, webui, map_generation, self.game_state.turn, console, panels)
            else:
                updated_map = generate_map.update_map(map_input, webui, map_generation, self.game_state.turn, console, panels)
                console.print(panels.render_map_panel("MAP", updated_map))
                self.game_state.update_map(updated_map)
        
        if not self.game_state.check_player_status():
            console.print(panels.render_end_panel("DUNGEN MASTER", "muhahahaha... You have perished in the DUNGEN!"))
            return False
        return True