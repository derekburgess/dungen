![Dungen Cover](assets/cover.png)

# DUNGEN!

A generative zork-like dungeon explorer that dynamically creates a world of mystery, peril, and unexpected discoveries. As you descend deeper into LLM generated labyrinths, your choices will shape the story, the dangers you face, and the secrets you uncover.

Uses a combination of LatitudeGames/Wayfarer-12B (Narrative) and OpenAI (Assistant).


## Updates

v0.1.0 | Refactored into small files, easier for LLM's to handle and for humans to reason about.


## SETUP!

Create an environment...

Set `OPENAI_API_KEY` env variable.

Set `HUGGINGFACE_API_KEY` env variable.

cd `dungen`

`pip install -e .`


## USAGE!

Use one of the demo settings files, `fantasy.yaml` or `cyberpunk.yaml`, or copy one and define your own theme and/or character.

`dungen --settings file.yaml`

This will run the Wayfarer-12B model on your local device. Works, but slow on a 3090.

Passing `--vllm` will run the Wayfarer-12B model on RunPod using a serverless vLLM endpoint.

This assumes you are familair with RunPod and setting up a serverless endpoint.

Set `REQUEST_KEY` env variable. This is your RunPod API Key.

Update the `endpoint_id` in the `config.yaml` file. This is your RunPod endpoint id.

`dungen --settings file.yaml --vllm`

## Experimental MapGen

An experiment using o4-mini to generate ASCII game maps from the narrative content and a fixed set of "ASCII map tiles"

Pass `--map` when running the game.

Additionally, when running the WebUI (See below), selecting MapGen in the UI, will use gpt-image-1 to generate stylistic images based on the games narrative, with the goal of generating "map tiles". *This is unfortunately expensive, hence "experimental",  and local/vllm support will be added.


## WEBUI!

`cd dungen/dungen/webui/`

`npm install` *Assumes node set up...

`python server.py`

Visit `http://127.0.0.1:5000/`


### Play it your way! In the console or in the browser.

![Screenshot](assets/screenshot.png)

*Or even on a phone... ;P