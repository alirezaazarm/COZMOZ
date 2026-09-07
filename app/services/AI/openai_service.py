"""Responses API integration; Assistants API was retired on 2026-08-26."""
from __future__ import annotations
import io, json, logging, re, time
from datetime import datetime, timezone
import openai
from ...config import Config
from ...models.additional_info import Additionalinfo
from ...models.client import Client
from ...models.database import db
from ...models.enums import ModuleType, Platform
from ...models.product import Product
from ...repositories.orderbook_repository import OrderbookRepository
from ...utils.exceptions import PermanentError, RetryableError
from ...utils.helpers import get_app_settings

logger = logging.getLogger(__name__)

def clean_sources(text: str) -> str:
    for pattern in (r'\[\d+:\d+:source\]', r'\[\d+:\d+\]', r'\(\d+:\d+\)'):
        text = re.sub(pattern, '', text)
    return text.strip()

class OpenAIService:
    MAX_UPLOAD_RETRIES, UPLOAD_RETRY_DELAY, BATCH_SIZE = 5, 2, 30
    DEFAULT_MODEL = Config.DEFAULT_OPENAI_MODEL
    openai_client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)

    def __init__(self, client_username=None, agent=None):
        if not client_username: raise ValueError('Must provide client_username')
        self.client_username = client_username
        self.client_obj = Client.get_by_username(client_username)
        if not self.client_obj: raise ValueError(f'Client not found: {client_username}')
        self.client = self.__class__.openai_client
        # Optional agent override: per-account model/instructions/vector_store
        self.agent = agent

    # Configuration is stored locally because Responses has no persistent Assistant object.
    def _refresh(self): self.client_obj = Client.get_by_username(self.client_username) or self.client_obj
    def _setting(self, name, default=None): return self.client_obj.get('ai', {}).get(name, default)
    def _save_settings(self, values):
        Client.update(self.client_username, {f'ai.{k}': v for k, v in values.items()}); self._refresh()
    def get_assistant_instructions(self): return self._setting('instructions', '')
    def get_assistant_temperature(self): return self._setting('temperature', 1.0)
    def get_assistant_top_p(self): return self._setting('top_p', 1.0)
    def get_model(self): return self._setting('model', self.DEFAULT_MODEL)
    def update_assistant_instructions(self, value):
        self._save_settings({'instructions': value or ''}); return {'success': True, 'message': 'Responses instructions saved.'}
    def update_assistant_temperature(self, value):
        if not 0 <= float(value) <= 2: return {'success': False, 'message': 'Temperature must be between 0 and 2.'}
        self._save_settings({'temperature': float(value)}); return {'success': True, 'message': 'Responses temperature saved.'}
    def update_assistant_top_p(self, value):
        if not 0 <= float(value) <= 1: return {'success': False, 'message': 'Top-p must be between 0 and 1.'}
        self._save_settings({'top_p': float(value)}); return {'success': True, 'message': 'Responses top-p saved.'}
    def update_model(self, value):
        if not isinstance(value, str) or not value.strip(): return {'success': False, 'message': 'A model name is required.'}
        self._save_settings({'model': value.strip()}); return {'success': True, 'message': 'Responses model saved.'}

    def delete_single_file(self, file_id):
        try: return bool(self.client.files.delete(file_id).deleted)
        except Exception as exc: logger.error('File deletion failed for %s: %s', file_id, exc); return False
    def clear_vs(self):
        vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
        if not vs_id: return True
        try:
            deleted = self.client.vector_stores.delete(vs_id).deleted
            if deleted: Client.update(self.client_username, {'keys.vector_store_id': None}); self._refresh()
            return bool(deleted)
        except Exception as exc: logger.error('Vector store deletion failed: %s', exc); return False
    def clear_files(self, model_cls):
        ok = True
        for entry in model_cls.get_all(client_username=self.client_username):
            if entry.get('file_id') and not self.delete_single_file(entry['file_id']): ok = False
            identifier = entry.get('title') if model_cls is Product else str(entry.get('_id'))
            try: model_cls.update(identifier, {'file_id': None}, client_username=self.client_username)
            except Exception as exc: logger.error('Could not clear %s: %s', identifier, exc); ok = False
        return ok
    @staticmethod
    def _prepare_content(entry, folder):
        if folder == 'products': return {key: entry.get(key) for key in ('title','price','description','additional_info','category','tags','excerpt','link')}
        return entry['content'] if entry.get('content_format') == 'json' else {'title': entry['title'], 'category': folder, 'content': entry['content']}
    def _retry_upload(self, entry, content):
        for attempt in range(self.MAX_UPLOAD_RETRIES):
            try:
                return self.client.files.create(file=(f"{entry['title']}.json", io.BytesIO(content.encode()), 'application/json'), purpose='user_data').id
            except Exception as exc: logger.warning('Upload attempt %d failed: %s', attempt + 1, exc); time.sleep(self.UPLOAD_RETRY_DELAY)
        return None
    def upload_files(self, model_cls, folder):
        ok = True
        for entry in model_cls.get_all(client_username=self.client_username):
            file_id = self._retry_upload(entry, json.dumps(self._prepare_content(entry, folder), ensure_ascii=False))
            identifier = entry.get('title') if model_cls is Product else str(entry.get('_id'))
            if not file_id or not model_cls.update(identifier, {'file_id': file_id}, client_username=self.client_username): ok = False
        return ok
    def create_vs(self):
        try:
            products, info = Product.get_all(client_username=self.client_username), Additionalinfo.get_all(client_username=self.client_username)
            if any(not p.get('file_id') for p in products): raise PermanentError('At least one product file was not uploaded.')
            file_ids = [item['file_id'] for item in products + info if item.get('file_id')]
            if not file_ids: raise PermanentError('No files to add to vector store.')
            self.clear_vs(); vs = self.client.vector_stores.create(name=f'Vector Store - {self.client_username}')
            for start in range(0, len(file_ids), self.BATCH_SIZE):
                batch = self.client.vector_stores.file_batches.create_and_poll(vector_store_id=vs.id, file_ids=file_ids[start:start+self.BATCH_SIZE], chunking_strategy={'type':'static','static':{'max_chunk_size_tokens':1000,'chunk_overlap_tokens':500}})
                if batch.status != 'completed': raise PermanentError(f'Vector store ingestion status: {batch.status}')
            Client.update(self.client_username, {'keys.vector_store_id': vs.id}); self._refresh(); return vs.id
        except Exception as exc: logger.error('Vector store creation failed: %s', exc, exc_info=True); return None
    def _disable_dm_assist(self):
        for platform in (Platform.INSTAGRAM.value, Platform.TELEGRAM.value): Client.update_module_status(self.client_username, platform, ModuleType.DM_ASSIST.value, False)
    def rebuild_all(self):
        stages = [('clear_files_product',self.clear_files(Product)), ('clear_files_additionalinfo',self.clear_files(Additionalinfo)), ('upload_files_product',self.upload_files(Product,'products')), ('upload_files_additionalinfo',self.upload_files(Additionalinfo,'info'))]
        for name, result in stages: Client.append_log(self.client_username, name, 'success' if result else 'failure')
        if not all(result for _, result in stages): self._disable_dm_assist(); return False
        vs_id = self.create_vs(); Client.append_log(self.client_username, 'create_vs', 'success' if vs_id else 'failure')
        if not vs_id: self._disable_dm_assist()
        return bool(vs_id)

    def _tools(self):
        tools = []
        if self.agent and self.agent.get('vector_store_id'):
            vs_id = self.agent.get('vector_store_id')
        else:
            vs_id = self.client_obj.get('keys', {}).get('vector_store_id')
        if vs_id: tools.append({'type':'file_search','vector_store_ids':[vs_id],'max_num_results':20})
        if get_app_settings(self.client_username).get(ModuleType.ORDERBOOK.value, False):
            props = {'tx_id':{'type':'integer'},'first_name':{'type':'string'},'last_name':{'type':'string'},'address':{'type':'string'},'phone':{'type':'string'},'product':{'type':'string'},'price':{'type':'string'},'count':{'type':'string'}}
            tools += [{'type':'function','name':'create_order','description':'Register a new order.','parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}, {'type':'function','name':'check_order','description':'Look up an order by transaction reference.','parameters':{'type':'object','properties':{'tx_id':{'type':'integer'}},'required':['tx_id'],'additionalProperties':False}}]
        return tools
    def _params(self, input_data, previous_response_id=None):
        model = (self.agent or {}).get('model') or self._setting('model', self.DEFAULT_MODEL)
        instructions = (self.agent or {}).get('instruction') if (self.agent or {}).get('instruction') is not None else self._setting('instructions', '')
        instructions = instructions or ''
        result = {'model':model,'instructions':instructions,'input':input_data,'tools':self._tools(),'store':True,'temperature':self._setting('temperature',1.0),'top_p':self._setting('top_p',1.0)}
        if previous_response_id: result['previous_response_id'] = previous_response_id
        return result
    def ensure_thread(self, user): return user.get('response_id') # old thread ids intentionally never reused
    def process_messages(self, previous_response_id, message_texts, user_id=None, user_query=None):
        content = '\n---\n'.join(str(msg) for msg in message_texts if msg)
        if not content: raise PermanentError('Cannot create a response from empty messages.')
        try:
            response = self._complete_functions(self.client.responses.create(**self._params(content, previous_response_id)))
            text = clean_sources(response.output_text or '')
            if not text: raise PermanentError('Responses API returned no text.')
            if user_id is not None:
                # user_query (preferred) targets the exact user document (same user_id can
                # exist once per client+platform+account); fall back to legacy lookup.
                query = user_query or {'user_id':str(user_id),'client_username':self.client_username}
                db.users.update_one(query,{'$set':{'response_id':response.id,'updated_at':datetime.now(timezone.utc)},'$unset':{'thread_id':''}})
            return text
        except openai.APIError as exc: raise RetryableError(f'OpenAI API error: {exc}') from exc
    def _complete_functions(self, response):
        while True:
            calls = [item for item in response.output if item.type == 'function_call']
            if not calls: return response
            outputs=[]
            for call in calls:
                result = self._handle_create_order(call.arguments) if call.name == 'create_order' else self._handle_check_order(call.arguments) if call.name == 'check_order' else f'Unsupported function: {call.name}'
                outputs.append({'type':'function_call_output','call_id':call.call_id,'output':result})
            response = self.client.responses.create(**self._params(outputs, response.id))
    def create_thread(self): return None # dashboard compatibility: no request is made until user sends a message

    def preview_agent(self, agent, message, conversation_id=None, image=None):
        """Run a one-off Responses call using an agent's model/instructions/vector store.
        Returns (reply_text, new_conversation_id)."""
        ag = {**(agent or {})}
        if not ag.get('model'): ag['model'] = self._setting('model', self.DEFAULT_MODEL)
        if ag.get('instruction') is None: ag['instruction'] = ''
        self.agent = ag
        input_payload = ''
        if image:
            input_payload = [{'type': 'input_text', 'text': message or ''}, {'type': 'input_image', 'image_url': image}]
            input_payload = [{'role': 'user', 'content': input_payload}] if input_payload else None
        else:
            input_payload = message or ''
        try:
            response = self._complete_functions(self.client.responses.create(**self._params(input_payload, conversation_id)))
            text = clean_sources(response.output_text or '')
            if not text: raise PermanentError('Responses API returned no text.')
            return text, response.id
        except openai.APIError as exc:
            raise RetryableError(f'OpenAI API error: {exc}') from exc
    def send_message_to_thread(self, previous_response_id, message):
        response=self._complete_functions(self.client.responses.create(**self._params(message, previous_response_id))); text=clean_sources(response.output_text or '')
        if not text: raise PermanentError('Responses API returned no text.')
        return text, response.id
    def _handle_create_order(self, arguments):
        try:
            args=json.loads(arguments) if isinstance(arguments,str) else arguments
            order=OrderbookRepository().create_order(status='created',date=datetime.now(timezone.utc),client_username=self.client_username,**args)
            return f"Order created successfully. Reference: {order.get('tx_id')}" if order else 'Failed to create order.'
        except Exception as exc: logger.error('create_order failed: %s',exc); return 'Error creating order.'
    def _handle_check_order(self, arguments):
        try:
            args=json.loads(arguments) if isinstance(arguments,str) else arguments; order=OrderbookRepository().get_order_by_tx_id(args['tx_id'],self.client_username)
            return f"Order status: {order.get('status')}, Product: {order.get('product')}, Price: {order.get('price')}, Count: {order.get('count')}" if order else 'Order not found.'
        except Exception as exc: logger.error('check_order failed: %s',exc); return 'Error checking order.'
