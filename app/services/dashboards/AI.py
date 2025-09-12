import logging
import streamlit as st
import requests
import importlib
import io
from PIL import Image
from ...models.product import Product
from ...models.additional_info import Additionalinfo
from ...config import Config
from ...models.client import Client
from ..AI.openai_service import OpenAIService
from ..AI.img_search import process_image

logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class AppConstants:
    """Centralized configuration for icons and messages"""
    ICONS = {
        "scraper": ":building_construction:" ,
        "scrape": ":rocket:",
        "update": ":arrows_counterclockwise:" ,
        "ai": ":robot_face:",
        "delete": ":wastebasket:" ,
        "add": ":heavy_plus_sign:" ,
        "success": ":white_check_mark:" ,
        "error": ":x:" ,
        "preview": ":package:" ,
        "brain": ":brain:" ,
        "chat": ":speech_balloon:",
        "connect": ":link:",
        "instagram": ":camera:",
        "post": ":newspaper:",
        "story": ":film_frames:",
        "paper_and_pen": ":memo:",
        "previous": ":arrow_left:",
        "next": ":arrow_right:",
        "label": ":label:",
        "save": ":floppy_disk:",
        "model": ":brain:",
        "folder": ":open_file_folder:",
        "dashboard": ":bar_chart:",
        "data": ":page_facing_up:",
        "login": ":key:",
        "logout": ":door:",
        "user": ":bust_in_silhouette:",
        "magic": ":magic_wand:",
    }

    MESSAGES = {
        "scraping_start": "Scraping all products. This may take several minutes...",
        "update_start": "Checking for new products...",
        "processing_start": "Processing products - this may take several minutes..."
    }

class DataManagerBackend:
    def __init__(self, client_username=None):
        self.client_username = client_username
        self.client_data = None
        if self.client_username:
            self.client_data = Client.get_by_username(self.client_username)
            if not self.client_data:
                logging.error(f"Client '{self.client_username}' not found")
                raise ValueError(f"Client '{self.client_username}' not found")
            if self.client_data.get('status') != 'active':
                logging.error(f"Client '{self.client_username}' is not active")
                raise ValueError(f"Client '{self.client_username}' is not active")
            logging.info(f"DataManagerBackend initialized for client: {self.client_username}")
        else:
            logging.info("DataManagerBackend initialized without client context (admin mode)")
        self.app_setting_url = Config.BASE_URL + "/hooshang_update/app-settings"
        self.headers = {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }
        self.scraper = self._load_scraper()
        self.openai_service = OpenAIService(client_username=self.client_username) if self.client_username else None

    def _load_scraper(self):
        if not self.client_username:
            return None
        module_name = f"app.services.scrapers.{self.client_username}"
        try:
            scraper_module = importlib.import_module(module_name)
            return scraper_module.Scraper()
        except ModuleNotFoundError:
            logging.warning(f"No scraper found for client '{self.client_username}' (module: {module_name})")
            return None
        except AttributeError:
            logging.error(f"Scraper class not found in module '{module_name}'")
            return None

    def _validate_client_access(self, required_module=None):
        if not self.client_username:
            return True
        if not self.client_data:
            raise ValueError("Client data not loaded")
        if self.client_data.get('status') != 'active':
            raise ValueError(f"Client '{self.client_username}' is not active")
        if required_module:
            if not Client.is_module_enabled(self.client_username, required_module):
                raise ValueError(f"Module '{required_module}' is not enabled for client '{self.client_username}'")
        return True

    def reload_main_app_memory(self):
        logging.info("Triggering main app to reload memory from DB.")
        try:
            response = requests.post(
                Config.BASE_URL + "/hooshang_update/reload-memory",
                headers=self.headers
            )
            if response.status_code == 200:
                logging.info("Main app memory reload triggered successfully.")
                return True
            else:
                logging.error(f"Failed to trigger main app memory reload. Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logging.error(f"Error triggering main app memory reload: {str(e)}")
            return False

    def update_products(self):
        self._validate_client_access('scraper')
        logging.info(f"Scraping the site is starting for client: {self.client_username or 'admin'}")
        try:
            self.scraper.update_products()
            logging.info("Update products completed.")
        except Exception as e:
            logging.error(f"Failed to update products: {str(e)}", exc_info=True)
            return False
        try:
            self.reload_main_app_memory()
        except Exception as e:
            logging.error(f"Failed to send app settings: {e}")
        return True

    def get_products(self):
        self._validate_client_access()
        logging.info(f"Fetching products from the database for client: {self.client_username or 'admin'}")
        try:
            products = Product.get_all(client_username=self.client_username)
            products_data = [
                {
                    "Title": p['title'],
                    # Convert dict to string if it's a dict, otherwise use the value as is.
                    "Price": str(p['price']) if isinstance(p['price'], dict) else p['price'],
                    "Additional info": str(p['additional_info']) if isinstance(p['additional_info'], dict) else p['additional_info'],
                    "Category": p['category'],
                    "Stock status": p['stock_status'],
                    "Link": p['link']
                }
                for p in products
            ]
            logging.info(f"Successfully fetched {len(products_data)} products for client: {self.client_username or 'admin'}")
            return products_data
        except Exception as e:
            logging.error(f"Error fetching products: {e}")
            return []

    def get_additionalinfo(self, content_format="markdown"):
        self._validate_client_access()
        try:
            entries = Additionalinfo.get_by_format(content_format, client_username=self.client_username)
            result = []
            for entry in entries:
                item = {
                    "id": str(entry["_id"]),
                    "key": entry["title"],
                    "value": entry["content"],
                    "content_format": entry.get("content_format", "markdown")
                }
                result.append(item)
            return result
        except Exception as e:
            logging.error(f"Error fetching additional text entries: {str(e)}")
            return []

    def add_additionalinfo(self, key, value, content_format="markdown"):
        self._validate_client_access()
        logging.info(f"Adding/updating additional text: {key} for client: {self.client_username or 'admin'}")
        try:
            existing = Additionalinfo.search(key, client_username=self.client_username)
            if existing and len(existing) > 0:
                result = Additionalinfo.update(str(existing[0]['_id']), {
                    "title": key,
                    "content": value,
                    "content_format": content_format,
                    "client_username": self.client_username
                })
            else:
                result = Additionalinfo.create(title=key, content=value, client_username=self.client_username, content_format=content_format)
            if result:
                logging.info(f"Additional text '{key}' created/updated successfully for client: {self.client_username or 'admin'}")
                return True
            else:
                logging.error(f"Failed to create/update additional text '{key}'.")
                return False
        except Exception as e:
            logging.error(f"Error creating/updating additional text '{key}': {str(e)}")
            return False

    def delete_additionalinfo(self, key):
        self._validate_client_access()
        try:
            entries = Additionalinfo.search(key, client_username=self.client_username)
            if not entries or len(entries) == 0:
                logging.error(f"Additional text entry with title '{key}' not found for client: {self.client_username or 'admin'}")
                return False
            if entries[0].get('file_id'):
                if not self.openai_service:
                    logging.error("OpenAI service not initialized")
                    return False
                resp = self.openai_service.delete_single_file(entries[0]['file_id'])
                if resp:
                    result = Additionalinfo.delete(str(entries[0]['_id']))
                    if result:
                        logging.info(f"Additional text title '{key}' deleted from DB successfully for client: {self.client_username or 'admin'}")
                        return True
                    else:
                        logging.error(f"Failed to delete additional text title '{key}' from DB.")
                        return False
                else:
                    logging.error(f"Failed to delete file '{entries[0]['file_id']}' from openai.")
                    return False
            else:
                result = Additionalinfo.delete(str(entries[0]['_id']))
                if result:
                    logging.info(f"Additional text title '{key}' deleted from DB successfully for client: {self.client_username or 'admin'}")
                    return True
                else:
                    logging.error(f"Failed to delete additional text title '{key}' from DB.")
                    return False
        except Exception as e:
            logging.error(f"Error deleting additional text entry '{key}': {str(e)}")
            return False

    def rebuild_files_and_vs(self):
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return False
            scraper_update_products_success = self.update_products()
            if scraper_update_products_success:
                logging.info("Scraper successfully scraped the website")
                clear_success = self.openai_service.rebuild_all()
                if clear_success:
                    logging.info("Additional info + products files and vector store rebuilt successfully")
                    return True
                else:
                    logging.error("Failed to rebuild additional info files and vector store")
                    return False
            else:
                logging.error("the Sraper Failed to scrape the website")
                return False
        except Exception as e:
            logging.error(f"Error in rebuild_files_and_vs: {str(e)}")
            return False
        
class OpenAIBackend:
    def __init__(self, client_username=None):
        self.client_username = client_username
        self.client_data = None
        if self.client_username:
            self.client_data = Client.get_by_username(self.client_username)
            if not self.client_data:
                logging.error(f"Client '{self.client_username}' not found")
                raise ValueError(f"Client '{self.client_username}' not found")
            if self.client_data.get('status') != 'active':
                logging.error(f"Client '{self.client_username}' is not active")
                raise ValueError(f"Client '{self.client_username}' is not active")
            logging.info(f"OpenAIBackend initialized for client: {self.client_username}")
        else:
            logging.info("OpenAIBackend initialized without client context (admin mode)")
        self.openai_service = OpenAIService(client_username=self.client_username) if self.client_username else None

    def get_vs_id(self):
        logging.info("Fetching current vector store ID from client model.")
        try:
            if not self.client_username or not self.client_data:
                logging.warning("No client context loaded for get_vs_id.")
                return None
            vs_id = self.client_data.get('keys', {}).get('vector_store_id')
            if vs_id:
                logging.info(f"Current vector store ID: {vs_id}")
                return [vs_id]
            else:
                logging.info("No vector store ID found in client model.")
                return None
        except Exception as e:
            logging.error(f"Error fetching vector store ID: {str(e)}")
            return None

    def get_assistant_instructions(self):
        logging.info("Fetching assistant instructions.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return None
            instructions = self.openai_service.get_assistant_instructions()
            if instructions:
                logging.info("Assistant instructions retrieved successfully.")
            else:
                logging.warning("Failed to retrieve assistant instructions.")
            return instructions
        except Exception as e:
            logging.error(f"Error fetching assistant instructions: {str(e)}")
            return None

    def get_assistant_temperature(self):
        logging.info("Fetching assistant temperature.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return None
            temperature = self.openai_service.get_assistant_temperature()
            if temperature is not None:
                logging.info("Assistant temperature retrieved successfully.")
            else:
                logging.warning("Failed to retrieve assistant temperature.")
            return temperature
        except Exception as e:
            logging.error(f"Error fetching assistant temperature: {str(e)}")
            return None

    def get_assistant_top_p(self):
        logging.info("Fetching assistant top_p.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return None
            top_p = self.openai_service.get_assistant_top_p()
            if top_p is not None:
                logging.info("Assistant top_p retrieved successfully.")
            else:
                logging.warning("Failed to retrieve assistant top_p.")
            return top_p
        except Exception as e:
            logging.error(f"Error fetching assistant top_p: {str(e)}")
            return None

    def update_assistant_instructions(self, new_instructions):
        logging.info("Updating assistant instructions.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return {'success': False, 'message': 'OpenAI service not initialized'}
            result = self.openai_service.update_assistant_instructions(new_instructions)
            if result['success']:
                logging.info("Assistant instructions updated successfully.")
                return result
            else:
                logging.warning(f"Failed to update assistant instructions: {result['message']}")
                return result
        except Exception as e:
            logging.error(f"Error updating assistant instructions: {str(e)}")
            return {'success': False, 'message': str(e)}

    def update_assistant_temperature(self, new_temperature):
        logging.info("Updating assistant temperature.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return {'success': False, 'message': 'OpenAI service not initialized'}
            result = self.openai_service.update_assistant_temperature(new_temperature)
            if result['success']:
                logging.info("Assistant temperature updated successfully.")
                return result
            else:
                logging.warning(f"Failed to update assistant temperature: {result['message']}")
                return result
        except Exception as e:
            logging.error(f"Error updating assistant temperature: {str(e)}")
            return {'success': False, 'message': str(e)}

    def update_assistant_top_p(self, new_top_p):
        logging.info("Updating assistant top_p.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                return {'success': False, 'message': 'OpenAI service not initialized'}
            result = self.openai_service.update_assistant_top_p(new_top_p)
            if result['success']:
                logging.info("Assistant top_p updated successfully.")
                return result
            else:
                logging.warning(f"Failed to update assistant top_p: {result['message']}")
                return result
        except Exception as e:
            logging.error(f"Error updating assistant top_p: {str(e)}")
            return {'success': False, 'message': str(e)}

    def create_chat_thread(self):
        logging.info("Creating new chat thread.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                raise Exception("OpenAI service not initialized")
            thread_id = self.openai_service.create_thread()
            logging.info(f"Chat thread created successfully with ID: {thread_id}")
            return thread_id
        except Exception as e:
            logging.error(f"Failed to create chat thread: {str(e)}", exc_info=True)
            raise

    def send_message_to_thread(self, thread_id, user_message):
        logging.info(f"Sending message to thread {thread_id}.")
        try:
            if not self.openai_service:
                logging.error("OpenAI service not initialized")
                raise Exception("OpenAI service not initialized")
            response = self.openai_service.send_message_to_thread(thread_id, user_message)
            logging.info(f"Message sent to thread {thread_id} successfully.")
            return response
        except Exception as e:
            logging.error(f"Failed to send message to thread {thread_id}: {str(e)}", exc_info=True)
            raise

    def process_uploaded_image(self, image_bytes):
        logging.info(f"Processing uploaded image ({len(image_bytes)} bytes).")
        if not image_bytes:
            logging.warning("Received empty image bytes.")
            return "Error: No image data received."
        try:
            image_stream = io.BytesIO(image_bytes)
            pil_image = Image.open(image_stream)
            analysis_result = process_image(pil_image, self.client_username)
            logging.info(f"Image processing result: {analysis_result}")
            return analysis_result
        except Image.UnidentifiedImageError:
            logging.error("Could not identify image file. It might be corrupted or not an image.")
            return "Error: Could not read image file. Please upload a valid image."
        except Exception as e:
            logging.error(f"Error processing uploaded image in backend: {str(e)}", exc_info=True)
            return f"Error: An unexpected error occurred while processing the image."

class BaseSection:
    """Base class for UI sections"""
    def __init__(self, client_username=None):
        self.client_username = client_username
        self.const = AppConstants()

#===============================================================================================================================
# Main Streamlit UI Class
#===============================================================================================================================
class OpenAIManagementUI(BaseSection):
    """Handles all UI for AI and Data Management."""
    def __init__(self, client_username=None):
        super().__init__(client_username)
        try:
            self.backend = OpenAIBackend(client_username=self.client_username)
            self.data = DataManagerBackend(client_username=self.client_username)
        except Exception as e:
            logging.error(f"Failed to initialize backends: {str(e)}")
            self.backend = None
            self.data = None

    def render(self):
        if not self.backend or not self.data:
            st.error("A service is not properly configured. Please ensure you have a valid client configuration.")
            st.info("Contact your administrator to set up the integration.")
            return

        vs_id = self.backend.get_vs_id()

        settings_tab, chat_tab, data_tab = st.tabs([
            f"{self.const.ICONS['brain']} Assistant Settings",
            f"{self.const.ICONS['chat']} Test Assistant",
            f"{self.const.ICONS['data']} Data"
        ])

        with settings_tab:
            self._render_settings_section()

        with chat_tab:
            if vs_id is not None:
                self._render_chat_testing_section()
            else:
                st.error("You need a Vector Store before testing the assistant.")
                st.info("You can build the Vector Store from the 'Data' tab.")

        with data_tab:
            self._render_data_section()

        st.markdown("---")

    def _render_data_section(self):
        """Renders the entire data management UI."""
        self._render_action_buttons()
        self._render_product_table_only()
        st.write("---")
        self._render_additional_info_section()
        st.write("---")

    def _render_action_buttons(self):
        """Renders top action buttons like Update Products and Rebuild VS."""
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"{self.const.ICONS['update']} Update Products",
                        help="Add new products only", width='stretch'):
                self._handle_scraping_action(self.data.update_products)

        with col2:
            if st.button(f"{self.const.ICONS['brain']} Rebuild VS",
                        key="update_vs_btn_top",
                        help="Rebuild Vector Store for all data. This may take time.",
                        width='stretch'):
                try:
                    with st.spinner("Rebuilding Vector Store... Please wait."):
                        success = self.data.rebuild_files_and_vs()
                        if success:
                            st.success(f"{self.const.ICONS['success']} AI data rebuilt successfully!")
                        else:
                            st.error(f"{self.const.ICONS['error']} Failed to rebuild AI data.")
                except Exception as e:
                    st.error(f"{self.const.ICONS['error']} Error during rebuild: {str(e)}")

    def _handle_scraping_action(self, action_function):
        """Handles the execution of scraping-related actions."""
        try:
            with st.spinner(self.const.MESSAGES.get("update_start", "Processing...")):
                action_function()
                st.success(f"{self.const.ICONS['success']} Operation completed!")
                st.rerun()
        except Exception as e:
            logging.error(f"Scraping action failed: {e}", exc_info=True)
            st.error(f"{self.const.ICONS['error']} Operation failed: {str(e)}")

    def _render_product_table_only(self):
        """Renders only the product table."""
        st.subheader(f"{self.const.ICONS['preview']} Product Table")
        try:
            products = self.data.get_products()
            if products:
                st.dataframe(
                    products,
                    column_config={ "Link": st.column_config.LinkColumn("Product Link"), },
                    width='stretch',
                    height=400
                )
            else:
                st.info("No products found. Click 'Update Products' to get started.")
        except Exception as e:
            logging.error(f"Failed to load products: {e}", exc_info=True)
            st.error(f"Failed to load products: {str(e)}")

    def _render_additional_info_section(self):
        """Renders the 'Additional info' section."""
        st.subheader(f"{self.const.ICONS['paper_and_pen']} Additional info")
        edit_tab, add_tab = st.tabs(["Edit Existing", "Add New"])
        with add_tab:
            with st.form(key="add_additionalinfo_form"):
                title = st.text_input("Title", placeholder="Enter a descriptive title")
                text = st.text_area("Text", height=150, placeholder="Enter your text content here")
                submit = st.form_submit_button(f"{self.const.ICONS['save']} Save Info", width='stretch')
            if submit:
                if not title.strip() or not text.strip():
                    st.error("Title and Text content are required.")
                else:
                    with st.spinner("Saving..."):
                        success = self.data.add_additionalinfo(title.strip(), text.strip())
                        if success: st.success(f"'{title.strip()}' saved successfully!")
                        else: st.error(f"Failed to save '{title.strip()}'.")
        with edit_tab:
            app_settings = self.data.get_additionalinfo()
            if not app_settings:
                st.info("No saved info found. Use the 'Add New' tab to create some.")
            else:
                if 'editing_app_setting_key' not in st.session_state:
                    st.session_state['editing_app_setting_key'] = None
                for setting in app_settings:
                    key = setting["key"]
                    value = setting["value"]
                    if st.session_state.get('editing_app_setting_key') == key:
                        with st.container(border=True):
                            with st.form(key=f"edit_app_setting_form_{key}"):
                                st.subheader(f"Editing: {key}")
                                new_value = st.text_area("Content", value=value, key=f"edit_value_{key}", height=200, label_visibility="collapsed")
                                col1, col2 = st.columns(2)
                                with col1: update_btn = st.form_submit_button(f"{self.const.ICONS['save']} Update", width='stretch')
                                with col2: cancel_btn = st.form_submit_button("Cancel", type="secondary", width='stretch')
                            if update_btn:
                                if not new_value.strip(): st.error("Text content cannot be empty.")
                                else:
                                    with st.spinner(f"Updating '{key}'..."):
                                        success = self.data.add_additionalinfo(key, new_value.strip())
                                        if success:
                                            st.success(f"'{key}' updated successfully!")
                                            st.session_state['editing_app_setting_key'] = None
                                            st.rerun()
                                        else: st.error(f"Failed to update '{key}'.")
                            elif cancel_btn:
                                st.session_state['editing_app_setting_key'] = None
                                st.rerun()
                    else:
                        item_cols = st.columns([0.7, 0.15, 0.15])
                        with item_cols[0]: st.markdown(f"**{key}**")
                        with item_cols[1]:
                            if st.button("Edit", key=f"edit_btn_{key}", width='stretch', type="secondary"):
                                st.session_state['editing_app_setting_key'] = key
                                st.rerun()
                        with item_cols[2]:
                            if st.button(f"{self.const.ICONS['delete']}", key=f"remove_btn_{key}", width='stretch', help=f"Delete '{key}'"):
                                with st.spinner(f"Deleting '{key}'..."):
                                    success = self.data.delete_additionalinfo(key)
                                    if success:
                                        st.success(f"'{key}' deleted successfully!")
                                        if st.session_state.get('editing_app_setting_key') == key:
                                            st.session_state['editing_app_setting_key'] = None
                                        st.rerun()
                                    else: st.error(f"Failed to delete '{key}'.")
                        st.divider()

    def _render_settings_section(self):
        current_instructions = self.backend.get_assistant_instructions()
        current_temperature = self.backend.get_assistant_temperature()
        current_top_p = self.backend.get_assistant_top_p()
        default_temperature = 1.0 if current_temperature is None else current_temperature
        default_top_p = 1.0 if current_top_p is None else current_top_p
        new_instructions = st.text_area("Assistant Instructions", value=current_instructions or "", height=600, help="How the assistant should behave", label_visibility="collapsed")
        col1, col2, col3 = st.columns([4, 2, 4])
        with col1: new_temperature = st.slider("Temperature", 0.0, 2.0, float(default_temperature), 0.01, help="Randomness (0=strict, 2=creative)")
        with col2:
            st.write("")
            update_btn = st.button(f"{self.const.ICONS['update']} Update All", width='stretch', help="Save all settings")
            st.write("")
        with col3: new_top_p = st.slider("Top-P", 0.0, 1.0, float(default_top_p), 0.01, help="Focus (1=broad, 0=narrow)")
        if update_btn:
            with st.spinner("Saving..."):
                results = {
                    'instructions': self.backend.update_assistant_instructions(new_instructions),
                    'temperature': self.backend.update_assistant_temperature(new_temperature),
                    'top_p': self.backend.update_assistant_top_p(new_top_p)
                }
                if all(r['success'] for r in results.values()):
                    st.success(f"{self.const.ICONS['success']} All settings saved!")
                else:
                    errors = [f"{name}: {result['message']}" for name, result in results.items() if not result['success']]
                    st.error(f"{self.const.ICONS['error']} Issues: {', '.join(errors)}")

    def _render_chat_testing_section(self):
        st.subheader("Test your assistant")
        if 'thread_id' not in st.session_state:
            try:
                st.session_state['thread_id'] = self.backend.create_chat_thread()
                st.session_state['messages'] = []
                st.session_state['user_message_sent'] = True
                st.session_state['processed_file_ids'] = set()
            except Exception as e:
                st.error(f"Failed to create thread: {str(e)}")
                return
        if 'processed_file_ids' not in st.session_state:
             st.session_state['processed_file_ids'] = set()
        chat_container = st.container(height=400)
        input_container = st.container()
        new_user_input = None
        with input_container:
            uploaded_file = st.file_uploader("Upload an image (optional)", type=None)
            if uploaded_file and uploaded_file.file_id not in st.session_state['processed_file_ids']:
                with st.spinner("Analyzing image..."):
                    try:
                        st.session_state['processed_file_ids'].add(uploaded_file.file_id)
                        if uploaded_file.type.startswith('image/'):
                            image_bytes = uploaded_file.getvalue()
                            analysis_result = self.backend.process_uploaded_image(image_bytes)
                            new_user_input = f"Analysis of uploaded image: {analysis_result}"
                            with chat_container:
                                with st.chat_message("user"):
                                    st.image(image_bytes, width=150)
                                    st.write(new_user_input)
                        else: st.error("Please upload an image file (JPG, PNG, etc.)")
                    except Exception as e: st.error(f"Error handling image upload: {str(e)}")
            user_text_input = st.chat_input("Type your message here...")
            if user_text_input: new_user_input = user_text_input
        if new_user_input:
            st.session_state['messages'].append({"role": "user", "content": new_user_input})
            st.session_state['user_message_sent'] = False
        with chat_container:
            for message in st.session_state.get('messages', []):
                 with st.chat_message(message["role"]):
                     st.write(message["content"])
        if not st.session_state.get('user_message_sent', True):
            last_message = st.session_state['messages'][-1]
            if last_message["role"] == "user":
                with st.spinner("Assistant is thinking..."):
                    try:
                        response = self.backend.send_message_to_thread(st.session_state['thread_id'], last_message["content"])
                        st.session_state['messages'].append({"role": "assistant", "content": response})
                        st.session_state['user_message_sent'] = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error getting response: {str(e)}")
                        st.session_state['user_message_sent'] = True