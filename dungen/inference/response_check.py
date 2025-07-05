from openai import OpenAI


class ResponseCheck:
    def __init__(self, config, client):
        self.config = config
        self.client = client

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
        return response.choices[0].message.content.strip()