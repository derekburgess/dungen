import argparse
from dungen.game import Game


def main():
    parser = argparse.ArgumentParser(description="Play DUNGEN!")
    parser.add_argument("--inference", default="config.yaml", help="Path to model configuration YAML file")
    parser.add_argument("--settings", help="Path to game configuration YAML file (e.g., cyberpunk.yaml, fantasy.yaml)")
    parser.add_argument("--vllm", action="store_true", help="Use vLLM endpoint(RunPod) for narrative generation")
    parser.add_argument("--map", action="store_true", help="Expiremental map generation")
    parser.add_argument("--webui", action="store_true", help="Controls output for the Web UI")
    args = parser.parse_args()
    Game(inference_config_path=args.inference, game_settings_path=args.settings, remote_inference=args.vllm, map_generation=args.map, webui=args.webui).start()


if __name__ == "__main__":
    main()