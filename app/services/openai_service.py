from ..utils.exceptions import  PermanentError, RetryableError
from ..models.product import Product
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
    def __init__(self):
        try:
            self.client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
            if not self.client:
                raise ValueError("OpenAI client failed to initialize")
        except Exception as e:
            logger.critical(f"Failed to initialize OpenAI client: {str(e)}")
            self.client = None

    def delete_all_vector_stores(self):
        has_more = True
        while has_more:
            vs_list = self.client.vector_stores.list()
            has_more = vs_list.has_more

            for vs in vs_list.data:
                try:
                    self.client.vector_stores.delete(vs.id)
                    AppSettings.delete_by_key(vs.id)
                    logger.info(f"Deleted vector store: {vs.id}")
                except Exception as e:
                    logger.info(f"Error deleting vector store {vs.id}: {e}")

    def delete_all_files(self):
        file_list = self.client.files.list()
        products_with_files = [p for p in Product.get_all() if p.get('file_id')]
        Product.update_many({"file_id": {"$in": products_with_files}}, {"$unset": {"file_id": "", "batch_number": ""}})
        for file in file_list.data:
            try:
                self.client.files.delete(file.id)
                logger.info(f"Deleted file: {file.id}")
            except Exception as e:
                logger.info(f"Error deleting file {file.id}: {e}")

    def upload_file(self):
        products_without_files = [p for p in Product.get_all() if not p.get('file_id')]

        for p in products_without_files:
            content = json.dumps({
                    'عنوان محصول': p['title'],
                    'قیمت محصول': p['price'],
                    'توضیحات محصول': p['description'],
                    'توضیحات تکمیلی محصول': p['additional_info'],
                    'دسته‌بندی محصول': p['category'],
                    'تگ': p['tags'],
                    'توضیح مختصر': p['excerpt'],
                    'لینک خرید محصول': p['link']
                }, ensure_ascii=False)

            max_retries = 5
            retry_count = 0
            file_id = None

            while retry_count < max_retries and file_id is None:
                try:
                    file_response = self.client.files.create(
                        file=(f"{p['title']}.json", content, "application/json"),
                        purpose="assistants"
                    )
                    file_id = file_response.id
                    logger.info(f"File {file_id} created for product: {p['title']}")

                    while file_response.status != "processed":
                        time.sleep(1)
                        file_response = self.client.files.retrieve(file_id)

                        if file_response.status == "error":
                            self.client.files.delete(file_id)
                            raise Exception(f"File creation for product {p['title']}  failed: {file_response.error}")

                except Exception as e:
                    retry_count += 1
                    logger.info(f"Error creating file for product {p['title']} (attempt {retry_count}/{max_retries}): {str(e)}")


            if file_response.status == "processed":
                Product.update(p['title'], {"file_id": file_id})
                logger.info(f"File {file_id} for product {p['title']} stored for product: {p['title']}")

            elif file_response.status == "error":
                logger.error(f"File creation for product {p['title']}  failed: {file_response.error}")
                self.client.files.delete(file_id)
                return False

        return True



    def create_vector_store(self):
        while True:
            try:
                batch_size = 50
                products = Product.get_all()
                total_products = len(products)
                total_batches = total_products // batch_size + 1
                vector_store_id = None
                file_ids = [p['file_id'] for p in products]

                for batch_number in range(total_batches):
                    start = batch_number * batch_size
                    end = start + batch_size
                    batch = file_ids[start:end]

                    if not vector_store_id:
                        vector_store = self.client.vector_stores.create( name="Product Catalog",
                                                                         file_ids=batch,
                                                                         chunking_strategy={"type": "static",
                                                                                             "static": { "max_chunk_size_tokens": 100, "chunk_overlap_tokens": 30}})
                        vector_store_id = vector_store.id
                        logger.info(f"Vector store {vector_store_id} created for batch {batch_number + 1}/{total_batches}")
                        time.sleep(5)
                    elif vector_store_id:
                        vector_store = self.client.vector_stores.file_batches.create_and_poll(vector_store_id=vector_store_id,
                                                                                              file_ids=batch,
                                                                                              chunking_strategy={"type": "static",
                                                                                             "static": { "max_chunk_size_tokens": 100, "chunk_overlap_tokens": 30}}
                                                                                             )
                        logger.info(f"Added batch {batch_number + 1}/{total_batches} to vector store {vector_store_id}")
                        time.sleep(5)

                vector_store = self.client.vector_stores.retrieve(vector_store_id)
                while vector_store.file_counts.completed != total_products:
                    if vector_store.file_counts.failed > 0 or vector_store.file_counts.cancelled > 0:
                        self.client.vector_stores.delete(vector_store_id)
                        logger.error(f"Vector store creation failed: {vector_store.file_counts} files failed and {vector_store.file_counts.cancelled} files cancelled")
                        raise Exception(f"Vector store creation failed: {vector_store.file_counts}")
                    else:
                        time.sleep(5)
                        vector_store = self.client.vector_stores.retrieve(vector_store_id)

                if vector_store.file_counts.completed == total_products:
                    AppSettings.update('vs_id', vector_store_id)
                    logger.info(f"Vector store {vector_store_id} created for all products")
                    return vector_store_id
                else:
                    logger.error(f"Vector store creation failed: {vector_store.file_counts.failed} files failed and {vector_store.file_counts.cancelled} files cancelled")
            except Exception as e:
                logger.error(f"Error creating vector store: {str(e)}")
                continue

    def rebuild_files_and_vector_store(self):
        files = None
        vector_store_id = None
        Product.update_many({}, {"$unset": {"file_id": 1}})

        while not files:
            self.delete_all_files()
            files = self.upload_file()

        while not vector_store_id:
            logger.error("Error creating vector store")
            self.delete_all_vector_stores()
            vector_store_id = self.create_vector_store()

        if files and vector_store_id:
            return True
        else:
            return False

# =================================================================================================

    def translate_titles(self):
        # Get products without translations
        products = [p for p in Product.get_all() if not p.get('translated_title')]
        if not products:
            logger.info("No products need translation.")
            return True

        thread = self.client.beta.threads.create()
        for product in products:
            original_title = product['title']
            logger.info(f"Translating title for product: {original_title}")
            try:
                # Send the single product title to be translated
                self.client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=original_title
                )
                # Start the translation run
                run = self.client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=Config.OPENAI_TRANSLATOR_ID
                )
                # Wait for completion with a timeout of 60 seconds
                start_time = time.time()
                while run.status != "completed":
                    if time.time() - start_time > 60:
                        logger.error(f"Translation timeout for product: {original_title}")
                        raise TimeoutError("Translation run timed out")
                    time.sleep(0.1)
                    run = self.client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                # Retrieve the translation response
                messages = self.client.beta.threads.messages.list(thread_id=thread.id)
                if not messages.data:
                    logger.error(f"No translation response for product: {original_title}")
                    raise ValueError("No translation response received")
                translated_title = messages.data[0].content[0].text.value.strip()
                if not translated_title:
                    logger.error(f"Empty translation for product: {original_title}")
                    raise ValueError("Empty translation received")
                # Update product with translated title
                Product.update(original_title, {"translated_title": translated_title})
                logger.info(f"Translated title stored for product {original_title}: {translated_title}")
            except Exception as e:
                logger.error(f"Error translating product {original_title}: {str(e)}")
                return False

        logger.info("All titles have been translated!")
        return True

# =================================================================================================

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

            # Get vector store ID from settings
            vs_setting = AppSettings.get_by_key('vs_id')
            if not vs_setting:
                raise ValueError("No valid vector store ID found in AppSettings.")

            vector_store_id = vs_setting['value']

            thread = self.client.beta.threads.create(
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
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

    def process_messages(self, thread_id, message_texts, user=None):
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

    def create_thread(self):
        try:
            if not self.client:
                logger.error("OpenAI client is not initialized.")
                raise PermanentError("OpenAI client is not initialized.")

            # Check that a vector store ID exists in the database
            with get_db() as db:
                vs_setting = AppSettings.get_by_key('vs_id')
                if not vs_setting:
                    logger.error("No vector store ID found in database")
                    raise PermanentError("No vector store is configured. Please connect to a vector store first.")

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
                    if vs_setting['value'] in assistant.tool_resources.file_search.vector_store_ids:
                        has_vector_store = True

                # If the assistant doesn't have file_search tool or vector store, update it
                if not has_file_search or not has_vector_store:
                    logger.info(f"Updating assistant to connect with vector store {vs_setting['value']}")
                    self.client.beta.assistants.update(
                        assistant_id=Config.OPENAI_ASSISTANT_ID,
                        tools=[{"type": "file_search"}],
                        tool_resources={
                            "file_search": {
                                "vector_store_ids": [vs_setting['value']]
                            }
                        }
                    )
                    logger.info(f"Successfully connected assistant to vector store {vs_setting['value']}")

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