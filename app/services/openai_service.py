from ..utils.exceptions import  PermanentError, RetryableError
from contextlib import contextmanager
from ..models.product import Product
from ..models.appsettings import AppSettings
from ..models.base import SessionLocal
from ..config import Config
import openai
import time
import re
import logging
import json

logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        if db.in_transaction():
            db.commit()
    except Exception:
        if db.in_transaction():
            db.rollback()
        raise
    finally:
        db.close()
        db.expunge_all()

def clean_sources(response_text):

    metadata_patterns = [
        r'\[\d+:\d+:source\]',  # Matches [123:456:source]
        r'【\d+:\d+†source】',   # Matches 【14:4†source】
        r'\[\d+:\d+\]',         # Matches [123:456]
        r'【\d+:\d+】',          # Matches 【14:4】
        r'\(\d+:\d+\)',         # Matches (123:456)
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


    def update_or_create_vs(self):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return False

        with get_db() as db:
            try:
                # Step 1: Delete previous vector store and files if they exist
                logger.info("Checking for existing vector stores and files...")

                # Get existing vector store ID
                existing_vs_id = db.query(AppSettings.value).filter_by(key='vs_id').scalar()
                if existing_vs_id:
                    try:
                        # First verify the vector store exists on OpenAI
                        try:
                            self.client.beta.vector_stores.retrieve(existing_vs_id)
                            # If no exception, delete it
                            self.client.beta.vector_stores.delete(existing_vs_id)
                            logger.info(f"Deleted previous vector store {existing_vs_id} from OpenAI")
                        except Exception as vs_e:
                            logger.warning(f"Vector store {existing_vs_id} not found on OpenAI: {str(vs_e)}")

                        # Always delete from database
                        vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
                        if vs_setting:
                            db.delete(vs_setting)
                            logger.info(f"Deleted vector store ID {existing_vs_id} from database")
                    except Exception as e:
                        logger.warning(f"Failed to delete vector store {existing_vs_id}: {str(e)}")

                # Get existing file IDs
                existing_file_settings = db.query(AppSettings).filter(
                    AppSettings.key.like('file_id_%')
                ).all()

                for file_setting in existing_file_settings:
                    file_id = file_setting.value
                    try:
                        # First verify the file exists on OpenAI
                        try:
                            self.client.files.retrieve(file_id)
                            # If no exception, delete it
                            self.client.files.delete(file_id)
                            logger.info(f"Deleted previous file {file_id} from OpenAI")
                        except Exception as file_e:
                            logger.warning(f"File {file_id} not found on OpenAI: {str(file_e)}")

                        # Always delete from database
                        db.delete(file_setting)
                        logger.info(f"Deleted file ID {file_id} from database")
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file_id}: {str(e)}")

                # Commit deletions before proceeding
                db.commit()

                # Step 2: Get all products and create a single file
                logger.info("Retrieving products from database...")
                products = db.query(Product).all()

                # Create a single JSON file for all products
                logger.info(f"Creating a single file for {len(products)} products...")
                file_content = json.dumps([{
                    'title': product.title,
                    'price': product.price,
                    'description': product.description,
                    'additional_info': product.additional_info,
                    'category': product.category,
                    'tags': product.tags,
                    'excerpt': product.excerpt,
                    'sku': product.sku,
                    'stock_status': product.stock_status,
                    'product_link': product.link
                } for product in products], ensure_ascii=False)
                file_name = "all_products.json"

                # Upload file to OpenAI
                file_response = self.client.files.create(
                    file=(file_name, file_content, "application/json"),
                    purpose="assistants"
                )

                file_id = file_response.id
                logger.info(f"Created file {file_id} for all products")

                # Wait for file processing
                processing_timeout = 60  # 60 seconds timeout
                start_time = time.time()
                while True:
                    if time.time() - start_time > processing_timeout:
                        raise TimeoutError("File processing timed out for all products")

                    file_status = self.client.files.retrieve(file_id).status
                    if file_status == "processed":
                        logger.info(f"File {file_id} for all products is processed")
                        break
                    elif file_status == "error":
                        raise Exception("File processing failed for all products")

                    logger.debug(f"Waiting for file {file_id} to process... Status: {file_status}")
                    time.sleep(3)

                # Save file ID in the database
                db_key = "file_id_all_products"
                setting = db.query(AppSettings).filter_by(key=db_key).first()
                if setting:
                    setting.value = file_id
                else:
                    db.add(AppSettings(key=db_key, value=file_id))

                # Step 3: Create a vector store with the single file
                logger.info("Creating vector store with the single file...")
                vector_store = self.client.beta.vector_stores.create(
                    name="All Products",
                    file_ids=[file_id]
                )

                # Wait for vector store processing
                vs_processing_timeout = 120  # 120 seconds timeout
                start_time = time.time()
                while True:
                    if time.time() - start_time > vs_processing_timeout:
                        raise TimeoutError("Vector store creation timed out")

                    vs_status = self.client.beta.vector_stores.retrieve(vector_store.id).status
                    if vs_status == "completed":
                        logger.info(f"Vector store {vector_store.id} is completed")
                        break
                    elif vs_status in ["failed", "cancelled"]:
                        raise Exception(f"Vector store creation failed with status: {vs_status}")

                    logger.debug(f"Waiting for vector store to complete... Status: {vs_status}")
                    time.sleep(5)

                # Save vector store ID
                vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
                if vs_setting:
                    vs_setting.value = vector_store.id
                else:
                    db.add(AppSettings(key='vs_id', value=vector_store.id))

                db.commit()
                logger.info(f"Successfully created vector store {vector_store.id} with the single file")
                return True

            except Exception as e:
                logger.error(f"Error updating vector store: {str(e)}", exc_info=True)
                db.rollback()
                return False

# ============================

    def translate_titles(self):
        with get_db() as db:
            products = db.query(Product).filter(Product.translated_title.is_(None)).all()
            thread = self.client.beta.threads.create()

            for product in products:
                try:
                    message = self.client.beta.threads.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=f'{product.title}'
                    )
                    run = self.client.beta.threads.runs.create(thread_id=thread.id, assistant_id=Config.OPENAI_TRANSLATOR_ID)

                    while run.status != "completed":
                        time.sleep(0.2)
                        run = self.client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

                    messages = self.client.beta.threads.messages.list(thread_id=thread.id)
                    translated_title = messages.data[0].content[0].text.value.strip()

                    product.translated_title = translated_title
                    db.add(product)
                    db.commit()
                    logger.info(f"Translated title Stored for product {product.pID}: {translated_title}")
                except Exception as e:
                    logger.error(f"Error translating title for product {product.pID}: {str(e)}")
                    return False


        logger.info("All titles have been translated!")
        return True

# ============================================

    def ensure_thread(self, user):
        try:
            if user.assistant_thread_id:
                try:

                    thread = self.client.beta.threads.retrieve(user.assistant_thread_id)
                    logger.debug(f"Thread {thread.id} exists")
                    return thread.id
                except openai.APIError:
                    logger.error("Existing thread invalid, creating new one")

            with get_db() as db:
                vs_setting = db.query(AppSettings.value).filter_by(key='vs_id').first()
                if not vs_setting or not vs_setting.value:
                    raise ValueError("No valid vector store ID found in AppSettings.")

                vector_store_id = vs_setting.value

            thread = self.client.beta.threads.create(
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
            )
            logger.debug(f"Created thread {thread.id}")

            user.assistant_thread_id = thread.id
            with get_db() as db:
                db.merge(user)
                db.commit()

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
                if time.time() - start > 45:
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
        """
        Retrieve the current instructions for the assistant.

        Returns:
            str: The current instructions, or None if there was an error.
        """
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
        """
        Update the instructions for the assistant.

        Args:
            new_instructions (str): The new instructions for the assistant.

        Returns:
            dict: Dictionary containing success status and message.
        """
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}

        try:
            # Get the vector store ID if it exists
            vs_id = None
            with get_db() as db:
                vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
                if vs_setting:
                    vs_id = vs_setting.value

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

    def connect_assistant_to_vs(self):
        """
        Create a new vector store with all products and connect the assistant to it.

        This method:
        1. Removes ALL existing files and vector stores from OpenAI
        2. Creates a new file with all products
        3. Creates a new vector store with this file
        4. Connects the assistant to the new vector store

        Returns:
            dict: Dictionary containing success status and message.
        """
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {'success': False, 'message': 'OpenAI client is not initialized.'}

        try:
            # STEP 1: Delete ALL previous vector stores and files
            logger.info("Deleting ALL existing vector stores and files from OpenAI...")

            # List all vector stores from OpenAI
            try:
                openai_vector_stores = self.client.beta.vector_stores.list()
                logger.info(f"Found {len(openai_vector_stores.data)} vector stores in OpenAI account")

                # Delete ALL vector stores
                for vs in openai_vector_stores.data:
                    try:
                        self.client.beta.vector_stores.delete(vs.id)
                        logger.info(f"Deleted vector store {vs.id} from OpenAI")
                    except Exception as e:
                        logger.warning(f"Failed to delete vector store {vs.id}: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to list OpenAI vector stores: {str(e)}")

            # List all files with purpose "assistants" from OpenAI
            try:
                openai_files = self.client.files.list()
                logger.info(f"Found {len(openai_files.data)} files in OpenAI account")

                # Delete ALL files with purpose "assistants"
                for file in openai_files.data:
                    if file.purpose == "assistants":
                        try:
                            self.client.files.delete(file.id)
                            logger.info(f"Deleted file {file.id} from OpenAI")
                        except Exception as e:
                            logger.warning(f"Failed to delete file {file.id}: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to list OpenAI files: {str(e)}")

            # Clean up database entries
            with get_db() as db:
                # Delete all vector store entries
                vs_settings = db.query(AppSettings).filter_by(key='vs_id').all()
                for vs_setting in vs_settings:
                    db.delete(vs_setting)
                    logger.info(f"Deleted vector store ID {vs_setting.value} from database")

                # Delete all file entries
                file_settings = db.query(AppSettings).filter(
                    AppSettings.key.like('file_id_%')
                ).all()
                for file_setting in file_settings:
                    db.delete(file_setting)
                    logger.info(f"Deleted file ID {file_setting.value} from database")

                # Commit all deletions
                db.commit()

            # Wait a bit to ensure deletions are processed
            time.sleep(5)

            # STEP 2: Get all products and create a single file
            with get_db() as db:
                logger.info("Retrieving products from database...")
                products = db.query(Product).all()

                # Create a single JSON file for all products
                logger.info(f"Creating a single file for {len(products)} products...")
                file_content = json.dumps([{
                    'title': product.title,
                    'price': product.price,
                    'description': product.description,
                    'additional_info': product.additional_info,
                    'category': product.category,
                    'tags': product.tags,
                    'excerpt': product.excerpt,
                    'sku': product.sku,
                    'stock_status': product.stock_status,
                    'product_link': product.link
                } for product in products], ensure_ascii=False)
                file_name = "all_products.json"

                # Upload file to OpenAI
                file_response = self.client.files.create(
                    file=(file_name, file_content, "application/json"),
                    purpose="assistants"
                )

                file_id = file_response.id
                logger.info(f"Created file {file_id} for all products")

                # Wait for file processing
                processing_timeout = 60  # 60 seconds timeout
                start_time = time.time()
                while True:
                    if time.time() - start_time > processing_timeout:
                        raise TimeoutError("File processing timed out for all products")

                    file_status = self.client.files.retrieve(file_id).status
                    if file_status == "processed":
                        logger.info(f"File {file_id} for all products is processed")
                        break
                    elif file_status == "error":
                        raise Exception("File processing failed for all products")

                    logger.debug(f"Waiting for file {file_id} to process... Status: {file_status}")
                    time.sleep(3)

                # Save file ID in the database
                db_key = "file_id_all_products"
                setting = db.query(AppSettings).filter_by(key=db_key).first()
                if setting:
                    setting.value = file_id
                else:
                    db.add(AppSettings(key=db_key, value=file_id))

                # STEP 3: Create a vector store with the single file
                logger.info("Creating vector store with the single file...")
                vector_store = self.client.beta.vector_stores.create(
                    name="All Products",
                    file_ids=[file_id]
                )

                # Wait for vector store processing
                vs_processing_timeout = 120  # 120 seconds timeout
                start_time = time.time()
                while True:
                    if time.time() - start_time > vs_processing_timeout:
                        raise TimeoutError("Vector store creation timed out")

                    vs_status = self.client.beta.vector_stores.retrieve(vector_store.id).status
                    if vs_status == "completed":
                        logger.info(f"Vector store {vector_store.id} is completed")
                        break
                    elif vs_status in ["failed", "cancelled"]:
                        raise Exception(f"Vector store creation failed with status: {vs_status}")

                    logger.debug(f"Waiting for vector store to complete... Status: {vs_status}")
                    time.sleep(5)

                # Save vector store ID
                vs_id = vector_store.id
                vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
                if vs_setting:
                    vs_setting.value = vs_id
                else:
                    db.add(AppSettings(key='vs_id', value=vs_id))

                db.commit()
                logger.info(f"Successfully created vector store {vs_id} with the single file")

                # STEP 4: Connect the assistant to the vector store
                # Update the assistant with the file_search tool and vector store
                self.client.beta.assistants.update(
                    assistant_id=Config.OPENAI_ASSISTANT_ID,
                    tools=[{"type": "file_search"}],
                    tool_resources={
                        "file_search": {
                            "vector_store_ids": [vs_id]
                        }
                    }
                )

                logger.info(f"Connected assistant to vector store {vs_id} successfully.")
                return {
                    'success': True,
                    'message': f'Created vector store and connected assistant successfully.',
                    'vector_store_id': vs_id,
                    'file_id': file_id,
                    'product_count': len(products)
                }

        except Exception as e:
            logger.error(f"Failed to create vector store and connect assistant: {str(e)}", exc_info=True)
            return {'success': False, 'message': f"Failed to process: {str(e)}"}

    def create_thread(self):
        """Create a new thread for testing the assistant"""
        try:
            if not self.client:
                logger.error("OpenAI client is not initialized.")
                raise PermanentError("OpenAI client is not initialized.")
                
            # Check that a vector store ID exists in the database
            with get_db() as db:
                vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
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
                    if vs_setting.value in assistant.tool_resources.file_search.vector_store_ids:
                        has_vector_store = True
                
                # If the assistant doesn't have file_search tool or vector store, update it
                if not has_file_search or not has_vector_store:
                    logger.info(f"Updating assistant to connect with vector store {vs_setting.value}")
                    self.client.beta.assistants.update(
                        assistant_id=Config.OPENAI_ASSISTANT_ID,
                        tools=[{"type": "file_search"}],
                        tool_resources={
                            "file_search": {
                                "vector_store_ids": [vs_setting.value]
                            }
                        }
                    )
                    logger.info(f"Successfully connected assistant to vector store {vs_setting.value}")

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
                vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
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