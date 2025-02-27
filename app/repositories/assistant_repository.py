from sqlalchemy.orm import Session
from ..models.message import AssistantResponse

class AssistantRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_response(self, message_ids, response_text, sender_id):
        response = AssistantResponse(
            message_ids=message_ids,
            response_text=response_text,
            assistant_status="PENDING",
            instagram_status="PENDING",
            sender_id=sender_id
        )
        self.session.add(response)
        self.session.commit()

    def update_status(self, message_ids, assistant_status=None, instagram_status=None):
        query = self.session.query(AssistantResponse).filter(
            AssistantResponse.message_ids.contains(message_ids)
        )
        if assistant_status:
            query.update({"assistant_status": assistant_status}, synchronize_session=False)
        if instagram_status:
            query.update({"instagram_status": instagram_status}, synchronize_session=False)
        self.session.commit()