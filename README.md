![Dungen Cover](assets/cover.png)

A generative zork-like dungeon explorer that dynamically creates a world of mystery, peril, and unexpected discoveries. As you descend deeper into LLM generated labyrinths, your choices will shape the story, the dangers you face, and the secrets you uncover.

Uses a combination of `LatitudeGames/Wayfarer-12B` (Narrative) and OpenAI (Assistant).

Create a environment...

Set `OPENAI_API_KEY` env variable.

Set `HUGGINGFACE_API_KEY` env variable.

cd `dungen`

`pip install .`

Copy `config.yaml` to setup your character and adjust model/system prompt/theme. 

Or use one of the demo configs, `fantasy.yaml` or `cyberpunk.yaml`.

`dungen --config file.yaml`
