from ...utils.exceptions import PermanentError, RetryableError
from ...models.product import Product
from ...models.additional_info import Additionalinfo
from ...models.client import Client
from ...models.enums import Platform,ModuleType
from ...models.database import db
from ...config import Config
import openai
import time
import re
import logging
import json
from datetime import datetime, timezone
from ...models.enums import ModuleType
from ...utils.helpers import get_app_settings
from ...repositories.orderbook_repository import OrderbookRepository

logger = logging.getLogger(__name__)

def clean_sources(response_text):
    metadata_patterns = [
        r'\[\d+:\d+:source\]',
        r'【\d+:\d+†source】',
        r'\[\d+:\d+\]',
        r'【\d+:\d+】',
        r'\(\d+:\d+\)',
    ]
    for pattern in metadata_patterns:
        response_text = re.sub(pattern, "", response_text)
    return response_text

class OpenAIService:
    MAX_UPLOAD_RETRIES = 5
    UPLOAD_RETRY_DELAY = 2
    BATCH_SIZE = 30
    # Shared OpenAI client for all instances (API key is constant)
    openai_client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)

    def __init__(self, client_username=None):
        """
        OpenAIService is initialized with a client_username, which is used to fetch user-specific data
        from your own database/models. The OpenAI client is shared and constant for all users.
        """
        if not client_username:
            raise ValueError("Must provide client_username")
        self.client_username = client_username
        self.client_obj = Client.get_by_username(client_username)
        if not self.client_obj:
            raise ValueError(f"Client not found: {client_username}")
        # Use the shared OpenAI client
        self.client = self.__class__.openai_client

    # ------------------------------------------------------------------
    # Files and Vector Store (per client)
    # ------------------------------------------------------------------
    def delete_single_file(self, file_id) -> bool:
        try:
            resp = self.client.files.delete(file_id)
            if resp.deleted:
                logger.info(f"File with the ID {file_id} has deleted successfully")
                return True
            else:
                logger.error(f"Failed to delete file '{file_id}': {getattr(resp, 'error', None)}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file '{file_id}': {e}")
            return False

    def clear_vs(self) -> bool:
        assert self.client_obj is not None, "client_obj should never be None here"
        vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
        if not vs_id:
            logger.info("No vector store ID found for client")
            return True
        try:
            # Requires openai>=1.74.0
            response = self.client.vector_stores.delete(vs_id)
            if response.deleted:
                # Remove vector_store_id from client
                Client.update(self.client_username, {"keys.vector_store_id": None})
                logger.info(f"Deleted vector store '{vs_id}' and unset vector_store_id in client")
                return True
            logger.error(f"Vector store deletion returned deleted=False for '{vs_id}'")
            return False
        except Exception as e:
            logger.error(f"Failed to delete vector store '{vs_id}': {e}")
            return False

    def clear_files(self, model_cls) -> bool:
        entries = model_cls.get_all(client_username=self.client_obj['username'])
        success = True

        # Get all entry titles to match against OpenAI files
        entry_titles = set()
        for entry in entries:
            title = entry.get('title')
            if title:
                entry_titles.add(f"{title}.json")  # Files are uploaded with .json extension

        # Get all files from OpenAI and find matches by filename
        try:
            openai_files = self.client.files.list(purpose='assistants')
            files_to_delete = []

            for file_obj in openai_files.data:
                filename = getattr(file_obj, 'filename', '')
                if filename in entry_titles:
                    files_to_delete.append(file_obj.id)
                    logger.info(f"Found file to delete: {filename} (ID: {file_obj.id})")

            # Delete all matching files from OpenAI
            for file_id in files_to_delete:
                try:
                    resp = self.client.files.delete(file_id)
                    if resp.deleted:
                        logger.info(f"Deleted file '{file_id}' from OpenAI")
                    else:
                        logger.error(f"Failed to delete file '{file_id}': {getattr(resp, 'error', None)}")
                        success = False
                except Exception as e:
                    logger.error(f"Error deleting file '{file_id}': {e}")
                    success = False

        except Exception as e:
            logger.error(f"Error listing files from OpenAI: {e}")
            success = False

        # Reset file_id in database entries to None
        for entry in entries:
            try:
                identifier = entry.get('title') if model_cls is Product else str(entry.get('_id'))
                model_cls.update(identifier, {"file_id": None}, client_username=self.client_obj['username'])
                logger.info(f"Reset file_id for '{identifier}'")
            except Exception as e:
                logger.error(f"Error resetting file_id for entry '{identifier}': {e}")
                success = False

        return success

    def upload_files(self, model_cls, folder_name: str) -> bool:
        entries = model_cls.get_all(client_username=self.client_username)
        all_success = True
        import io
        for entry in entries:
            content_data = self._prepare_content(entry, folder_name)
            content = json.dumps(content_data, ensure_ascii=False)
            file_id = self._retry_upload(entry, content)
            if not file_id:
                all_success = False
                continue
            identifier = entry.get('title') if model_cls is Product else str(entry.get('_id'))
            updated = model_cls.update(identifier, {"file_id": file_id}, client_username=self.client_username)
            if not updated:
                logger.error(f"Failed to update database for '{identifier}' with file_id '{file_id}'")
                all_success = False
        return all_success

    def _prepare_content(self, entry, folder_name: str) -> dict:
        if folder_name == 'products':
            return {
                'title': entry['title'],
                'price': entry['price'],
                'description': entry['description'],
                'additional_info': entry.get('additional_info'),
                'category': entry['category'],
                'tags': entry.get('tags'),
                'excerpt': entry.get('excerpt'),
                'link': entry.get('link')
            }
        else: # additionalinfo
            if entry["content_format"] == "json":
                return entry["content"]

            else: #markdown
                return {
                    'title': entry['title'],
                    'category': folder_name,
                    'content': entry['content']
                }

    def _retry_upload(self, entry, content: str) -> str | None:
        retry = 0
        file_id = None
        import io
        while retry < self.MAX_UPLOAD_RETRIES:
            try:
                # OpenAI expects file as (filename, fileobj) or (filename, fileobj, content_type)
                file_bytes = io.BytesIO(content.encode('utf-8'))
                resp = self.client.files.create(
                    file=(f"{entry['title']}.json", file_bytes, 'application/json'),
                    purpose='assistants'
                )
                file_id = resp.id
                logger.info(f"Uploaded file id={file_id} for '{entry['title']}'")
                self._wait_for_processing(file_id)
                return file_id
            except Exception as e:
                retry += 1
                logger.warning(f"Upload error for '{entry['title']}' (attempt {retry}): {e}")
                time.sleep(self.UPLOAD_RETRY_DELAY)
        logger.error(f"Exceeded retries uploading '{entry['title']}'")
        return None

    def _wait_for_processing(self, file_id: str):
        timeout = 60
        interval = 2
        waited = 0
        while waited < timeout:
            resp = self.client.files.retrieve(file_id)
            if resp.status == 'processed':
                return
            if resp.status == 'error':
                raise Exception(f"File {file_id} processing error: {getattr(resp, 'error', None)}")
            time.sleep(interval)
            waited += interval
        raise TimeoutError(f"Timeout waiting for file {file_id} to process")

    def create_vs(self) -> str | None:
        try:
            products = Product.get_all(client_username=self.client_username)
            additional = Additionalinfo.get_all(client_username=self.client_username)
            prod_ids = [p['file_id'] for p in products if p.get('file_id')]
            add_ids = [a['file_id'] for a in additional if a.get('file_id')]
            missing = [p['title'] for p in products if not p.get('file_id')]
            if missing:
                logger.error(f"Cannot create VS: missing product file_ids for {missing}")
                return None
            file_ids = prod_ids + add_ids
            self.clear_vs()
            # Requires openai>=1.74.0
            vs = self.client.vector_stores.create(
                name=f"Vector Store - {self.client_username}",
                file_ids=file_ids[:self.BATCH_SIZE],
                chunking_strategy={
                    'type': 'static',
                    'static': {'max_chunk_size_tokens': 1000, 'chunk_overlap_tokens': 500}
                }
            )
            vs_id = vs.id
            logger.info(f"Created vector store {vs_id} for first batch")
            for i in range(self.BATCH_SIZE, len(file_ids), self.BATCH_SIZE):
                batch = file_ids[i:i + self.BATCH_SIZE]
                self.client.vector_stores.file_batches.create_and_poll(
                    vector_store_id=vs_id,
                    file_ids=batch,
                    chunking_strategy={
                        'type': 'static',
                        'static': {'max_chunk_size_tokens': 1000, 'chunk_overlap_tokens': 500}
                    }
                )
                logger.info(f"Appended batch files {i}-{i + len(batch)} to vector store {vs_id}")
            final_vs = self.client.vector_stores.retrieve(vs_id)
            if final_vs.file_counts.completed == len(file_ids):
                Client.update(self.client_username, {"keys.vector_store_id": vs_id})
                logger.info(f"Stored vector_store_id '{vs_id}' in client")
                # Attach the vector store to the client's assistant as well
                attach_result = self.set_assistant_vector_store(vs_id)
                if not attach_result.get('success'):
                    logger.error(f"Failed to attach vector store to assistant: {attach_result.get('message')}")
                return vs_id
            logger.error(f"Vector store incomplete: {final_vs.file_counts}")
            return None
        except Exception as e:
            logger.error(f"Error in create_vs: {e}")
            return None

    def rebuild_all(self) -> bool:
        ok1 = self.clear_files(Product)
        Client.append_log(self.client_username, 'clear_files_product', 'success' if ok1 else 'failure')
        ok2 = self.clear_files(Additionalinfo)
        Client.append_log(self.client_username, 'clear_files_additionalinfo', 'success' if ok2 else 'failure')
        ok3 = self.upload_files(Product, 'products')
        Client.append_log(self.client_username, 'upload_files_product', 'success' if ok3 else 'failure')
        ok4 = self.upload_files(Additionalinfo, 'info')
        Client.append_log(self.client_username, 'upload_files_additionalinfo', 'success' if ok4 else 'failure')
        if not (ok1 and ok2 and ok3 and ok4):
            Client.append_log(self.client_username, 'rebuild_all', 'failure', details='One or more clear/upload steps failed')
            # Disable DM_ASSIST module if any step failed
            Client.update_module_status(self.client_username, Platform.INSTAGRAM._value_, ModuleType.DM_ASSIST.value , False)
            Client.update_module_status(self.client_username, Platform.TELEGRAM._value_, ModuleType.DM_ASSIST.value , False)
            Client.append_log(self.client_username, 'disable_dm_assist', 'success', details='Disabled DM_ASSIST for all platforms due to rebuild_all failure')
        else:
            Client.append_log(self.client_username, 'rebuild_all', 'success')
        vs_id = self.create_vs()
        if not vs_id:
            Client.append_log(self.client_username, 'create_vs', 'failure')
            # Disable DM_ASSIST module if vector store creation failed
            Client.update_module_status(self.client_username, Platform.INSTAGRAM._value_, ModuleType.DM_ASSIST.value , False)
            Client.update_module_status(self.client_username, Platform.TELEGRAM._value_, ModuleType.DM_ASSIST.value , False)
            Client.append_log(self.client_username, 'disable_dm_assist', 'success', details='Disabled DM_ASSIST for all platforms due to create_vs failure')
            return False
        Client.append_log(self.client_username, 'create_vs', 'success')
        return True

    # ------------------------------------------------------------------
    # Chat/Assistant config (per client)
    # ------------------------------------------------------------------
    def ensure_thread(self, user):
        try:
            thread_id = user.get('thread_id')
            if thread_id:
                try:
                    thread = self.client.beta.threads.retrieve(thread_id)
                    logger.debug(f"Thread {thread.id} exists")
                    return thread.id
                except openai.APIError:
                    logger.error("Existing thread invalid, creating new one")
            vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
            if not vs_id:
                logger.error("No valid vector store ID found in client.")
                raise PermanentError("No valid vector store ID found in client.")
            thread = self.client.beta.threads.create(
                tool_resources={"file_search": {"vector_store_ids": [vs_id]}}
            )
            logger.debug(f"Created thread {thread.id}")
            user_id = user.get('user_id')
            if not user_id:
                raise ValueError("User document is missing user_id field")
            result = db.users.update_one(
                {"user_id": user_id},
                {"$set": {"thread_id": thread.id, "updated_at": datetime.now(timezone.utc)}}
            )
            if result.modified_count == 0:
                logger.warning(f"Failed to update user {user_id} with thread ID")
            else:
                logger.debug(f"Updated user {user_id} with thread ID {thread.id}")
            return thread.id
        except openai.APIError as e:
            logger.critical(f"OpenAI API Failure: {e.message}")
            raise RetryableError("OpenAI API unavailable")
        except Exception as e:
            logger.critical(f"Thread creation failed: {str(e)}", exc_info=True)
            raise PermanentError("Thread creation permanently failed")

    def process_messages(self, thread_id, message_texts):
        logger.info(f"Processing {len(message_texts)} messages for thread_id: {thread_id}")
        try:
            self.wait_for_active_run_completion(thread_id)
            if len(message_texts) > 1:
                message_content = "\n---\n".join(message_texts)
            else:
                message_content = message_texts[0]
            logger.debug(f"Message content prepared for thread_id: {thread_id}")
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_content
            )
            logger.info(f"User message batch created for thread_id: {thread_id}")
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                raise PermanentError("No assistant_id found in client keys")
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )
            logger.info(f"Run created with ID: {run.id} for thread_id: {thread_id}")
            start = time.time()
            while run.status not in ["completed", "failed", "cancelled"]:
                if time.time() - start > 300:
                    logger.error(f"Timeout occurred while waiting for run completion for thread_id: {thread_id}")
                    raise TimeoutError("OpenAI timeout")
                time.sleep(5)
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                logger.debug(f"Run status for thread_id: {thread_id}: {run.status}")
            if run.status != "completed":
                logger.error(f"Run failed for thread_id: {thread_id}. Last error: {run.last_error}")
                raise openai.OpenAIError(f"Run failed: {run.last_error}")
            logger.info(f"Run completed successfully for thread_id: {thread_id}")
            # Handle tool/function calls if present
            tool_response = self.handle_tool_calls(thread_id, run)
            if tool_response is not None:
                return tool_response
            return clean_sources(self._get_assistant_response(thread_id))
        except openai.APIError as e:
            logger.error(f"OpenAI API Error for thread_id: {thread_id}: {e.message}")
            raise RetryableError(f"API Error: {e.message}") from e
        except Exception as e:
            logger.error(f"Unexpected error while processing messages for thread_id: {thread_id}: {str(e)}")
            raise

    def _get_assistant_response(self, thread_id):
        logger.info(f"Retrieving assistant response for thread_id: {thread_id}")
        try:
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id, order="desc", limit=1
            )
            if not messages.data:
                logger.error(f"No messages found in thread_id: {thread_id}")
                raise ValueError("No messages in thread")
            latest_message = messages.data[0]
            logger.debug(f"Latest message retrieved for thread_id: {thread_id}")
            text_content = None
            for c in latest_message.content:
                if getattr(c, 'type', None) == "text" and hasattr(c, 'text') and hasattr(c.text, 'value'):
                    text_content = c.text.value
                    break
            if not text_content or not text_content.strip():
                logger.error(f"Empty response from assistant for thread_id: {thread_id}")
                raise ValueError("Empty response from assistant")
            logger.info(f"Assistant response successfully retrieved for thread_id: {thread_id}")
            return text_content
        except openai.APIError as e:
            logger.error(f"OpenAI API Error while retrieving response for thread_id: {thread_id}: {e.message}")
            raise RetryableError(f"OpenAI API Error: {e.message}")
        except Exception as e:
            logger.error(f"Error parsing assistant response for thread_id: {thread_id}: {str(e)}")
            raise PermanentError(f"Response parsing failed: {str(e)}")

    def wait_for_active_run_completion(self, thread_id):
        try:
            while True:
                runs = self.client.beta.threads.runs.list(thread_id=thread_id)
                active_runs = [run for run in runs.data if run.status in ["queued", "in_progress"]]
                if not active_runs:
                    break
                logger.info(f"Waiting for {len(active_runs)} active runs to complete...")
                time.sleep(5)
        except openai.APIError as e:
            logger.error(f"Failed to check active runs: {e.message}")
            raise RetryableError("Failed to check active runs")

    def get_assistant_instructions(self):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return None
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return None
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            logger.info(f"Retrieved assistant instructions successfully.")
            return assistant.instructions
        except Exception as e:
            logger.error(f"Failed to retrieve assistant instructions: {str(e)}")
            return None

    def get_assistant_temperature(self):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return None
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return None
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            logger.info(f"Retrieved assistant temperature successfully.")
            return assistant.temperature
        except Exception as e:
            logger.error(f"Failed to retrieve assistant temperature: {str(e)}")
            return None

    def get_assistant_top_p(self):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return None
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return None
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            logger.info(f"Retrieved assistant top_p successfully.")
            return assistant.top_p
        except Exception as e:
            logger.error(f"Failed to retrieve assistant top_p: {str(e)}")
            return None

    def _build_tools_and_resources(self, vs_id_override: str | None = None):
        """
        Build the tools and tool_resources for the assistant based on client config.
        Always includes file_search if vector store is present.
        Adds orderbook functions if the orderbook module is enabled (from APP_SETTINGS).
        Returns: (tools, tool_resources)
        """
        tools = []
        tool_resources = {}
        vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
        if vs_id_override is not None:
            vs_id = vs_id_override
        if vs_id:
            tools.append({"type": "file_search"})
            tool_resources["file_search"] = {"vector_store_ids": [vs_id]}
        # Check if orderbook module is enabled in APP_SETTINGS
        orderbook_enabled = False
        app_settings = get_app_settings(self.client_username)
        # The helpers.py loader sets app_settings[ModuleType.ORDERBOOK.value] = True/False
        if app_settings.get(ModuleType.ORDERBOOK.value, False):
            orderbook_enabled = True
        if orderbook_enabled:
            # Add create_order function
            tools.append({
                "type": "function",
                "function": {
                    "name": "create_order",
                    "description": "ثبت سفارش جدید",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tx_id": {"type": "integer", "description": "شماره ارجاع(یا مرجع) تراکنش"},
                            "first_name": {"type": "string", "description": "نام سفارش دهنده"},
                            "last_name": {"type": "string", "description": "نام خانوادگی سفارش دهنده"},
                            "address": {"type": "string", "description": "آدرس (نشانی) سفارش دهنده"},
                            "phone": {"type": "string", "description": "شماره تلفن سفارش دهنده"},
                            "product": {"type": "string", "description": "عنوان محصول خریداری شده"},
                            "price": {"type": "string", "description": "قیمت محصول خریداری شده"},
                            "count": {"type": "string", "description": "تعداد سفارش از محصول موردنظر"}
                        },
                        "required": ["tx_id", "first_name", "last_name", "address", "phone", "product", "price", "count"]
                    }
                }
            })
            # Add check_order function
            tools.append({
                "type": "function",
                "function": {
                    "name": "check_order",
                    "description": "پیگیری سفارش با شماره ارجاع(یا مرجع) تراکنش",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tx_id": {"type": "integer", "description": "شماره ارجاع(یا مرجع) تراکنش"}
                        },
                        "required": ["tx_id"]
                    }
                }
            })
        return tools, tool_resources if tool_resources else None

    def set_assistant_vector_store(self, vs_id: str):
        """
        Attach the provided vector store ID to the client's assistant by
        updating tools and tool_resources accordingly.
        """
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return {'success': False, 'message': 'No assistant_id found in client keys.'}
            tools, tool_resources = self._build_tools_and_resources(vs_id_override=vs_id)
            self.client.beta.assistants.update(
                assistant_id=assistant_id,
                tools=tools,
                tool_resources=tool_resources
            )
            logger.info(f"Attached vector store {vs_id} to assistant {assistant_id} successfully.")
            return {'success': True, 'message': 'Vector store attached to assistant.'}
        except Exception as e:
            logger.error(f"Failed to attach vector store to assistant: {str(e)}")
            return {'success': False, 'message': f"Failed to attach vector store: {str(e)}"}

    def update_assistant_instructions(self, new_instructions):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return {'success': False, 'message': 'No assistant_id found in client keys.'}
            tools, tool_resources = self._build_tools_and_resources()
            update_params = {
                "assistant_id": assistant_id,
                "instructions": new_instructions
            }
            if tools:
                update_params["tools"] = tools
            if tool_resources:
                update_params["tool_resources"] = tool_resources
            self.client.beta.assistants.update(**update_params)
            logger.info("Updated assistant instructions successfully.")
            return {
                'success': True,
                'message': 'Assistant instructions updated successfully.'
            }
        except Exception as e:
            logger.error(f"Failed to update assistant instructions: {str(e)}")
            return {'success': False, 'message': f"Failed to update: {str(e)}"}

    def update_assistant_temperature(self, new_temperature):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return {'success': False, 'message': 'No assistant_id found in client keys.'}
            self.client.beta.assistants.update(
                assistant_id=assistant_id,
                temperature=new_temperature
            )
            logger.info("Updated assistant temperature successfully.")
            return {
                'success': True,
                'message': 'Assistant temperature updated successfully.'
            }
        except Exception as e:
            logger.error(f"Failed to update assistant temperature: {str(e)}")
            return {'success': False, 'message': f"Failed to update: {str(e)}"}

    def update_assistant_top_p(self, new_top_p):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}
        try:
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not assistant_id:
                logger.error("No assistant_id found in client keys")
                return {'success': False, 'message': 'No assistant_id found in client keys.'}
            self.client.beta.assistants.update(
                assistant_id=assistant_id,
                top_p=new_top_p
            )
            logger.info("Updated assistant top_p successfully.")
            return {
                'success': True,
                'message': 'Assistant top_p updated successfully.'
            }
        except Exception as e:
            logger.error(f"Failed to update assistant top_p: {str(e)}")
            return {'success': False, 'message': f"Failed to update: {str(e)}"}

    def create_thread(self):
        try:
            if not self.client:
                logger.error("OpenAI client is not initialized.")
                raise PermanentError("OpenAI client is not initialized.")
            vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            if not vs_id or not assistant_id:
                logger.error("No vector store ID or assistant_id found in client keys")
                raise PermanentError("No vector store ID or assistant_id found in client keys")
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            # Always update tools if needed
            tools, tool_resources = self._build_tools_and_resources()
            needs_update = False
            if hasattr(assistant, 'tools'):
                # Check if all required tools are present
                current_tool_types = set(getattr(tool, 'type', None) for tool in assistant.tools)
                required_tool_types = set(t["type"] for t in tools) if tools else set()
                if current_tool_types != required_tool_types:
                    needs_update = True
            else:
                needs_update = True
            if needs_update:
                logger.info(f"Updating assistant to connect with vector store {vs_id} and add function tools if needed")
                self.client.beta.assistants.update(
                    assistant_id=assistant_id,
                    tools=tools,
                    tool_resources=tool_resources
                )
                logger.info(f"Successfully updated assistant tools for {assistant_id}")
            thread = self.client.beta.threads.create()
            logger.info(f"Created new thread with ID: {thread.id}")
            return thread.id
        except Exception as e:
            logger.error(f"Error creating thread: {str(e)}", exc_info=True)
            raise PermanentError(f"Failed to create thread: {str(e)}")

    def send_message_to_thread(self, thread_id, message_content):
        try:
            if not self.client:
                logger.error("OpenAI client is not initialized.")
                raise PermanentError("OpenAI client is not initialized.")
            assistant_id = self.client_obj.get('keys', {}).get('assistant_id')
            vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
            if not assistant_id or not vs_id:
                logger.error("No assistant_id or vector_store_id found in client keys")
                raise PermanentError("No assistant_id or vector_store_id found in client keys")
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_content
            )
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )
            while True:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                if run_status.status == "completed":
                    break
                elif run_status.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"Run failed with status: {run_status.status}")
                    raise PermanentError(f"Assistant run failed: {run_status.status}")
                time.sleep(0.5)
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id,
                order="desc",
                limit=1
            )
            if not messages.data:
                logger.error("No messages returned from assistant")
                return "No response received from assistant"
            assistant_response = messages.data[0].content[0].text.value
            assistant_response = clean_sources(assistant_response)
            return assistant_response
        except Exception as e:
            logger.error(f"Error sending message to thread: {str(e)}", exc_info=True)
            raise PermanentError(f"Failed to get response: {str(e)}")

    def handle_tool_calls(self, thread_id, run):
        """
        Handles OpenAI assistant tool/function calls for create_order and check_order.
        Returns a string response if a tool call was handled, otherwise None.
        """
        try:
            # Get messages for the thread, look for tool_calls in the latest message
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id, order="desc", limit=1
            )
            if not messages.data:
                return None
            latest_message = messages.data[0]
            # Check for tool_calls in the message content
            for c in getattr(latest_message, 'content', []):
                if getattr(c, 'type', None) == "tool_calls" and hasattr(c, 'tool_calls'):
                    for tool_call in c.tool_calls:
                        function_name = getattr(tool_call, 'function_name', None)
                        arguments = getattr(tool_call, 'arguments', None)
                        if function_name == "create_order":
                            return self._handle_create_order(arguments)
                        elif function_name == "check_order":
                            return self._handle_check_order(arguments)
            return None
        except Exception as e:
            logger.error(f"Error handling tool calls: {str(e)}")
            return None

    def _handle_create_order(self, arguments):
        """
        Handles the create_order function call from the assistant.
        """
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            # Add now date/time
            now = datetime.now(timezone.utc)
            orderbook_repo = OrderbookRepository()
            order = orderbook_repo.create_order(
                tx_id=args["tx_id"],
                status="created",
                first_name=args["first_name"],
                last_name=args["last_name"],
                address=args["address"],
                phone=args["phone"],
                product=args["product"],
                price=args["price"],
                date=now,
                count=args["count"],
                client_username=self.client_username
            )
            if order:
                return f"Order created successfully. Reference: {order.get('tx_id')}"
            else:
                return "Failed to create order."
        except Exception as e:
            logger.error(f"Error in _handle_create_order: {str(e)}")
            return "Error creating order."

    def _handle_check_order(self, arguments):
        """
        Handles the check_order function call from the assistant.
        """
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            orderbook_repo = OrderbookRepository()
            order = orderbook_repo.get_order_by_tx_id(args["tx_id"], self.client_username)
            if order:
                # Return order status and summary
                return f"Order status: {order.get('status')}, Product: {order.get('product')}, Price: {order.get('price')}, Count: {order.get('count')}"
            else:
                return "Order not found."
        except Exception as e:
            logger.error(f"Error in _handle_check_order: {str(e)}")
            return "Error checking order."

def wait_for_active_run_completion(self, thread_id):
    try:
        while True:
            runs = self.client.beta.threads.runs.list(thread_id=thread_id)
            active_runs = [run for run in runs.data if run.status in ["queued", "in_progress"]]
            if not active_runs:
                break
            logger.info(f"Waiting for {len(active_runs)} active runs to complete...")
            time.sleep(5)
    except openai.APIError as e:
        logger.error(f"Failed to check active runs: {e.message}")
        raise RetryableError("Failed to check active runs")