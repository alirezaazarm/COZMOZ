from ..utils.exceptions import  PermanentError, RetryableError
from ..models.product import Product
from ..models.appsettings import AppSettings
from ..models.database import db
from ..config import Config
from ..utils.helpers import get_db  # Import the proper context manager
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


    def update_or_create_vs(self):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return {"success": False, "message": "OpenAI client is not initialized.", "logs": ["Error: OpenAI client is not initialized."]}

        logs = []
        error_logs = []  # Only collect error and warning logs for UI
        try:
            # Step 1: Delete previous vector store and files if they exist
            logger.info("Checking for existing vector stores and files...")

            # Get existing vector store ID
            vs_setting = AppSettings.get_by_key('vs_id')
            existing_vs_id = vs_setting['value'] if vs_setting else None
            
            if existing_vs_id:
                try:
                    # First verify the vector store exists on OpenAI
                    try:
                        self.client.vector_stores.retrieve(existing_vs_id)
                        # If no exception, delete it
                        self.client.vector_stores.delete(existing_vs_id)
                        logger.info(f"Deleted previous vector store {existing_vs_id} from OpenAI")
                    except Exception as vs_e:
                        log_msg = f"Vector store {existing_vs_id} not found on OpenAI: {str(vs_e)}"
                        error_logs.append(log_msg)
                        logger.warning(log_msg)

                    # Delete from database
                    AppSettings.delete('vs_id')
                    logger.info(f"Deleted vector store ID {existing_vs_id} from database")
                except Exception as e:
                    log_msg = f"Failed to delete vector store {existing_vs_id}: {str(e)}"
                    error_logs.append(log_msg)
                    logger.warning(log_msg)

            # Delete existing file IDs from OpenAI and clear product file_id fields
            # Get all products with file_ids
            products_with_files = [p for p in Product.get_all() if p.get('file_id')]
            logger.info(f"Found {len(products_with_files)} products with existing file IDs")

            for product in products_with_files:
                file_id = product.get('file_id')
                if file_id:
                    try:
                        # First verify the file exists on OpenAI
                        try:
                            self.client.files.retrieve(file_id)
                            # If no exception, delete it
                            self.client.files.delete(file_id)
                            logger.info(f"Deleted previous file {file_id} for product '{product['title']}'")
                        except Exception as file_e:
                            log_msg = f"File {file_id} for product '{product['title']}' not found on OpenAI: {str(file_e)}"
                            error_logs.append(log_msg)
                            logger.warning(log_msg)

                        # Remove file_id from product record
                        Product.update(product['title'], {'file_id': None, 'batch_number': None})
                        logger.info(f"Cleared file ID for product '{product['title']}'")
                    except Exception as e:
                        log_msg = f"Failed to clean up file {file_id} for product '{product['title']}': {str(e)}"
                        error_logs.append(log_msg)
                        logger.warning(log_msg)

            # For backwards compatibility, also clean up any old file IDs in AppSettings
            file_settings = [s for s in AppSettings.get_all() if s['key'].startswith('file_id_')]
            for file_setting in file_settings:
                file_id = file_setting['value']
                try:
                    # Try to delete from OpenAI if it exists
                    try:
                        self.client.files.retrieve(file_id)
                        self.client.files.delete(file_id)
                        logger.info(f"Deleted legacy file {file_id} from OpenAI")
                    except Exception:
                        pass  # Already logged for product files above

                    # Delete from AppSettings
                    AppSettings.delete(file_setting['key'])
                    logger.info(f"Removed legacy file ID {file_id} from AppSettings")
                except Exception as e:
                    log_msg = f"Failed to clean up legacy file {file_id}: {str(e)}"
                    error_logs.append(log_msg)
                    logger.warning(log_msg)

            # Step 2: Get all products and create individual files
            logger.info("Retrieving products from database...")
            products = Product.get_all()

            file_ids = []
            processed_count = 0
            total_products = len(products)
            
            logger.info(f"Creating individual files for {total_products} products...")

            # Create individual files for each product
            for index, p in enumerate(products):
                # Create a sanitized filename from the product title
                product_title = p['title']
                sanitized_title = ''.join(c if c.isalnum() or c in [' ', '_', '-'] else '_' for c in product_title)
                sanitized_title = sanitized_title[:50]  # Limit length to avoid issues
                file_name = f"{sanitized_title}.json"
                
                logger.info(f"Processing product {index+1}/{total_products}: {sanitized_title}")

                # Create product JSON content
                file_content = json.dumps({
                    'title': p['title'],
                    'price': p['price'],
                    'description': p['description'],
                    'additional_info': p['additional_info'],
                    'category': p['category'],
                    'tags': p['tags'],
                    'excerpt': p['excerpt'],
                    'sku': p['sku'],
                    'stock_status': p['stock_status'],
                    'product_link': p['link']
                }, ensure_ascii=False)

                # Try to upload the file with retry logic
                max_retries = 3
                retry_count = 0
                file_id = None

                while retry_count < max_retries and file_id is None:
                    try:
                        file_response = self.client.files.create(
                            file=(file_name, file_content, "application/json"),
                            purpose="assistants"
                        )
                        file_id = file_response.id
                        logger.info(f"Created file {file_id} for product: {sanitized_title}")
                    except Exception as e:
                        retry_count += 1
                        log_msg = f"Error creating file for product {sanitized_title} (attempt {retry_count}/{max_retries}): {str(e)}"
                        if retry_count == max_retries:  # Only add to error logs on final attempt
                            error_logs.append(log_msg)
                        logger.error(log_msg)
                        time.sleep(1)  # Wait before retrying

                if file_id is None:
                    log_msg = f"Failed to create file for product {sanitized_title} after {max_retries} attempts. Skipping."
                    error_logs.append(log_msg)
                    logger.error(log_msg)
                    continue

                # Wait for file processing with timeout
                processing_timeout = 60  # 60 seconds timeout
                start_time = time.time()
                processed = False

                while not processed and time.time() - start_time < processing_timeout:
                    try:
                        file_status = self.client.files.retrieve(file_id).status
                        if file_status == "processed":
                            logger.info(f"File {file_id} for product {sanitized_title} is processed")
                            processed = True
                            break
                        elif file_status == "error":
                            log_msg = f"File processing failed for product {sanitized_title}"
                            error_logs.append(log_msg)
                            logger.error(log_msg)
                            
                            # Delete the failed file
                            try:
                                self.client.files.delete(file_id)
                                logger.info(f"Deleted failed file {file_id}")
                            except Exception as del_e:
                                log_msg = f"Failed to delete failed file {file_id}: {str(del_e)}"
                                error_logs.append(log_msg)
                                logger.warning(log_msg)
                                
                            file_id = None
                            break

                        logger.debug(f"Waiting for file {file_id} to process... Status: {file_status}")
                        time.sleep(3)
                    except Exception as e:
                        log_msg = f"Error checking file status: {str(e)}"
                        error_logs.append(log_msg)
                        logger.error(log_msg)
                        time.sleep(3)

                # Handle timeout case
                if not processed:
                    log_msg = f"File processing timed out for product {sanitized_title}"
                    error_logs.append(log_msg)
                    logger.error(log_msg)
                    
                    # Try to delete the file that timed out
                    try:
                        self.client.files.delete(file_id)
                        logger.info(f"Deleted timed out file {file_id}")
                    except Exception as del_e:
                        log_msg = f"Failed to delete timed out file {file_id}: {str(del_e)}"
                        error_logs.append(log_msg)
                        logger.warning(log_msg)
                        
                    file_id = None
                    continue

                if file_id:
                    # Save file ID directly in the product record
                    # We'll assign a batch number later
                    if Product.update(p['title'], {'file_id': file_id}):
                        logger.info(f"Updated product '{p['title']}' with file ID {file_id}")
                        file_ids.append(file_id)
                        processed_count += 1
                    else:
                        log_msg = f"Failed to update product '{p['title']}' with file ID {file_id}"
                        error_logs.append(log_msg)
                        logger.error(log_msg)
                        # Try to delete the file since we couldn't store its ID
                        try:
                            self.client.files.delete(file_id)
                            logger.info(f"Deleted file {file_id} due to product update failure")
                        except Exception as del_e:
                            log_msg = f"Failed to delete file {file_id} after product update failure: {str(del_e)}"
                            error_logs.append(log_msg)
                            logger.warning(log_msg)

                # Add a small delay between file creations to avoid rate limits
                time.sleep(0.5)

            if not file_ids:
                log_msg = "No files were successfully created. Cannot create vector store."
                error_logs.append(log_msg)
                logger.error(log_msg)
                return {"success": False, "message": "No files were successfully created", "logs": error_logs}

            # Step 3: Create a vector store with batches of files (max 100 per batch)
            logger.info(f"Creating vector store with {len(file_ids)} successful files (max 100 per batch)...")
            
            try:
                # Define the batch size
                batch_size = 100
                
                # Create the initial vector store with the first batch of files
                initial_batch = file_ids[:batch_size]
                
                vector_store = self.client.vector_stores.create(
                    name="Product Catalog",
                    file_ids=initial_batch
                )
                
                vector_store_id = vector_store.id
                logger.info(f"Created initial vector store {vector_store_id} with first batch of {len(initial_batch)} files")
                
                # Update batch number for the first batch of products
                products_with_files = [p for p in Product.get_all() if p.get('file_id') and p.get('file_id') in initial_batch]
                for product in products_with_files:
                    Product.update(product['title'], {'batch_number': 1})
                
                # Process any remaining files in batches
                remaining_files = file_ids[batch_size:]
                batch_number = 2
                
                for i in range(0, len(remaining_files), batch_size):
                    batch = remaining_files[i:i + batch_size]
                    if not batch:
                        continue
                        
                    logger.info(f"Adding batch {batch_number} with {len(batch)} files to vector store")
                    
                    try:
                        # Add this batch to the vector store
                        self.client.vector_stores.file_batches.create_and_poll(
                            vector_store_id=vector_store_id,
                            file_ids=batch
                        )
                        
                        logger.info(f"Successfully added batch {batch_number} to vector store")
                        
                        # Update batch number for these products
                        products_for_batch = [p for p in Product.get_all() if p.get('file_id') and p.get('file_id') in batch]
                        for product in products_for_batch:
                            Product.update(product['title'], {'batch_number': batch_number})
                            
                        batch_number += 1
                    except Exception as batch_e:
                        log_msg = f"Error adding batch {batch_number} to vector store: {str(batch_e)}"
                        error_logs.append(log_msg)
                        logger.error(log_msg)
                        # Continue with next batch rather than failing the whole process

                # Wait for vector store processing to complete
                vs_processing_timeout = 300  # 5 minutes timeout
                start_time = time.time()
                vs_processed = False
                
                while not vs_processed and time.time() - start_time < vs_processing_timeout:
                    vs_status = self.client.vector_stores.retrieve(vector_store_id).status
                    if vs_status == "completed":
                        logger.info(f"Vector store {vector_store_id} is completed")
                        vs_processed = True
                        break
                    elif vs_status in ["failed", "cancelled"]:
                        log_msg = f"Vector store creation failed with status: {vs_status}"
                        error_logs.append(log_msg)
                        logger.error(log_msg)
                        raise Exception(log_msg)

                    logger.debug(f"Waiting for vector store to complete... Status: {vs_status}")
                    time.sleep(10)  # Longer wait time for vector store processing
                
                if not vs_processed:
                    log_msg = "Vector store creation timed out"
                    error_logs.append(log_msg)
                    logger.error(log_msg)
                    return {"success": False, "message": "Vector store creation timed out", "logs": error_logs}

                # Save vector store ID in AppSettings (we still need this for reference)
                AppSettings.create_or_update('vs_id', vector_store_id)
                
                logger.info(f"Successfully created vector store {vector_store_id} with {processed_count} product files in {batch_number-1} batches")
                
                # Connect the assistant to the vector store
                try:
                    self.client.beta.assistants.update(
                        assistant_id=Config.OPENAI_ASSISTANT_ID,
                        tools=[{"type": "file_search"}],
                        tool_resources={
                            "file_search": {
                                "vector_store_ids": [vector_store_id]
                            }
                        }
                    )
                    logger.info(f"Connected assistant to vector store {vector_store_id}")
                except Exception as connect_e:
                    log_msg = f"Failed to connect assistant to vector store: {str(connect_e)}"
                    error_logs.append(log_msg)
                    logger.warning(log_msg)
                    # Continue as the vector store was still created successfully
                
                return {
                    "success": True, 
                    "message": f"Successfully created vector store with {processed_count} product files in {batch_number-1} batches", 
                    "logs": error_logs,  # Only return error logs to UI
                    "vector_store_id": vector_store_id,
                    "processed_count": processed_count,
                    "total_count": total_products,
                    "batch_count": batch_number-1
                }
            except Exception as e:
                log_msg = f"Error creating vector store: {str(e)}"
                error_logs.append(log_msg)
                logger.error(log_msg)
                return {"success": False, "message": f"Failed to create vector store: {str(e)}", "logs": error_logs}
        except Exception as e:
            log_msg = f"Error in update_or_create_vs process: {str(e)}"
            error_logs.append(log_msg)
            logger.error(log_msg, exc_info=True)
            return {"success": False, "message": f"Error updating vector store: {str(e)}", "logs": error_logs}

# ============================

    def translate_titles(self):
        # Get products without translations
        products = [p for p in Product.get_all() if not p.get('translated_title')]
        if not products:
            logger.info("No products need translation.")
            return True

        # Extract titles and join with commas
        titles = [product['title'] for product in products]
        titles_str = ','.join(titles)

        # Create a thread and send the list of titles
        thread = self.client.beta.threads.create()
        try:
            message = self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=titles_str
            )
            run = self.client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=Config.OPENAI_TRANSLATOR_ID
            )

            # Wait for the run to complete
            while run.status != "completed":
                time.sleep(1)
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )

            # Retrieve the assistant's response
            messages = self.client.beta.threads.messages.list(thread_id=thread.id)
            response = messages.data[0].content[0].text.value.strip()

            # Parse the response into a dictionary
            translated_dict = json.loads(response)

            # Update each product with the translated title
            for product in products:
                original_title = product['title']
                if original_title not in translated_dict:
                    logger.error(f"No translation found for product {original_title}")
                    return False
                translated_title = translated_dict[original_title]
                try:
                    Product.update(original_title, {"translated_title": translated_title})
                    logger.info(f"Translated title stored for product {original_title}: {translated_title}")
                except Exception as e:
                    logger.error(f"Error updating product {original_title}: {str(e)}")
                    return False

            logger.info("All titles have been translated!")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing translation response: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error during translation process: {str(e)}")
            return False

# ============================================

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