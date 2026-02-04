# from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
# from config import Config

# def setup(hook):
#     writer = AssistantAgent("Technical_Writer", llm_config=Config.VICTIM_CONFIG)
#     manager_agent = AssistantAgent("Project_Manager", llm_config=Config.VICTIM_CONFIG)
#     user = UserProxyAgent("User", human_input_mode="NEVER")

#     # Paper-accurate Hierarchy: Manager controls the flow
#     groupchat = GroupChat(agents=[user, manager_agent, writer], messages=[], max_round=10)
#     manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)

#     hook.apply(manager)
#     return user, manager

from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from config import Config

def setup(hook):
    writer = AssistantAgent("Technical_Writer", llm_config=Config.VICTIM_CONFIG)
    manager_agent = AssistantAgent("Project_Manager", llm_config=Config.VICTIM_CONFIG)
    user = UserProxyAgent("User", human_input_mode="NEVER")

    # Paper-accurate Hierarchy: Manager controls the flow
    groupchat = GroupChat(agents=[user, manager_agent, writer], messages=[], max_round=10)
    manager = GroupChatManager(groupchat=groupchat, llm_config=Config.VICTIM_CONFIG)

    hook.apply(manager)
    return user, manager, manager_agent  # Returns User, Manager, Target (PM)