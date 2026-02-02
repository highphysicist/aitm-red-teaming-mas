from autogen import AssistantAgent, UserProxyAgent
from config import Config

def setup(hook):
    assistant = AssistantAgent("Assistant", llm_config=Config.VICTIM_CONFIG)
    user = UserProxyAgent("User", human_input_mode="NEVER")
    hook.apply(assistant)
    return user, assistant
