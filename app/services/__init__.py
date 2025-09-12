def get_message_service():
    from .message_service import MessageService
    return MessageService()

def get_openai_service():
    from .AI.openai_service import OpenAIService
    return OpenAIService()

def get_instagram_service():
    from .platforms.instagram import InstagramService
    return InstagramService()

def get_telegram_service():
    from .platforms.telegram import TelegramService
    return TelegramService()

def get_mediator():
    from .mediator import Mediator
    return Mediator()
