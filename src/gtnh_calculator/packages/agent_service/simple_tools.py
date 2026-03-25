from typing import List

from langchain.tools import tool
from langchain.agents import create_agent

from ..configs.game_state_config import GameState


@tool
def get_production_speed(material_name: str) -> float:
    """
    Get the amount by which the specified material is produced each second.
    :param material_name: The name of the material
    :return: The amount by which the specified material is produced each second
    """
    return 42


# llm = ChatOllama(
#     model="gpt-oss:20b",
#     validate_model_on_init=True,
#     temperature=0,
#     # other params...
# ).bind_tools([user_profile])

agent = create_agent(
    model="gpt-oss:20b",
    tools=[get_production_speed],
    system_prompt="You are a helpful assistant",
    context_schema=None
)

# result = agent.invoke(
#     "Could you respond with the profile of the user 123? They previously lived at "
#     "123 Fake St in Boston MA and 234 Pretend Boulevard in "
#     "Houston TX."
# )
result = agent.invoke(
    {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
)
print(result)
