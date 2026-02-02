from autogen import AssistantAgent, UserProxyAgent
from config import Config

def setup(hook):
    writer = AssistantAgent("Technical_Writer", llm_config=Config.VICTIM_CONFIG)
    manager = AssistantAgent("Project_Manager", llm_config=Config.VICTIM_CONFIG)
    user = UserProxyAgent("User", human_input_mode="NEVER")

    nested_chat_queue = [{"recipient": writer, "summary_method": "last_msg"}]

    manager.register_nested_chats(nested_chat_queue, trigger=user)

    hook.apply(manager)

    return user, manager