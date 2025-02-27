def get_message_service():
    from .message_service import MessageService
    return MessageService()

def get_openai_service():
    from .openai_service import OpenAIService
    return OpenAIService()

def get_instagram_service():
    from .instagram_service import InstagramService
    return InstagramService()

def get_mediator():
    from .mediator import Mediator
    return Mediator()
