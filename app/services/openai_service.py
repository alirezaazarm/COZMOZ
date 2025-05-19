from ..utils.exceptions import  PermanentError, RetryableError
from ..models.product import Product
from ..models.additional_info import Additionalinfo
from ..models.appsettings import AppSettings
from ..models.database import db
from ..config import Config
from ..utils.helpers import get_db
import openai
import time
import re
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VS_ID = None

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
    
    def __init__(self):
        try:
            self.client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
            if not self.client:
                raise ValueError("OpenAI client failed to initialize")
        except Exception as e:
            logger.critical(f"Failed to initialize OpenAI client: {str(e)}")
            self.client = None


    @staticmethod
    def set_vs_id(settings):
        """Set VS_ID from update route"""
        global VS_ID

        if settings.get('vs_id'):
            VS_ID = settings.get('vs_id')
            logger.info(f"openai_service - VS_ID set to {VS_ID}")
            return True
        else:
            logger.info(f"appsetting to main doesnt have vs_id!")
            return False
    
    # ------------------------------------------------------------------
    # Files and Vector Store
    # ------------------------------------------------------------------
    
    def delete_single_file(self, file_id) -> bool:
        try:
            resp = self.client.files.delete(file_id)
            if resp.deleted:
                logger.info(f"File with the ID {file_id} has deleted successfully")
                return True
            else:
                logger.error(f"Failed to delete file '{file_id}': {resp.error}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file '{file_id}': {e}")
            return False

    def clear_vs(self) -> bool:
        setting = AppSettings.get_by_key('vs_id')
        if not setting:
            logger.info("No vector store setting found in database")
            return True
        # Extract the raw ID string
        raw_value = setting.get('value')
        if isinstance(raw_value, dict):
            vs_id = raw_value.get('value')
        else:
            vs_id = raw_value
        if not vs_id or not isinstance(vs_id, str):
            logger.error(f"Invalid vs_id in setting: {raw_value}")
            return False
        try:
            response = self.client.vector_stores.delete(vs_id)
            if response.deleted:
                # Store raw string ID only
                AppSettings.update('vs_id', '')
                logger.info(f"Deleted vector store '{vs_id}' and unset vs_id in database")
                return True
            logger.error(f"Vector store deletion returned deleted=False for '{vs_id}'")
            return False
        except Exception as e:
            logger.error(f"Failed to delete vector store '{vs_id}': {e}")
            return False

    def clear_files(self, model_cls) -> bool:
        entries = model_cls.get_all()
        success = True
        for entry in entries:
            file_id = entry.get('file_id')
            if not file_id:
                continue
            try:
                resp = self.client.files.delete(file_id)
                if resp.deleted:
                    # Use correct identifier: title for Product, id for Additionalinfo
                    identifier = entry.get('title') if model_cls is Product else str(entry.get('_id'))
                    model_cls.update(identifier, {"file_id": None})
                    logger.info(f"Deleted file '{file_id}' and reset file_id for '{identifier}'")
                else:
                    logger.error(f"Failed to delete file '{file_id}': {resp.error}")
                    success = False
            except Exception as e:
                logger.error(f"Error deleting file '{file_id}': {e}")
                success = False
        return success

    def upload_files(self, model_cls, folder_name: str) -> bool:
        entries = model_cls.get_all()
        all_success = True
        for entry in entries:
            content_data = self._prepare_content(entry, folder_name)
            content = json.dumps(content_data, ensure_ascii=False)
            file_id = self._retry_upload(entry, content)
            if not file_id:
                all_success = False
                continue
            identifier = entry.get('title') if model_cls is Product else str(entry.get('_id'))
            updated = model_cls.update(identifier, {"file_id": file_id})
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
        else:
            return {
                'title': entry['title'],
                'category': folder_name,
                'content': entry['content']
            }

    def _retry_upload(self, entry, content: str) -> str | None:
        retry = 0
        file_id = None
        while retry < self.MAX_UPLOAD_RETRIES:
            try:
                resp = self.client.files.create(
                    file=(f"{entry['title']}.json", content, 'application/json'),
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
                raise Exception(f"File {file_id} processing error: {resp.error}")
            time.sleep(interval)
            waited += interval
        raise TimeoutError(f"Timeout waiting for file {file_id} to process")

    def create_vs(self) -> str | None:
        try:
            products = Product.get_all()
            additional = Additionalinfo.get_all()
            prod_ids = [p['file_id'] for p in products if p.get('file_id')]
            add_ids = [a['file_id'] for a in additional if a.get('file_id')]
            missing = [p['title'] for p in products if not p.get('file_id')]
            if missing:
                logger.error(f"Cannot create VS: missing product file_ids for {missing}")
                return None
            file_ids = prod_ids + add_ids

            self.clear_vs()
            vs = self.client.vector_stores.create(
                name='Vector Store',
                file_ids=file_ids[:self.BATCH_SIZE],
                chunking_strategy={
                    'type': 'static',
                    'static': {'max_chunk_size_tokens': 4000, 'chunk_overlap_tokens': 2000}
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
                        'static': {'max_chunk_size_tokens': 4000, 'chunk_overlap_tokens': 2000}
                    }
                )
                logger.info(f"Appended batch files {i}-{i + len(batch)} to vector store {vs_id}")

            final_vs = self.client.vector_stores.retrieve(vs_id)
            if final_vs.file_counts.completed == len(file_ids):
                AppSettings.update('vs_id', f"{vs_id}")
                logger.info(f"Stored vs_id '{vs_id}' in database")
                return vs_id
            logger.error(f"Vector store incomplete: {final_vs.file_counts}")
            return None
        except Exception as e:
            logger.error(f"Error in create_vs: {e}")
            return None

    def rebuild_all(self) -> bool:
        ok1 = self.clear_files(Product)
        ok2 = self.clear_files(Additionalinfo)
        ok3 = self.upload_files(Product, 'products')
        ok4 = self.upload_files(Additionalinfo, 'info')
        if not (ok1 and ok2 and ok3 and ok4):
            logger.warning("Some clear or upload steps failed")
        vs_id = self.create_vs()
        if not vs_id:
            logger.error("Failed to create/update vector store")
            return False
        return True
    # ------------------------------------------------------------------
    # Chat/Assistant config
    # ------------------------------------------------------------------

    def ensure_thread(self, user):
        try:
            # In MongoDB, user is a dictionary, not an ORM object
            thread_id = user.get('thread_id')
            if thread_id:
                try:
                    thread = self.client.beta.threads.retrieve(thread_id)
                    logger.debug(f"Thread {thread.id} exists")
                    return thread.id
                except openai.APIError:
                    logger.error("Existing thread invalid, creating new one")

            # Get vector store ID from global variable, or from AppSettings if not set
            global VS_ID
            if not VS_ID:
                setting = AppSettings.get_by_key('vs_id')
                if setting and setting.get('value'):
                    VS_ID = setting.get('value')
                    logger.info(f"Loaded VS_ID from AppSettings: {VS_ID}")
                else:
                    logger.error("No valid vector store ID found in AppSettings.")

            thread = self.client.beta.threads.create(
                tool_resources={"file_search": {"vector_store_ids": [VS_ID]}}
            )
            logger.debug(f"Created thread {thread.id}")

            # Update user with thread ID in MongoDB
            user_id = user.get('user_id')
            if not user_id:
                raise ValueError("User document is missing user_id field")

            # Update the user document in MongoDB
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
            # Join all messages into a single message with separators
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

            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=Config.OPENAI_ASSISTANT_ID
            )
            logger.info(f"Run created with ID: {run.id} for thread_id: {thread_id}")

            start = time.time()
            while run.status not in ["completed", "failed", "cancelled"]:
                if time.time() - start > 300:  # Increased from 45 to 300 seconds (5 minutes)
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

            text_content = next(
                (c.text.value for c in latest_message.content if c.type == "text"),
                None
            )
            if not text_content.strip():
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
            assistant = self.client.beta.assistants.retrieve(Config.OPENAI_ASSISTANT_ID)
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
            assistant = self.client.beta.assistants.retrieve(Config.OPENAI_ASSISTANT_ID)
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
            assistant = self.client.beta.assistants.retrieve(Config.OPENAI_ASSISTANT_ID)
            logger.info(f"Retrieved assistant top_p successfully.")
            return assistant.top_p
        except Exception as e:
            logger.error(f"Failed to retrieve assistant top_p: {str(e)}")
            return None

    def update_assistant_instructions(self, new_instructions):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}

        try:
            # Get the vector store ID if it exists
            vs_id = None
            with get_db() as db:
                vs_setting = AppSettings.get_by_key('vs_id')
                if vs_setting:
                    vs_id = vs_setting['value']

            # Create basic update params
            update_params = {
                "assistant_id": Config.OPENAI_ASSISTANT_ID,
                "instructions": new_instructions
            }

            # If we have a vector store ID, use it for file search
            if vs_id:
                update_params["tools"] = [{"type": "file_search"}]
                update_params["tool_resources"] = {
                    "file_search": {
                        "vector_store_ids": [vs_id]
                    }
                }

            # Update the assistant
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
            self.client.beta.assistants.update(
                assistant_id=Config.OPENAI_ASSISTANT_ID,
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
            self.client.beta.assistants.update(
                assistant_id=Config.OPENAI_ASSISTANT_ID,
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

            # Check that a VS_ID exists in memory, or load from AppSettings
            global VS_ID
            if not VS_ID:
                from ..models.appsettings import AppSettings
                setting = AppSettings.get_by_key('vs_id')
                if setting and setting.get('value'):
                    VS_ID = setting.get('value')
                    logger.info(f"Loaded VS_ID from AppSettings: {VS_ID}")
                else:
                    logger.error("No vector store ID found in memory or AppSettings")
                    raise PermanentError("No vector store ID found in memory or AppSettings")

            # Verify the assistant is connected to this vector store
            assistant = self.client.beta.assistants.retrieve(Config.OPENAI_ASSISTANT_ID)

            # If the assistant doesn't have tools or file_search tool resources, update it
            has_file_search = False
            has_vector_store = False

            # Check if assistant has file_search tool
            if hasattr(assistant, 'tools'):
                for tool in assistant.tools:
                    if tool.type == "file_search":
                        has_file_search = True
                        break

            # Check if assistant has the vector store connected
            if hasattr(assistant, 'tool_resources') and hasattr(assistant.tool_resources, 'file_search'):
                if VS_ID in assistant.tool_resources.file_search.vector_store_ids:
                    has_vector_store = True

            # If the assistant doesn't have file_search tool or vector store, update it
            if not has_file_search or not has_vector_store:
                logger.info(f"Updating assistant to connect with vector store {VS_ID}")
                self.client.beta.assistants.update(
                    assistant_id=Config.OPENAI_ASSISTANT_ID,
                    tools=[{"type": "file_search"}],
                    tool_resources={
                        "file_search": {
                            "vector_store_ids": [VS_ID]
                        }
                    }
                )
                logger.info(f"Successfully connected assistant to vector store {VS_ID}")

            # Create the thread
            thread = self.client.beta.threads.create()
            logger.info(f"Created new thread with ID: {thread.id}")
            return thread.id
        except Exception as e:
            logger.error(f"Error creating thread: {str(e)}", exc_info=True)
            raise PermanentError(f"Failed to create thread: {str(e)}")

    def send_message_to_thread(self, thread_id, message_content):
        """Send a message to a thread and get the assistant's response"""
        try:
            if not self.client:
                logger.error("OpenAI client is not initialized.")
                raise PermanentError("OpenAI client is not initialized.")

            # Get assistant ID from Config
            assistant_id = Config.OPENAI_ASSISTANT_ID

            # Verify the vector store exists in the database
            with get_db() as db:
                vs_setting = AppSettings.get_by_key('vs_id')
                if not vs_setting:
                    logger.error("No vector store ID found in database")
                    raise PermanentError("No vector store is configured. Please connect to a vector store first.")

            # Add message to thread
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_content
            )

            # Run the thread with the assistant
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            # Poll for run completion
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

            # Get messages
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id,
                order="desc",
                limit=1
            )

            if not messages.data:
                logger.error("No messages returned from assistant")
                return "No response received from assistant"

            # Return the assistant's response
            assistant_response = messages.data[0].content[0].text.value
            assistant_response = clean_sources(assistant_response)
            return assistant_response

        except Exception as e:
            logger.error(f"Error sending message to thread: {str(e)}", exc_info=True)
            raise PermanentError(f"Failed to get response: {str(e)}")