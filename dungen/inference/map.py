import os
import io
import base64
from PIL import Image


class GenerateMap:
    def __init__(self, config, client):
        self.config = config
        self.client = client

    def update_map(self, input: str, webui: bool, map_generation: bool, turn: int, console, panels) -> str:
        if webui and map_generation:
            console.print(panels.render_info_panel("MAPGEN", f"{self.config.image_model} | One moment while I generate the map tile..."))
            prompt = f"{self.config.tile_generation_system_prompt}\n\n{self.config.system_prompt}\n\n{input}"
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
            save_path = os.path.join(save_dir, f"tile_{turn}.png")
            resized_image.save(save_path)
            console.print(panels.render_info_panel("MAPGEN", f"{self.config.image_model} | Done! Ready for next turn..."))
            return ""
        else:
            console.print(panels.render_info_panel("MAPGEN", f"{self.config.reasoning_model} | One moment while I update the game map..."))
            response = self.client.chat.completions.create(
                model=self.config.reasoning_model,
                messages=[
                    {"role": "system", "content": self.config.map_generator_system_prompt},
                    {"role": "user", "content": input},
                ],
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.startswith("```") and content.endswith("```"):
                content = content[3:-3].strip()
            elif content.startswith("`") and content.endswith("`"):
                content = content[1:-1].strip()
            
            return content