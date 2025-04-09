import torch
import logging
from types import MethodType

# Patch torch.classes to avoid crash on __path__._path access
def safe_getattr(self, attr):
    try:
        return object.__getattribute__(self, attr)
    except RuntimeError as e:
        if "__path__._path" in str(e) or "Class __path__._path not registered" in str(e):
            logging.warning("Bypassed Torch class registration error for '__path__._path'")
            return None
        raise

# Replace the __getattr__ method with our patched version
torch.classes.__class__.__getattr__ = MethodType(safe_getattr, torch.classes)

import streamlit as st
from app.services.backend import Backend # Assuming Backend class is defined here or imported
from functools import partial # Import partial for callbacks

# --- (Keep existing logging setup and AppConstants) ---
logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
#===============================================================================================================================
class AppConstants:
    """Centralized configuration for icons and messages"""
    ICONS = {
        "scraper": ":building_construction:" ,
        "scrape": ":rocket:",
        "update": ":arrows_counterclockwise:" ,
        "ai": ":robot_face:",
        "delete": ":wastebasket:" ,
        "add": ":heavy_plus_sign:" ,
        "translate": ":earth_asia:" ,
        "success": ":white_check_mark:" ,
        "error": ":x:" ,
        "preview": ":package:" ,
        "brain": ":brain:" ,
        "chat": ":speech_balloon:",
        "connect": ":link:",
        "instagram": ":camera:",
        "post": ":newspaper:",
        "story": ":film_frames:",
        "fixed_response": ":memo:",
        "previous": ":arrow_left:",
        "next": ":arrow_right:",
        "label": ":label:",
        "save": ":floppy_disk:",
        "model": ":brain:", # Added icon for model
    }

    MESSAGES = {
        "scraping_start": "Scraping all products. This may take several minutes...",
        "update_start": "Checking for new products...",
        "processing_start": "Processing products - this may take several minutes..."
    }
#===============================================================================================================================
class BaseSection:
    """Base class for UI sections"""
    def __init__(self, backend):
        self.backend = backend
        self.const = AppConstants()
#===============================================================================================================================
# --- (Keep AppStatusSection, ProductScraperSection, OpenAIManagementSection as they are) ---
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
#===============================================================================================================================
class ProductScraperSection(BaseSection):
    """Handles product scraping functionality, now calling Backend (no direct CozmozScraper)."""
    def render(self):
        st.header(f"{self.const.ICONS['scraper']} Product Scraper")

        col1, col2 = st.columns(2)

        with col1:
            self._render_update_products_button()
        with col2:
            self._render_translate_button()

        self._render_product_table()
        st.write("---")

    def _render_update_products_button(self):
        if st.button(f"{self.const.ICONS['update']} Update Products",
                    help="Add new products only"):
            self._handle_scraping_action(self.backend.update_products)

    def _render_translate_button(self):
        if st.button(f"{self.const.ICONS['translate']} Translate Titles", help="Translate product titles"):
            with st.spinner("Translating titles..."):
                success = self.backend.translate_titles()
            if success:
                st.success(f"{self.const.ICONS['success']} Titles translated successfully!")
            else:
                st.error(f"{self.const.ICONS['error']} Failed to translate titles!")

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
#===============================================================================================================================
class OpenAIManagementSection(BaseSection):
    """Handles OpenAI processing with improved UX (all calls via Backend)."""
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
                thread_id = self.backend.create_chat_thread()
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
                    response = self.backend.send_message_to_thread(
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
#===============================================================================================================================
class InstagramSection(BaseSection):
    """Handles Instagram-related functionality including posts, stories, and fixed responses."""
    def __init__(self, backend):
        super().__init__(backend)
        # Initialize session state for custom labels if not already present
        if 'custom_labels' not in st.session_state:
            st.session_state['custom_labels'] = [] # Store newly added custom labels here

    def render(self):
        st.header(f"{self.const.ICONS['instagram']} Instagram Management")

        # Create tabs for different Instagram functionalities
        posts_tab, stories_tab, fixed_responses_tab = st.tabs([
            f"{self.const.ICONS['post']} Posts",
            f"{self.const.ICONS['story']} Stories",
            f"{self.const.ICONS['fixed_response']} Fixed Responses"
        ])

        with posts_tab:
            self._render_posts_tab()

        with stories_tab:
            self._render_stories_tab()

        with fixed_responses_tab:
            self._render_fixed_responses_section()

        st.write("---")

    def _render_posts_tab(self):
        """Renders the section for managing and viewing Instagram posts."""
        # --- Row for Get/Update Posts, Set Labels by Model, and Add New Label ---
        col1, col2, col3, col4 = st.columns([1, 1, 2, 1]) # Adjust column ratios

        with col1:
            if st.button(f"{self.const.ICONS['update']} Get/Update Posts", help="Fetch and update all Instagram posts", use_container_width=True):
                with st.spinner("Fetching posts from Instagram..."):
                    try:
                        success = self.backend.fetch_instagram_posts()
                        if success:
                            st.success(f"{self.const.ICONS['success']} Posts fetched and updated successfully!")
                            st.rerun() # Rerun to refresh the post display
                        else:
                            st.error(f"{self.const.ICONS['error']} Failed to fetch posts from Instagram")
                    except Exception as e:
                        st.error(f"{self.const.ICONS['error']} Error fetching posts: {str(e)}")

        with col2:
            if st.button(f"{self.const.ICONS['model']} Set Labels by Model", help="Use AI to automatically label posts based on product matches", use_container_width=True):
                with st.spinner("AI is analyzing posts and setting labels..."):
                    try:
                        # Check if the backend method exists before calling
                        if hasattr(self.backend, 'set_labels_by_model'):
                            result = self.backend.set_labels_by_model()
                            # Assuming the backend method returns a dict with 'success' and 'message' keys
                            if result and result.get('success'):
                                st.success(f"{self.const.ICONS['success']} {result.get('message', 'Labels set successfully by model!')}")
                                st.rerun() # Refresh grid to show new labels
                            else:
                                st.error(f"{self.const.ICONS['error']} {result.get('message', 'Failed to set labels by model.')}")
                        else:
                            st.error(f"{self.const.ICONS['error']} Backend function 'set_labels_by_model' not found.")
                    except Exception as e:
                        st.error(f"{self.const.ICONS['error']} Error setting labels by model: {str(e)}")

        with col3:
            new_label = st.text_input(
                "Enter a new label to add to the dropdown list:",
                key="new_custom_label_input",
                placeholder="Add custom label",
                label_visibility="collapsed" # Hide the label text itself
            )

        with col4:
            if st.button(f"{self.const.ICONS['add']} Add Label", key="add_custom_label_button", use_container_width=True):
                new_label_stripped = new_label.strip()
                if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']:
                    # NOTE: Ideally, this would call a backend function to persist the label.
                    # Using session_state for simplicity in this example.
                    st.session_state['custom_labels'].append(new_label_stripped)
                    st.success(f"Added '{new_label_stripped}' to label options.")
                    # Clear the input field after adding - REMOVED to prevent StreamlitAPIException
                    # st.session_state.new_custom_label_input = ""
                    st.rerun() # Rerun to update dropdowns immediately
                elif not new_label_stripped:
                    st.warning("Label cannot be empty.")
                else:
                    st.warning(f"Label '{new_label_stripped}' already exists.")

        st.markdown("---") # Separator before the grid
        self._render_post_grid()


    def _handle_label_change(self, post_id, select_key):
        """Callback function to handle label selection change and save automatically."""
        selected_label = st.session_state.get(select_key, "-- Select --") # Default to generic select

        # Only save if a valid label (not the default placeholder) is selected
        final_label_to_save = selected_label if selected_label != "-- Select --" else ""

        if not post_id:
            st.error("Cannot save label: Post ID is missing.")
            return # Prevent further action

        # Attempt to save the selected label (or empty string if "-- Select --" was chosen)
        if hasattr(self.backend, 'set_label'):
            try:
                success = self.backend.set_label(post_id, final_label_to_save)
                if not success:
                    # This might occur if the post was deleted between rendering and saving
                    st.warning(f"Could not save label for post {post_id}. Post might not exist.")
            except Exception as e:
                st.error(f"{self.const.ICONS['error']} Error saving label for post {post_id}: {str(e)}")
        else:
            st.error("Backend function 'set_label' not found.")


    def _render_post_grid(self):
        """Renders Instagram posts in a 4-column scrollable grid with simplified labeling."""
        try:
            posts = self.backend.get_posts()
            products_data = self.backend.get_products()
            # Combine product titles and custom labels for the dropdown
            product_titles = sorted([p['Title'] for p in products_data if p.get('Title')])
            # Get custom labels from session state
            custom_labels = st.session_state.get('custom_labels', [])
            # Combine, remove duplicates (if any overlap), and add the placeholder
            all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels)))

        except Exception as e:
            st.error(f"Error loading posts or products: {str(e)}")
            return

        if not posts:
            st.info("No posts found in the database. Click 'Get/Update Posts' to fetch them.")
            return

        num_columns = 4
        cols = st.columns(num_columns)

        for index, post in enumerate(posts):
            post_id = post.get('id')
            if not post_id:
                post_id_key = f"index_{index}"
                st.warning(f"Post at index {index} missing database ID. Labeling will not persist.")
            else:
                post_id_key = str(post_id)

            col_index = index % num_columns
            with cols[col_index]:
                with st.container(border=True):
                    media_url = post.get('media_url')
                    caption = post.get('caption', 'No caption available.')

                    if media_url:
                        st.image(media_url, use_container_width=True)
                    else:
                        st.warning("Media URL not found.")

                    st.caption(f"**Caption:** {caption}")
                    # --- Simplified Labeling Section ---
                    # Determine the current label and set the default index for the selectbox
                    current_label = post.get('label', '')
                    try:
                        # Find the index in the combined list (including "-- Select --")
                        default_select_index = all_labels.index(current_label) if current_label else 0
                    except ValueError:
                        # Label exists but isn't in the current list (maybe added then removed?)
                        # Add it temporarily for this post's display or default to 0
                        if current_label:
                            st.warning(f"Label '{current_label}' for post {post_id} not in current options. Adding temporarily.")
                            all_labels.append(current_label) # Add for this dropdown instance
                            default_select_index = all_labels.index(current_label)
                        else:
                            default_select_index = 0 # Default to "-- Select --"

                    # --- Define unique key for this post's selectbox ---
                    select_key = f"label_select_{post_id_key}"

                    # --- Create callback ---
                    on_change_callback = partial(
                        self._handle_label_change,
                        post_id=post_id, # Pass the actual DB ID
                        select_key=select_key
                    )

                    # Dropdown for product titles and custom labels
                    st.selectbox(
                        label=self.const.ICONS['label'], # Use icon as label
                        options=all_labels,
                        key=select_key, # Use unique key
                        index=default_select_index, # Set default index based on current label
                        on_change=on_change_callback, # Trigger callback on change
                        help="Select a label for this post. Changes are saved automatically." # Add help text
                    )
                    # --- Removed custom text input and "Label Post" title ---


    def _render_stories_tab(self):
        """Renders the section for managing Instagram stories."""
        st.subheader("Instagram Stories")

        if st.button(f"{self.const.ICONS['update']} Get/Update Stories", help="Fetch and update all Instagram stories"):
            with st.spinner("Fetching stories from Instagram..."):
                try:
                    success = self.backend.fetch_instagram_stories()
                    if success:
                        st.success(f"{self.const.ICONS['success']} Stories fetched and updated successfully!")
                    else:
                        st.error(f"{self.const.ICONS['error']} Failed to fetch stories from Instagram")
                except Exception as e:
                    st.error(f"{self.const.ICONS['error']} Error fetching stories: {str(e)}")

        # Placeholder for displaying stories if needed in the future
        st.info("Story viewing is not implemented yet.")


    def _render_fixed_responses_section(self):
        """Renders the fixed responses section (called within its tab)."""
        st.subheader("Manage Fixed Responses")
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
        # Use unique container key based on response ID
        with st.container(border=True): # Added border for visual separation
            updated_time = self.backend.format_updated_at(response.get("updated_at"))
            st.markdown(f"_Updated {updated_time}_")

            trigger = st.text_input(
                "Trigger",
                value=response["trigger_keyword"],
                key=f"trigger_{response['id']}"
            )

            if incoming_type == "Direct":
                self._render_direct_response(response, trigger)
            else: # Comment type
                self._render_comment_response(response, trigger)


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
        # Layout toggles first
        col_t1, col_t2, col_t3, col_t4 = st.columns([1, 1, 1, 1]) # Use separate columns for toggles if needed
        with col_t1:
            direct_toggle = st.toggle(
                "Direct",
                value=bool(response["direct_response_text"]),
                key=f"direct_toggle_{response['id']}"
            )
        with col_t2:
            comment_toggle = st.toggle(
                "Comment",
                value=bool(response["comment_response_text"]),
                key=f"comment_toggle_{response['id']}"
            )

        # Conditionally display text areas based on toggles
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

        # Save and Delete buttons below text areas
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("Save", key=f"save_{response['id']}"):
                self._update_response(response, trigger, direct_text, comment_text)
        with col_b2:
            self._render_delete_button(response["id"])

    def _conditional_text_area(self, condition, label, value, key):
        if condition:
            return st.text_area(label, value=value or "", key=key, height=100)
        return None # Return None if not displayed

    def _update_response(self, response, trigger, direct_text, comment_text):
        try:
            # Ensure text is None if the corresponding toggle was off (important for DB update)
            final_direct_text = direct_text if direct_text is not None else None
            final_comment_text = comment_text if comment_text is not None else None

            self.backend.update_fixed_response(
                response["id"],
                trigger,
                comment_response_text=final_comment_text,
                direct_response_text=final_direct_text,
                incoming=response["incoming"] # Pass incoming type correctly
            )
            st.success(f"{self.const.ICONS['success']} Fixed response updated successfully!")
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
        except Exception as e: # Catch potential errors more broadly
             st.error(f"An unexpected error occurred during update: {str(e)}")


    def _render_delete_button(self, response_id):
        # Use a more descriptive key for the delete button
        if st.button(f"{self.const.ICONS['delete']} Delete", key=f"delete_{response_id}", help="Delete this fixed response"):
            try:
                self.backend.delete_fixed_response(response_id)
                st.success(f"{self.const.ICONS['success']} Fixed response deleted successfully!")
                # Clear relevant session state if needed, then rerun
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
            except Exception as e: # Catch potential errors more broadly
                st.error(f"An unexpected error occurred during deletion: {str(e)}")


    def _render_new_response_form(self, incoming_type):
        st.subheader(f"Add New {incoming_type} Response")
        with st.form(key=f"new_{incoming_type}_response_form"):
            new_trigger = st.text_input("New Trigger*", key="new_trigger")

            if incoming_type == "Direct":
                new_direct_text = st.text_area("Direct Response Text*", key="new_direct_text", height=100)
                new_comment_text = None
                # Validation check
                is_valid = new_trigger and new_direct_text
            else: # Comment type
                col1, col2 = st.columns([1, 1])
                with col1:
                    new_direct_toggle = st.toggle("Send Direct Response?", key="new_direct_toggle")
                with col2:
                    new_comment_toggle = st.toggle("Send Comment Response?", key="new_comment_toggle")

                new_direct_text = self._conditional_text_area(new_direct_toggle, "Direct Response Text", "", "new_direct_text")
                new_comment_text = self._conditional_text_area(new_comment_toggle, "Comment Response Text", "", "new_comment_text")
                # Validation check: need trigger and at least one response type
                is_valid = new_trigger and (new_direct_text or new_comment_text)

            submitted = st.form_submit_button(f"{self.const.ICONS['add']} Add Response")

            if submitted:
                if not is_valid:
                    if not new_trigger:
                        st.error("Trigger is required.")
                    elif incoming_type == "Direct" and not new_direct_text:
                         st.error("Direct Response Text is required for Direct type.")
                    elif incoming_type == "Comment" and not (new_direct_text or new_comment_text):
                         st.error("At least one response (Direct or Comment) is required for Comment type.")
                    return # Stop processing if invalid

                try:
                    self.backend.add_fixed_response(
                        new_trigger,
                        comment_response_text=new_comment_text,
                        direct_response_text=new_direct_text,
                        incoming=incoming_type
                    )
                    st.success(f"{self.const.ICONS['success']} Fixed response added successfully!")
                except RuntimeError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"An unexpected error occurred: {str(e)}")

#===============================================================================================================================
class AdminUI:
    """Main application container"""
    def __init__(self):
        st.set_page_config(layout="wide")
        try:
            self.backend = Backend()
        except NameError:
            st.error("Backend class definition not found. Please ensure it's defined or imported.")
            class DummyBackend:
                def __getattr__(self, name):
                    def method(*args, **kwargs):
                        print(f"DummyBackend: Method '{name}' called with args={args}, kwargs={kwargs}")
                        if name == 'get_labels': return {}
                        if name == 'get_posts': return []
                        if name == 'get_products': return []
                        if name == 'set_labels_by_model': return {'success': True, 'message': 'Dummy success!'} # Add dummy method
                        return None
                    return method
            self.backend = DummyBackend()


        self.sections = [
            AppStatusSection(self.backend),
            ProductScraperSection(self.backend),
            OpenAIManagementSection(self.backend),
            InstagramSection(self.backend) # Ensure InstagramSection is initialized correctly
        ]

    def render(self):
        """Render all application sections"""
        st.title("Admin Dashboard")
        for section in self.sections:
            section.render()

if __name__ == "__main__":
    app = AdminUI()
    app.render()
