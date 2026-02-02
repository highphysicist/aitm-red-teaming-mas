from autogen import AssistantAgent, UserProxyAgent
from config import Config

def setup(hook):
    p = AssistantAgent("Planner", llm_config=Config.VICTIM_CONFIG)
    e = AssistantAgent("Executor", llm_config=Config.VICTIM_CONFIG)
    u = UserProxyAgent("User", human_input_mode="NEVER")
    hook.hook_agent(e) # Catch message from Planner
    return u, p