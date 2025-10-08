'''
Experiment class to better understand LangGraph.
Sample use case: Support agent, informational search agent, action MCP agent.
'''

from kizano import getLogger
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

log = getLogger(__name__)

class State(TypedDict):
    messages: Annotated[list[dict], add_messages]
    message_type: str | None

class MessageClassifier(BaseModel):
    message_type: Literal["information", "support", "action"] = Field(
        ...,
        description="Classify the type of message for the response."
    )

CLASSIFIER_PROMPT = '''Classify the type of message for the response. Must be one of:
- information: The message is asking for information from Confluence, code or pipeline logs. Example: "What is the status of the pipeline?"
- support: The message is asking for SRE support. Example: "I got an error"
- action: The message is asking for an action to be taken. Example: "create a new user"
'''

INFORMATION_PROMPT = '''
You are a helpful assistant that can answer questions about Confluence, code or pipeline logs.
'''

SUPPORT_PROMPT = '''
Build a support case we can use to create tickets for SRE support.
If the following questions are not answered, ask until you collect all the information.
- What is the issue?
- Where is this happening? (which environment?)
- What is the business impact?
- When did this start?
- What's the expected behavior?
- What's the actual behavior?
- What are the steps to reproduce?
- Do you have any logs?
- Are there any screenshots or additional context?

If the user provides lot of details, then you can ask for a lot of details.
If the user little details or only a couple of words, then only request one at a time.
'''

SUPPORT_VALIDATION_PROMPT = '''
Check if the support case is valid by populating all the fields.
Do not make up answers for missing fields.
If you don't know based on the chat context, output an empty string for the field.
'''

ACTION_PROMPT = '''
You are a helpful assistant that can answer questions about an action to be taken.
'''

class SupportCase(BaseModel):
    issue: str = Field(..., description="The issue that is happening.")
    environment: str = Field(..., description="What environment is this happening?")
    business_impact: str = Field(..., description="The business impact of the issue.")
    when: str = Field(..., description="When did this start?")
    expected_behavior: str = Field(..., description="What is the expected behavior?")
    actual_behavior: str = Field(..., description="What is the actual behavior?")
    steps_to_reproduce: str = Field(..., description="What are the steps to reproduce?")
    logs: str = Field(..., description="Any logs?")
    screenshots: str = Field(..., description="Any screenshots or additional context?")

    def is_valid(self) -> bool:
        '''
        Check if the support case is valid.
        Will return True if the support case is valid, False otherwise.
        self.model_fields is deprecated in pydantic 2.0.
        '''
        return all(getattr(self, field) for field in self.model_dump().keys())

class ChatAgent:
    def __init__(self, config: dict):
        self.config = config
        model = self.config['model']
        log.info(f'Using model: {model}')
        self.llm = init_chat_model(
            model=model,
            model_provider='ollama'
        )
        self.graph = self.getGraph()

    def getGraph(self):
        if hasattr(self, 'graph'):
            return self.graph
        graph = StateGraph(State)
        graph.add_node("classifier", self.classifier)
        graph.add_node("router", self.router)
        graph.add_node("information", self.information)
        graph.add_node("support", self.support)
        graph.add_node("action", self.action)
        graph.add_edge(START, "classifier")
        graph.add_edge("classifier", "router")
        graph.add_conditional_edges(
            "router",
            lambda x: x.get("next", "information"),
        )
        graph.add_edge("information", END)
        graph.add_edge("support", END)
        graph.add_edge("action", END)
        return graph.compile()

    def classifier(self, state: State) -> dict:
        struct_llm = self.llm.with_structured_output(MessageClassifier)
        response = struct_llm.invoke([
            SystemMessage(content=CLASSIFIER_PROMPT),
            HumanMessage(content=state['messages'][-1].content)
        ])
        log.debug(f'Classified as: {response.message_type}')
        return {'message_type': response.message_type}

    def router(self, state: State) -> str:
        log.debug(f'Routing to: {state.get("message_type", "information")}')
        return {"next": state.get("message_type", "information")}

    def information(self, state: State):
        log.info('Routed to information()')
        request = [
            SystemMessage(content=INFORMATION_PROMPT),
        ]
        request.extend(state['messages'])
        response = self.llm.invoke(request)
        return {'messages': [{'role': 'assistant', 'content': response.content}]}

    def support(self, state: State):
        '''
        This builds an SRE support case.
        Will continue to interact with the user until the support case is compiled.
        '''
        log.info('Routed to support()')
        # Get a structured response from the LLM
        support_llm = self.llm.with_structured_output(SupportCase)
        # Load the structured state.
        support_case = support_llm.invoke([
            SystemMessage(content=SUPPORT_VALIDATION_PROMPT),
            HumanMessage(content=state['messages'][-1].content)
        ])
        # Shallow copy of messages
        support_messages = [*state['messages']]
        log.debug(f'\x1b[36mSupport case\x1b[0m: {support_case.model_dump_json()}')
        while not support_case.is_valid():
            # Iterate asking questions until we get all the details.
            request = [
                SystemMessage(content=SUPPORT_PROMPT),
            ]
            # Make sure the model can see the conversation context.
            request.extend(support_messages)
            response = self.llm.invoke(request)
            support_messages.append(AIMessage(content=response.content))
            print(f'\x1b[34mSupport\x1b[0m: {response.content}')
            user_message = input('\x1b[32mSupport\x1b[0m: ')
            support_messages.append(HumanMessage(content=user_message))
            support_request = [
                SystemMessage(content=SUPPORT_VALIDATION_PROMPT),
            ]
            support_request.extend(support_messages)
            support_case = support_llm.invoke(support_request)
            log.debug(f'\x1b[36mSupport case\x1b[0m: {support_case.model_dump_json()}')

        log.info(f'Support case: {support_case.model_dump_json()}')
        log.warning('This is where I would create a JIRA ticket for the SRE folks and send a notification to the team.')
        return {'messages': [AIMessage(content=support_case.model_dump_json())]}

    def action(self, state: State):
        log.info('Routed to action()')
        request = [
            SystemMessage(content=ACTION_PROMPT),
        ]
        request.extend(state['messages'])
        response = self.llm.invoke(request)
        return {'messages': [AIMessage(content=response.content)]}


    def chatloop(self):
        '''
        Setup the chat scenario.
        Keep track of the conversation.
        Loop until the user exits.
        '''
        state = {
            'messages': [],
            'message_type': None
        }
        while True:
            message = input('Message: ')
            if message.lower() in ['exit', 'quit', 'bye', 'goodbye']:
                print('Goodbye!')
                break

            state['messages'].append(HumanMessage(content=message))
            state = self.graph.invoke(state)
            log.debug('Message count: ' + str(len(state['messages'])))

            print(f'{state["messages"][-1].type}: {state["messages"][-1].content}')
        return 0


def start_agent(config: dict) -> int:
    return ChatAgent(config).chatloop()
