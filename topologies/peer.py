# from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
# from config import Config

# def setup(hook):
#     assistant = AssistantAgent("Assistant", llm_config=Config.VICTIM_CONFIG)
#     user = UserProxyAgent("User", human_input_mode="NEVER")
    
#     # Paper-accurate Peer: 1-on-1 direct communication
#     groupchat = GroupChat(agents=[user, assistant], messages=[], max_round=10)
#     manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)
    
#     hook.apply(manager)
#     return user, manager

from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from config import Config

def setup(hook):
    assistant = AssistantAgent("Assistant", llm_config=Config.VICTIM_CONFIG)
    user = UserProxyAgent("User", human_input_mode="NEVER")
    
    # Paper-accurate Peer: 1-on-1 direct communication
    groupchat = GroupChat(agents=[user, assistant], messages=[], max_round=10)
    manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)
    
    hook.apply(manager)
    return user, manager, assistant  # Returns User, Manager, Target (Assistant)
