import time
import random
import requests
import transformers
import torch


class NarrativeGeneration:
    def __init__(self, config, client, request_key=None, remote_inference=False):
        self.config = config
        self.client = client
        self.request_key = request_key
        self.remote_inference = remote_inference
        self._device_pipeline = None

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

    def generate_narrative(self, input: str, messages, console, panels) -> str:
        messages.append({"role": "user", "content": input})

        dm_waiting_strings = [
            "You notice something different…",
            "There's a shift in the atmosphere…",
            "Your surroundings begin to change…",
            "You become aware of something new…",
            "Something catches your attention…"
        ]
        console.print(panels.render_info_panel("DUNGEN MASTER", f"{self.config.narrative_model} | {random.choice(dm_waiting_strings)}"))

        device_input = f"<|im_start|>system\n{self.config.system_prompt}<|im_end|>\n"

        for message in messages[1:]:
            if message["role"] == "system":
                device_input += f"<|im_start|>system\n{message['content']}<|im_end|>\n"
            elif message["role"] == "user":
                device_input += f"<|im_start|>user\n{message['content']}<|im_end|>\n"
            elif message["role"] == "assistant":
                device_input += f"<|im_start|>assistant\n{message['content']}<|im_end|>\n"
        
        device_input += f"<|im_start|>assistant\n"

        if self.remote_inference:
            content = self.vllm_pipeline(device_input)
        else:
            content = self.device_pipeline(device_input)

        messages.append({"role": "assistant", "content": content})
        return content