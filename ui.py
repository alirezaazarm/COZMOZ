import streamlit as st
from app.services.backend import Backend
from app.services.scraper import CozmozScraper
from app.services.openai_service import OpenAIService
import logging
from app.config import Config

logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
class AppConstants:
    """Centralized configuration for icons and messages"""
    ICONS = {
        "scraper": ":building_construction:" , # 🏗️
        "scrape": ":rocket:", # 🚀
        "update": ":arrows_counterclockwise:" , # 🔄
        "ai": ":robot_face:", # 🤖
        "delete": ":wastebasket:" , # 🗑️
        "add": ":heavy_plus_sign:" , # ➕
        "translate": ":earth_asia:" , # 🌍
        "success": ":white_check_mark:" , # ✅
        "error": ":x:" , # ❌
        "preview": ":package:" , # 📦
        "brain": ":brain:" , # 🧠
        "chat": ":speech_balloon:", # 💬
        "connect": ":link:", # 🔗
    }

    MESSAGES = {
        "scraping_start": "Scraping all products. This may take several minutes...",
        "update_start": "Checking for new products...",
        "processing_start": "Processing products - this may take several minutes..."
    }

class BaseSection:
    """Base class for UI sections"""
    def __init__(self, backend, scraper, openai_service):
        self.backend = backend
        self.scraper = scraper
        self.openai_service = openai_service
        self.const = AppConstants()

class AppStatusSection(BaseSection):
    """Handles application status settings"""
    def render(self):
        st.header("App Status")

        try:
            self._render_toggles()
            st.write("---")
        except RuntimeError as e:
            st.error(f"Error managing app status: {str(e)}")

    def _render_toggles(self):
        """Render configuration toggles"""
        settings = {
            "assistant": f"{self.const.ICONS['success']} Enable Assistant",
            "fixed_responses": f"{self.const.ICONS['success']} Enable Fixed Responses"
        }

        for key, label in settings.items():
            current_status = self.backend.get_app_setting(key)
            new_state = st.toggle(label, value=(current_status == "true"), key=f"{key}_toggle")

            if new_state != (current_status == "true"):
                self.backend.update_is_active(key, str(new_state).lower())
                status_msg = "enabled" if new_state else "disabled"
                icon = self.const.ICONS['success'] if new_state else self.const.ICONS['error']
                st.success(f"{icon} {key.replace('_', ' ').title()} {status_msg} successfully!")

class ProductScraperSection(BaseSection):
    """Handles product scraping functionality"""
    def render(self):
        st.header(f"{self.const.ICONS['scraper']} Product Scraper")

        col1, col2, col3 = st.columns(3)
        with col1:
            self._render_scrape_button()
        with col2:
            self._render_update_button()
        with col3:
            self._render_connect_button()

        self._render_product_table()
        st.write("---")

    def _render_scrape_button(self):
        if st.button(f"{self.const.ICONS['scrape']} Scrape All Products",
                     help="Scrape all products from scratch"):
            self._handle_scraping_action(self.scraper.scrape_products)

    def _render_update_button(self):
        if st.button(f"{self.const.ICONS['update']} Update Products",
                    help="Add new products only"):
            self._handle_scraping_action(self.scraper.update_products)
            
    def _render_connect_button(self):
        if st.button(f"{self.const.ICONS['connect']} Connect to Vector Store", 
                     help="Process all products, create a vector store, and connect it to the assistant."):
            
            # Create a placeholder for the status and logs
            status_placeholder = st.empty()
            log_placeholder = st.container()
            
            with status_placeholder:
                st.info("Starting product processing and vector store creation...")
            
            # Process the products and create vector store
            result = self.backend.connect_assistant_to_vs()
            
            # Display error logs if any (they're already filtered by the service)
            if 'logs' in result and result['logs']:
                # Only show the log container if there are error logs
                with log_placeholder:
                    log_container = st.expander("Error Logs", expanded=True)
                    with log_container:
                        for log in result['logs']:
                            if "error" in log.lower() or "failed" in log.lower():
                                st.error(log)
                            else:
                                st.warning(log)
            
            # Update the status with final result
            with status_placeholder:
                if result['success']:
                    st.success(f"{self.const.ICONS['success']} Vector store created successfully")
                    
                    # Display basic confirmation information
                    if 'processed_count' in result and 'total_count' in result:
                        processed_count = result['processed_count']
                        total_count = result['total_count']
                        batch_count = result.get('batch_count', 1)
                        error_count = total_count - processed_count if total_count > processed_count else 0
                        
                        batch_info = f" in {batch_count} batch{'es' if batch_count > 1 else ''}" if batch_count else ""
                        st.info(f"Successfully processed {processed_count} of {total_count} products{batch_info}. " + 
                                (f"({error_count} errors)" if error_count > 0 else ""))
                    
                    if 'vector_store_id' in result:
                        st.code(f"Vector Store ID: {result['vector_store_id']}")
                else:
                    # Don't show the detailed error message here since it's already in the error logs
                    st.error(f"{self.const.ICONS['error']} Failed to create vector store")
                    if 'logs' in result and not result['logs']:
                        # Only show message in status if no logs are displayed
                        st.error(result['message'])
                    
            # Don't trigger rerun as we want to keep the logs visible

    def _handle_scraping_action(self, action):
        try:
            with st.spinner(self.const.MESSAGES["scraping_start"]):
                action()
                st.success(f"{self.const.ICONS['success']} Operation completed!")
                st.rerun()
        except Exception as e:
            st.error(f"{self.const.ICONS['error']} Operation failed: {str(e)}")

    def _render_product_table(self):
        st.subheader(f"{self.const.ICONS['preview']} Product Table")
        try:
            products = self.backend.get_products()
            if products:
                st.dataframe(
                    products,
                    column_config={
                        "Link": st.column_config.LinkColumn("Product Link"),
                    },
                    use_container_width=True,
                    height=400
                )
            else:
                st.info("No products found. Click 'Scrape All Products' to get started!")
        except Exception as e:
            st.error(f"Failed to load products: {str(e)}")

class OpenAIManagementSection(BaseSection):
    """Handles OpenAI processing with improved UX"""
    def render(self):
        st.header(f"{self.const.ICONS['ai']} OpenAI Management")

        # Only show warning if no vector store is configured
        vs_id = self.backend.get_current_vs_id()
        if not vs_id:
            st.warning("No vector store currently available. Please connect to a vector store before testing the assistant.")
            
        # Create tabs for instruction management and chat testing
        instruction_tab, chat_tab = st.tabs([
            f"{self.const.ICONS['brain']} Assistant Instructions", 
            f"{self.const.ICONS['chat']} Test Assistant"
        ])
        
        # Instructions tab content
        with instruction_tab:
            self._render_instructions_section()
            
        # Chat testing tab content
        with chat_tab:
            if vs_id:
                self._render_chat_testing_section()
            else:
                st.error("You need to connect to a vector store first before testing the assistant. Go to the Product Scraper section and click 'Connect to Vector Store'.")

        # Add separator line between OpenAI Management and Fixed Responses sections
        st.markdown("---")

    def _render_instructions_section(self):
        # Get current instructions
        current_instructions = self.backend.get_assistant_instructions()
        
        if current_instructions:
            # Display the current instructions in a text area that can be edited
            new_instructions = st.text_area(
                "Edit Assistant Instructions", 
                value=current_instructions,
                height=300,
                help="Edit the instructions and click 'Update Instructions' to save changes."
            )
        else:
            new_instructions = st.text_area(
                "Set Assistant Instructions", 
                value="Enter instructions for the assistant...",
                height=300,
                help="Enter instructions and click 'Update Instructions' to save."
            )

        # Button to update instructions
        if st.button(f"{self.const.ICONS['update']} Update Instructions", 
                    help="Update the assistant's instructions with the text above."):
            with st.spinner("Updating assistant instructions..."):
                result = self.backend.update_assistant_instructions(new_instructions)
                if result['success']:
                    st.success(f"{self.const.ICONS['success']} {result['message']}")
                else:
                    st.error(f"{self.const.ICONS['error']} {result['message']}")
                    
    def _render_chat_testing_section(self):
        st.subheader("Test your assistant")
        
        # Create a new thread for each session if not already created
        if 'thread_id' not in st.session_state:
            try:
                # Create a new thread and store its ID
                thread_id = self.openai_service.create_thread()
                st.session_state['thread_id'] = thread_id
                st.session_state['messages'] = []
            except Exception as e:
                st.error(f"Failed to create thread: {str(e)}")
                return

        # Create a container for the chat messages
        chat_container = st.container()
        
        # Create a container for the input field at the bottom
        input_container = st.container()
        
        # Display existing messages in the chat container
        with chat_container:
            for message in st.session_state.get('messages', []):
                with st.chat_message(message["role"]):
                    st.write(message["content"])
        
        # Get user input at the bottom
        with input_container:
            user_input = st.chat_input("Type your message here...")
        
        if user_input:
            # Add user message to chat
            st.session_state['messages'].append({"role": "user", "content": user_input})
            with chat_container:
                with st.chat_message("user"):
                    st.write(user_input)
            
            # Send to assistant and get response
            with st.spinner("Assistant is thinking..."):
                try:
                    response = self.openai_service.send_message_to_thread(
                        st.session_state['thread_id'], 
                        user_input
                    )
                    
                    # Add assistant response to chat
                    st.session_state['messages'].append({"role": "assistant", "content": response})
                    with chat_container:
                        with st.chat_message("assistant"):
                            st.write(response)
                except Exception as e:
                    st.error(f"Error getting response: {str(e)}")

class FixedResponsesSection(BaseSection):
    """Manages fixed responses configuration"""
    def render(self):
        st.header("Fixed Responses")
        incoming_type = st.radio(
            "Select Incoming Type",
            options=["Direct", "Comment"],
            index=0,
            horizontal=True,
            key="incoming_type"
        )

        existing_tab, add_new_tab = st.tabs(["Existing", "Add New"])

        with existing_tab:
            self._render_existing_responses(incoming_type)

        with add_new_tab:
            self._render_new_response_form(incoming_type)

        st.write("---")

    def _render_existing_responses(self, incoming_type):
        st.subheader(f"Existing {incoming_type} Fixed Responses")
        try:
            responses = self.backend.get_fixed_responses(incoming=incoming_type)
            if responses:
                for resp in responses:
                    self._render_response_card(resp, incoming_type)
            else:
                st.info(f"No {incoming_type.lower()} fixed responses available.")
        except RuntimeError as e:
            st.error(str(e))

    def _render_response_card(self, response, incoming_type):
        with st.container():
            updated_time = self.backend.format_updated_at(response.get("updated_at"))
            st.markdown(f"Updated {updated_time}")

            trigger = st.text_input(
                "Trigger",
                value=response["trigger_keyword"],
                key=f"trigger_{response['id']}"
            )

            if incoming_type == "Direct":
                self._render_direct_response(response, trigger)
            else:
                self._render_comment_response(response, trigger)

            st.write("---")

    def _render_direct_response(self, response, trigger):
        direct_text = st.text_area(
            "Direct Response Text",
            value=response["direct_response_text"] or "",
            key=f"direct_text_{response['id']}",
            height=100
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Save", key=f"save_{response['id']}"):
                self._update_response(response, trigger, direct_text, None)
        with col2:
            self._render_delete_button(response["id"])

    def _render_comment_response(self, response, trigger):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col1:
            direct_toggle = st.toggle(
                "Direct",
                value=bool(response["direct_response_text"]),
                key=f"direct_toggle_{response['id']}"
            )
        with col2:
            comment_toggle = st.toggle(
                "Comment",
                value=bool(response["comment_response_text"]),
                key=f"comment_toggle_{response['id']}"
            )

        direct_text = self._conditional_text_area(
            direct_toggle,
            "Direct Response Text",
            response["direct_response_text"],
            f"direct_text_{response['id']}"
        )

        comment_text = self._conditional_text_area(
            comment_toggle,
            "Comment Response Text",
            response["comment_response_text"],
            f"comment_text_{response['id']}"
        )

        with col3:
            if st.button("Save", key=f"save_{response['id']}"):
                self._update_response(response, trigger, direct_text, comment_text)
        with col4:
            self._render_delete_button(response["id"])

    def _conditional_text_area(self, condition, label, value, key):
        if condition:
            return st.text_area(label, value=value or "", key=key, height=100)
        return None

    def _update_response(self, response, trigger, direct_text, comment_text):
        try:
            self.backend.update_fixed_response(
                response["id"],
                trigger,
                comment_response_text=comment_text,
                direct_response_text=direct_text,
                incoming=response["incoming"]
            )
            st.success("Fixed response updated successfully!")
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))

    def _render_delete_button(self, response_id):
        if st.button(self.const.ICONS['delete'], key=f"delete_{response_id}"):
            try:
                self.backend.delete_fixed_response(response_id)
                st.success("Fixed response deleted successfully!")
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))

    def _render_new_response_form(self, incoming_type):
        st.subheader(f"Add New {incoming_type} Response")
        new_trigger = st.text_input("New Trigger", key="new_trigger")

        if incoming_type == "Direct":
            new_direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=100)
            new_comment_text = None
        else:
            col1, col2 = st.columns([1, 1])
            with col1:
                new_direct_toggle = st.toggle("Direct", key="new_direct_toggle")
            with col2:
                new_comment_toggle = st.toggle("Comment", key="new_comment_toggle")

            new_direct_text = self._conditional_text_area(new_direct_toggle, "Direct Response Text", "", "new_direct_text")
            new_comment_text = self._conditional_text_area(new_comment_toggle, "Comment Response Text", "", "new_comment_text")

        if st.button("Add Response", key="add_response_button"):
            if not new_trigger:
                st.error("Trigger is required.")
                return

            try:
                self.backend.add_fixed_response(
                    new_trigger,
                    comment_response_text=new_comment_text,
                    direct_response_text=new_direct_text,
                    incoming=incoming_type
                )
                st.success("Fixed response added successfully!")
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))

class AdminUI:
    """Main application container"""
    def __init__(self):
        self.backend = Backend()
        self.scraper = CozmozScraper()
        self.openai_service = OpenAIService()

        self.sections = [
            AppStatusSection(self.backend, self.scraper, self.openai_service),
            ProductScraperSection(self.backend, self.scraper, self.openai_service),
            OpenAIManagementSection(self.backend, self.scraper, self.openai_service),
            FixedResponsesSection(self.backend, self.scraper, self.openai_service)
        ]

    def render(self):
        """Render all application sections"""
        for section in self.sections:
            section.render()

if __name__ == "__main__":
    app = AdminUI()
    app.render()