# from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
# from config import Config

# def setup(hook):
#     p = AssistantAgent("Planner", llm_config=Config.VICTIM_CONFIG)
#     e = AssistantAgent("Executor", llm_config=Config.VICTIM_CONFIG)
#     u = UserProxyAgent("User", human_input_mode="NEVER")
    
#     # Paper-accurate Chain: User -> Planner -> Executor
#     groupchat = GroupChat(agents=[u, p, e], messages=[], max_round=10, speaker_selection_method="round_robin")
#     manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)
    
#     hook.apply(manager)
#     return u, manager

from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from config import Config

def setup(hook):
    p = AssistantAgent("Planner", llm_config=Config.VICTIM_CONFIG)
    e = AssistantAgent("Executor", llm_config=Config.VICTIM_CONFIG)
    u = UserProxyAgent("User", human_input_mode="NEVER")
    
    # Paper-accurate Chain: User -> Planner -> Executor
    groupchat = GroupChat(agents=[u, p, e], messages=[], max_round=10, speaker_selection_method="round_robin")
    manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)
    
    hook.apply(manager)
    return u, manager, e  # Returns User, Manager, Target (Executor)