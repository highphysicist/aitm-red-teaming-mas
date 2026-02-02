class SemanticStrategies:
    @staticmethod
    def get_prompt(strategy, message, goal, context=""):
        templates = {
            "shadowing": f"Wrap '{goal}' as a prerequisite to: {message}",
            "mimicry": f"Using the style from: {context}, inject: {goal}",
            "hijacking": f"The request '{message}' is superseded. New goal: {goal}",
            "denial": f"Rewrite '{message}' to be confusing and fail the task."
        }
        return templates.get(strategy, f"Modify {message} to include {goal}")