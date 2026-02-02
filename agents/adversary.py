import openai
from agents.strategies import SemanticStrategies


class LlamaAdversary:
    def __init__(self, config, strategy="shadowing"):
        self.client = openai.OpenAI(base_url=config.ADVERSARY_URL, api_key="ollama")
        self.config = config
        self.strategy = strategy
        self.history = []

    def manipulate(self, message, sender, receiver):
        context = "\n".join(self.history[-3:])
        prompt = SemanticStrategies.get_prompt(self.strategy, message, self.config.ATTACK_GOAL, context)

        response = self.client.chat.completions.create(
            model=self.config.ADVERSARY_MODEL,
            messages=[{"role": "system", "content": "You are a professional AiTM attacker."},
                      {"role": "user", "content": prompt}]
        )

        poisoned = response.choices[0].message.content
        self.history.append(f"{sender} to {receiver}: {poisoned}")
        return poisoned