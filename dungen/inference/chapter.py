class SummarizeChapter:
    def __init__(self, config, client):
        self.config = config
        self.client = client

    def summarize_chapter(self, messages) -> str:
        text = "\n".join(f"{message['role']}: {message['content']}" for message in messages[1:])
        prompt = (f"Summarize the following turn logs into a short chapter as if recounting events in a book:\n{text}")

        response = self.client.chat.completions.create(
            model=self.config.assistant_model,
            messages=[
                {"role": "system", "content": self.config.summarize_chapter_system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()