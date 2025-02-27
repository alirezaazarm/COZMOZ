from datetime import datetime, timezone
from ..models.appsettings import AppSettings
from ..models.fixedresponse import FixedResponse
from ..models.base import SessionLocal
from ..models.product import Product
from ..config import Config
import requests
import json

class Backend:
    def __init__(self):
        self.fixed_responses_url = Config.BASE_URL + "/update/fixed-responses"
        self.app_setting_url = Config.BASE_URL + "/update/app-settings"
        self.headers = {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }

    def get_products(self):
        try:
            with SessionLocal() as db:
                products = db.query(Product).all()
                products_data = [
                    {
                        "ID": p.pID,
                        "Title": p.title,
                        "Price": json.loads(p.price) if isinstance(p.price, dict) else p.price,
                        "Additional info": json.loads(p.additional_info) if isinstance(p.additional_info, dict) else p.additional_info,
                        "Category": p.category,
                        "Stock status" : p.stock_status,
                        "Translated Title": p.translated_title,
                        "Vector Store ID": p.vector_store_ID,
                        "File ID": p.file_ID,
                        "Link": p.link
                    }
                    for p in products
                ]
                return products_data
        except Exception as e:
            print(f"Error fetching products: {e}")
            return []

    def app_settings_to_main(self):
        try:
            with SessionLocal() as db:
                setting = db.query(AppSettings).all()
                setting = [{s.key:s.value} for s in setting]

                response = requests.post(self.app_setting_url, headers=self.headers, json=setting)
                if response.status_code == 200:
                    return True
                else:
                    print(setting)
                    return False

        except Exception as e:
            return {"error in app_settings_to_main calling": str(e)}

    def fixedresponses_to_main(self, fixedresponses, incoming):
        data = {"fixed_responses":fixedresponses, "incoming":incoming}
        response = requests.post(self.fixed_responses_url, headers=self.headers, json=data)

        if response.status_code == 200:
            return True
        else:
            print(f"Request failed with status code: {response.status_code}")
            print(response.text)
            return False

    def get_app_setting(self, key):
        self.app_settings_to_main()
        try:
            with SessionLocal() as db:
                setting = db.query(AppSettings).filter(AppSettings.key == key).first()
                return setting.value if setting else None
        except Exception as e:
            return {"error in get_app_setting calling": str(e)}

    def update_is_active(self, key, value):
        try:
            with SessionLocal() as db:
                setting = db.query(AppSettings).filter(AppSettings.key == key).first()
                if not setting:
                    setting = AppSettings(key=key, value=value)
                    db.add(setting)
                else:
                    setting.value = value
                db.commit()
            self.app_settings_to_main()
        except Exception as e:
            return {"error in update_is_active": str(e)}

    def get_fixed_responses(self, incoming=None):
        try:
            with SessionLocal() as db:
                responses = db.query(FixedResponse).filter(FixedResponse.incoming == incoming).all()
                responses = [
                    {
                        "id": r.id,
                        "trigger_keyword": r.trigger_keyword,
                        "comment_response_text": r.comment_response_text,
                        "direct_response_text": r.direct_response_text,
                        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S.%f") if r.updated_at else None
                    }
                    for r in responses
                ]
                self.fixedresponses_to_main(responses, incoming)
                return responses
        except Exception as e:
            raise RuntimeError(f"Failed to fetch fixed responses: {str(e)}")

    def add_fixed_response(self, trigger, comment_response_text, direct_response_text, incoming):
        try:
            with SessionLocal() as db:
                new_response = FixedResponse(
                    trigger_keyword=trigger,
                    comment_response_text=comment_response_text if incoming == "Comment" else None,
                    direct_response_text=direct_response_text,
                    incoming=incoming,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_response)
                db.commit()
                db.refresh(new_response)
                return new_response.id
        except Exception as e:
            raise RuntimeError(f"Failed to add fixed response: {str(e)}")

    def update_fixed_response(self, response_id, trigger, comment_response_text, direct_response_text, incoming):
        try:
            with SessionLocal() as db:
                response = db.query(FixedResponse).filter(FixedResponse.id == response_id).first()
                if response:
                    response.trigger_keyword = trigger
                    response.comment_response_text = comment_response_text if incoming == "Comment" else None,
                    response.direct_response_text = direct_response_text
                    response.incoming = incoming
                    response.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(response)
                return True
        except Exception as e:
            raise RuntimeError(f"Failed to update fixed response: {str(e)}")

    def delete_fixed_response(self, response_id):
        try:
            with SessionLocal() as db:
                response = db.query(FixedResponse).filter(FixedResponse.id == response_id).first()
                if response:
                    db.delete(response)
                    db.commit()
                return True
        except Exception as e:
            raise RuntimeError(f"Failed to delete fixed response: {str(e)}")

    @staticmethod
    def format_updated_at(updated_at):
        if not updated_at:
            return "Never updated"

        try:
            # Handle timestamps without timezone info (assume UTC)
            updated_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)

            # Calculate time difference
            time_diff = datetime.now(timezone.utc) - updated_time
            days = time_diff.days
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes = remainder // 60

            if days > 0:
                return f"{days} day{'s' if days > 1 else ''}, {hours} hour{'s' if hours > 1 else ''} ago"
            elif hours > 0:
                return f"{hours} hour{'s' if hours > 1 else ''}, {minutes} minute{'s' if minutes > 1 else ''} ago"
            else:
                return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        except ValueError:
            return "Invalid timestamp"