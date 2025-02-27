from ..utils.exceptions import  PermanentError, RetryableError
from ..utils.helpers import clean_openai_response
from contextlib import contextmanager
from ..models.product import Product
from ..models.base import SessionLocal
import openai
import time
from ..config import Config
import logging
import json

logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

class OpenAIService:
    def __init__(self):
        try:
            self.client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
            if not self.client:
                raise ValueError("OpenAI client failed to initialize")
        except Exception as e:
            logger.critical(f"Failed to initialize OpenAI client: {str(e)}")
            self.client = None

    def create_vs(self):
        if not self.client:
            logger.error("OpenAI client is not initialized.")
            return False

        with get_db() as db:
            products = db.query(Product).all()
            for product in products:
                try:
                    if not product.vector_store_ID or not product.file_ID:
                        file_content = json.dumps(product.__dict__)
                        file_response = self.client.files.create(
                            file=(f"{product.title}.json", file_content, "application/json"),
                            purpose="assistants"
                        )
                        file_ID = file_response.id
                        vector_store = self.client.beta.vector_stores.create(name=product.title)
                        self.client.beta.vector_stores.files.create(vector_store_ID=vector_store.id, file_id=file_ID)

                        product.vector_store_ID = vector_store.id
                        product.file_ID = file_ID
                        db.add(product)
                        db.commit()
                        logger.info(f"Created and Stored vector store and file for product {product.pID}: {product.title}")
                except Exception as e:
                    logger.error(f"Error processing product {product.pID}: {str(e)}")
                    return False
        return True

    def delete_vs(self):
        with get_db() as db:
            products = db.query(Product).all()
            for product in products:
                try:
                    if product.vector_store_ID:
                        self.client.beta.vector_stores.delete(product.vector_store_ID)
                        logger.debug(f"Deleted vector store with ID {product.vector_store_ID}")

                    if product.file_ID:
                        self.client.files.delete(product.file_ID)
                        logger.debug(f"Deleted file with ID {product.file_ID}")
                except Exception as e:
                    logger.error(f"Error deleting product {product.pID}: {str(e)}")
                db.query(Product).update({"vector_store_ID": None, "file_ID": None}, synchronize_session=False)
                db.commit()

        logger.info("All vector stores and files deleted successfully.")
        return True

    def add_vs(self):
        with get_db() as db:
            products = db.query(Product).filter((Product.vector_store_ID.is_(None)) | (Product.file_ID.is_(None))).all()
            for product in products:
                try:
                    file_content = json.dumps(product.__dict__)
                    file_response = self.client.files.create(
                        file=(f"{product.title}.json", file_content, "application/json"),
                        purpose="assistants"
                    )
                    file_id = file_response.id
                    vector_store = self.client.beta.vector_stores.create(name=product.title)
                    self.client.beta.vector_stores.files.create(vector_store_id=vector_store.id, file_id=file_id)

                    product.vector_store_ID = vector_store.id
                    product.file_ID = file_id
                    db.add(product)
                    db.commit()
                    logger.info(f"Added and Stored vector store and file for product {product.pID}: {product.title}")
                except Exception as e:
                    logger.error(f"Error adding vector store for product {product.pID}: {str(e)}")
                    return False

        return True

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

    def ensure_thread(self, user):
        try:
            if user.assistant_thread_id:
                try:

                    thread = self.client.beta.threads.retrieve(user.assistant_thread_id)
                    logger.debug(f"Thread {thread.id} exists")
                    return thread.id
                except openai.APIError:
                    logger.warning("Existing thread invalid, creating new one")

            with get_db() as db:
                products = db.query(Product.vector_store_ID).filter(Product.vector_store_ID.isnot(None)).all()
                vector_store_IDs = [p.vector_store_ID for p in products if p.vector_store_ID]

            if not vector_store_IDs:
                raise ValueError("No valid vector store IDs found in the database.")

            thread = self.client.beta.threads.create(
                tool_resources={"file_search": {"vector_store_ids": vector_store_IDs}}
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
        try:
            message_content = "\n".join(message_texts)
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_content
            )
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=Config.OPENAI_ASSISTANT_ID
            )
            start = time.time()
            while run.status not in ["completed", "failed", "cancelled"]:
                if time.time() - start > 45:
                    raise TimeoutError("OpenAI timeout")
                time.sleep(5)
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
            if run.status != "completed":
                raise openai.OpenAIError(f"Run failed: {run.last_error}")
            return clean_openai_response(self._get_assistant_response(thread_id))
        except openai.APIError as e:
            raise RetryableError(f"API Error: {e.message}") from e

    def _get_assistant_response(self, thread_id):
        try:
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id, order="desc", limit=1
            )
            if not messages.data:
                raise ValueError("No messages in thread")
            latest_message = messages.data[0]
            text_content = next(
                (c.text.value for c in latest_message.content if c.type == "text"),
                None
            )
            if not text_content.strip():
                raise ValueError("Empty response from assistant")
            return text_content
        except openai.APIError as e:
            raise RetryableError(f"OpenAI API Error: {e.message}")
        except Exception as e:
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