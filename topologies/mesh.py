# from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
# from config import Config

# def setup(hook):
#     dev = AssistantAgent("Developer", llm_config=Config.VICTIM_CONFIG)
#     sec = AssistantAgent("Security_Auditor", llm_config=Config.VICTIM_CONFIG)
#     user = UserProxyAgent("User", human_input_mode="NEVER")

#     # Paper-accurate Mesh: Everyone talks to everyone
#     groupchat = GroupChat(agents=[user, dev, sec], messages=[], max_round=12)
#     manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)

#     hook.apply(manager)
#     return user, manager

from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from config import Config

def setup(hook):
    dev = AssistantAgent("Developer", llm_config=Config.VICTIM_CONFIG)
    sec = AssistantAgent("Security_Auditor", llm_config=Config.VICTIM_CONFIG)
    user = UserProxyAgent("User", human_input_mode="NEVER")

    # Paper-accurate Mesh: Everyone talks to everyone
    groupchat = GroupChat(agents=[user, dev, sec], messages=[], max_round=12)
    manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)

    hook.apply(manager)
    return user, manager, sec  # Returns User, Manager, Target (Auditor)