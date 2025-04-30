import logging
import streamlit as st
from app.services.backend import Backend
from functools import partial

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
        "model": ":brain:",
        "folder": ":open_file_folder:"
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
        self._render_update_products_button()

        self._render_product_table()
        st.write("---")

    def _render_update_products_button(self):
        if st.button(f"{self.const.ICONS['update']} Update Products",
                    help="Add new products only"):
            self._handle_scraping_action(self.backend.update_products)

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
        settings_tab, chat_tab = st.tabs([
            f"{self.const.ICONS['brain']} Assistant Settings",
            f"{self.const.ICONS['chat']} Test Assistant"
        ])

        # Instructions tab content
        with settings_tab:
            self._render_settings_section()

        # Chat testing tab content
        with chat_tab:
            if vs_id:
                self._render_chat_testing_section()
            else:
                st.error("You need to connect to a vector store first before testing the assistant. Go to the Product Scraper section and click 'Connect to Vector Store'.")

        # Add separator line between OpenAI Management and Fixed Responses sections
        st.markdown("---")

    def _render_settings_section(self):
        # Get current settings
        current_instructions = self.backend.get_assistant_instructions()
        current_temperature = self.backend.get_assistant_temperature()
        current_top_p = self.backend.get_assistant_top_p()

        # Instruction area (full width)
        new_instructions = st.text_area(
            "Assistant Instructions",
            value=current_instructions if current_instructions else "Enter instructions...",
            height=600,
            help="How the assistant should behave",
            label_visibility="collapsed"  # Minimal: move label to placeholder
        )

        # Compact controls row
        col1, col2, col3 = st.columns([4, 2, 4])

        with col1:
            new_temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(current_temperature),
                step=0.01,
                help="Randomness (0=strict, 2=creative)"
            )

        with col2:
            # Vertically centered update button
            st.write("")  # spacer
            update_btn = st.button(
                f"{self.const.ICONS['update']} Update All",
                use_container_width=True,
                help="Save all settings"
            )
            st.write("")  # spacer

        with col3:
            new_top_p = st.slider(
                "Top-P",
                min_value=0.0,
                max_value=1.0,
                value=float(current_top_p),
                step=0.01,
                help="Focus (1=broad, 0=narrow)"
            )

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
                    errors = [
                        f"{name}: {result['message']}"
                        for name, result in results.items()
                        if not result['success']
                    ]
                    st.error(f"{self.const.ICONS['error']} Issues: {', '.join(errors)}")

    def _render_chat_testing_section(self):
        st.subheader("Test your assistant")

        # --- Initialization ---
        if 'thread_id' not in st.session_state:
            try:
                thread_id = self.backend.create_chat_thread()
                st.session_state['thread_id'] = thread_id
                st.session_state['messages'] = []
                # Flag to track if the current user message (text or image) has been sent
                st.session_state['user_message_sent'] = True
                # Set to store IDs of already processed file uploads
                st.session_state['processed_file_ids'] = set()
            except Exception as e:
                st.error(f"Failed to create thread: {str(e)}")
                return
        # Ensure processed_file_ids exists even if thread creation fails but session persists
        if 'processed_file_ids' not in st.session_state:
             st.session_state['processed_file_ids'] = set()


        # --- UI Layout ---
        chat_container = st.container()
        chat_container.height = 400 # Set a fixed height

        input_container = st.container()

        # --- Input Handling ---
        new_user_input = None

        # Image Uploader
        with input_container:
            uploaded_file = st.file_uploader(
                "Upload an image (optional)",
                type=['png', 'jpg', 'jpeg'],
                key="chat_image_uploader" # Keep the key for widget identity
            )

            if uploaded_file is not None:
                 # --- Check if this specific file upload has already been processed ---
                 if uploaded_file.file_id not in st.session_state['processed_file_ids']:
                    with st.spinner("Analyzing image..."):
                        try:
                            # Mark as processing attempt (even before success)
                            # Add ID immediately to prevent race conditions across reruns
                            st.session_state['processed_file_ids'].add(uploaded_file.file_id)

                            image_bytes = uploaded_file.getvalue()
                            analysis_result = self.backend.process_uploaded_image(image_bytes)
                            new_user_input = f"Analysis of uploaded image: {analysis_result}"

                            # Display the image and analysis temporarily
                            with chat_container:
                                 with st.chat_message("user"):
                                     st.image(image_bytes, width=150)
                                     st.write(new_user_input)

                        except Exception as e:
                            st.error(f"Error handling image upload: {str(e)}")
                            new_user_input = None # Don't proceed if image processing failed
                            # Optionally remove ID if processing failed catastrophically?
                            # st.session_state['processed_file_ids'].remove(uploaded_file.file_id)


            # Text Input (runs after image uploader logic)
            user_text_input = st.chat_input("Type your message here...")

            if user_text_input:
                # Prioritize text input if both image and text happened
                new_user_input = user_text_input
                # Clear processed file IDs if new text is submitted? Optional.
                # st.session_state['processed_file_ids'].clear()


        # --- Update Message History and State ---
        if new_user_input:
            # Add the processed input (image analysis or text) to messages
            st.session_state['messages'].append({"role": "user", "content": new_user_input})
            st.session_state['user_message_sent'] = False # Mark that a new user message needs sending
            # DO NOT RERUN HERE YET

        # --- Display Chat History ---
        with chat_container:
            # Always display the full message history from session state
            for message in st.session_state.get('messages', []):
                 with st.chat_message(message["role"]):
                     st.write(message["content"])


        # --- Assistant Interaction ---
        # Check if there's a new user message that hasn't been sent yet
        if not st.session_state.get('user_message_sent', True):
            last_message = st.session_state['messages'][-1] if st.session_state['messages'] else None

            if last_message and last_message["role"] == "user":
                with st.spinner("Assistant is thinking..."):
                    try:
                        response = self.backend.send_message_to_thread(
                            st.session_state['thread_id'],
                            last_message["content"]
                        )
                        st.session_state['messages'].append({"role": "assistant", "content": response})
                        st.session_state['user_message_sent'] = True # Mark user message as processed

                        # --- Single Rerun Point ---
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error getting response: {str(e)}")
                        # Set flag back to True to avoid retrying the same failed message automatically
                        st.session_state['user_message_sent'] = True
#===============================================================================================================================

class InstagramSection(BaseSection):
    """Handles Instagram-related functionality including posts, stories, and fixed responses."""
    def __init__(self, backend):
        super().__init__(backend)
        # Initialize session state for custom labels and pagination if not already present
        if 'custom_labels' not in st.session_state:
            st.session_state['custom_labels'] = []
        if 'post_page' not in st.session_state:
            st.session_state['post_page'] = 0
        if 'posts_per_page' not in st.session_state:
            st.session_state['posts_per_page'] = 8  # Default to 8 posts per page (2 rows of 4)
        if 'post_filter' not in st.session_state:
            st.session_state['post_filter'] = "All"

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
        """Renders the section for managing and viewing Instagram posts with optimized performance."""
        # --- Top Control Bar with Reduced Elements ---
        col1, col2, col3 = st.columns([1, 1, 2])  # Simplified layout

        with col1:
            if st.button(f"{self.const.ICONS['update']} Update Posts", help="Fetch and update Instagram posts", use_container_width=True):
                with st.spinner("Fetching posts..."):
                    try:
                        success = self.backend.fetch_instagram_posts()
                        if success:
                            st.success(f"{self.const.ICONS['success']} Posts updated!")
                            st.rerun()
                        else:
                            st.error(f"{self.const.ICONS['error']} Fetch failed")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col2:
            if st.button(f"{self.const.ICONS['model']} AI Label", help="Auto-label posts with AI", use_container_width=True):
                with st.spinner("AI labeling..."):
                    try:
                        if hasattr(self.backend, 'set_labels_by_model'):
                            result = self.backend.set_labels_by_model()
                            if result and result.get('success'):
                                st.success(f"Labels updated!")
                                st.rerun()
                            else:
                                st.error(f"Labeling failed")
                        else:
                            st.error(f"Function not found")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col3:
            # Combine label input and button in one line for space efficiency
            col3a, col3b = st.columns([3, 1])
            with col3a:
                new_label = st.text_input(
                    "New label",
                    key="new_custom_label_input",
                    placeholder="Add custom label",
                    label_visibility="collapsed"
                )
            with col3b:
                if st.button(f"{self.const.ICONS['add']}", key="add_custom_label_button", help="Add new label", use_container_width=True):
                    new_label_stripped = new_label.strip()
                    if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']:
                        st.session_state['custom_labels'].append(new_label_stripped)
                        st.success(f"Added '{new_label_stripped}'")
                        st.rerun()
                    elif not new_label_stripped:
                        st.warning("Label cannot be empty")
                    else:
                        st.warning(f"Label already exists")

        # --- Filter and Pagination Controls ---
        try:
            # Lazy load posts only once for this render
            posts = self.backend.get_posts()
            total_posts = len(posts)

            if not posts:
                st.info("No posts found. Click 'Update Posts' to fetch them.")
                return

            # Get all unique labels for filtering
            all_labels = sorted(list(set(post.get('label', '') for post in posts if post.get('label', ''))))
            filter_options = ["All"] + all_labels

            col_filter, col_per_page, col_pagination = st.columns([2, 1, 2])

            with col_filter:
                # Filter selector
                selected_filter = st.selectbox(
                    "Filter by label",
                    options=filter_options,
                    index=filter_options.index(st.session_state['post_filter']) if st.session_state['post_filter'] in filter_options else 0,
                    key="post_filter_selector",
                    on_change=lambda: self._handle_filter_change()
                )
                st.session_state['post_filter'] = selected_filter

            with col_per_page:
                # Posts per page selector
                st.selectbox(
                    "Posts per page",
                    options=[4, 8, 12, 16],
                    index=[4, 8, 12, 16].index(st.session_state['posts_per_page']) if st.session_state['posts_per_page'] in [4, 8, 12, 16] else 1,
                    key="posts_per_page_selector",
                    on_change=lambda: self._handle_page_size_change()
                )

            # Filter posts based on selection
            if st.session_state['post_filter'] != "All":
                filtered_posts = [post for post in posts if post.get('label', '') == st.session_state['post_filter']]
            else:
                filtered_posts = posts

            filtered_count = len(filtered_posts)
            max_pages = (filtered_count - 1) // st.session_state['posts_per_page'] + 1 if filtered_count > 0 else 1

            # Ensure current page is valid after filtering
            if st.session_state['post_page'] >= max_pages:
                st.session_state['post_page'] = max_pages - 1

            with col_pagination:
                # Pagination controls
                pagination_cols = st.columns([1, 3, 1])
                with pagination_cols[0]:
                    prev_disabled = st.session_state['post_page'] <= 0
                    if st.button(f"{self.const.ICONS['previous']}", disabled=prev_disabled, key="prev_page_btn"):
                        st.session_state['post_page'] -= 1
                        st.rerun()

                with pagination_cols[1]:
                    st.markdown(f"**Page {st.session_state['post_page'] + 1} of {max_pages}** ({filtered_count} posts)")

                with pagination_cols[2]:
                    next_disabled = st.session_state['post_page'] >= max_pages - 1
                    if st.button(f"{self.const.ICONS['next']}", disabled=next_disabled, key="next_page_btn"):
                        st.session_state['post_page'] += 1
                        st.rerun()

            # Calculate slice for current page
            start_idx = st.session_state['post_page'] * st.session_state['posts_per_page']
            end_idx = min(start_idx + st.session_state['posts_per_page'], filtered_count)
            current_page_posts = filtered_posts[start_idx:end_idx]

            # Render only the current page of posts
            self._render_post_grid(current_page_posts)

        except Exception as e:
            st.error(f"Error loading post grid: {str(e)}")

    def _handle_filter_change(self):
        """Reset to first page when filter changes"""
        st.session_state['post_page'] = 0

    def _handle_page_size_change(self):
        """Reset to first page when posts per page changes"""
        st.session_state['post_page'] = 0

    def _handle_label_change(self, post_id, select_key):
        """Optimized callback for label selection that avoids unnecessary reruns"""
        selected_label = st.session_state.get(select_key, "-- Select --")
        final_label_to_save = selected_label if selected_label != "-- Select --" else ""

        if not post_id:
            st.error("Cannot save label: Post ID is missing.")
            return

        # Use a progress placeholder to show save status without triggering a rerun
        if hasattr(self.backend, 'set_label'):
            try:
                success = self.backend.set_label(post_id, final_label_to_save)
                if not success:
                    st.warning(f"Could not save label for post {post_id}. Post might not exist.")
            except Exception as e:
                st.error(f"{self.const.ICONS['error']} Error saving label: {str(e)}")
        else:
            st.error("Backend function 'set_label' not found.")

    def _render_post_grid(self, posts_to_display):
        """Renders a paginated grid of Instagram posts with minimal UI"""
        try:
            products_data = self.backend.get_products()
            # Get product titles for the dropdown - only load once per render
            product_titles = sorted([p['Title'] for p in products_data if p.get('Title')])
            custom_labels = st.session_state.get('custom_labels', [])
            all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels)))
        except Exception as e:
            st.error(f"Error loading label options: {str(e)}")
            return

        # Determine grid layout - adaptive columns based on screen size would be ideal
        num_columns = 4  # Fixed for consistency
        cols = st.columns(num_columns)

        for index, post in enumerate(posts_to_display):
            post_id = post.get('id')
            if not post_id:
                post_id_key = f"index_{index}"
            else:
                post_id_key = str(post_id)

            col_index = index % num_columns
            with cols[col_index]:
                # Use minimal styling for containers to reduce rendering overhead
                with st.container(border=True):
                    media_url = post.get('media_url')

                    # Only show essential info - thumbnail image + minimal caption
                    if media_url:
                        st.image(media_url, use_container_width=True)
                    else:
                        st.warning("No image")

                    # Truncate caption to reduce rendering overhead
                    caption = post.get('caption', 'No caption')
                    if len(caption) > 100:
                        caption = caption[:97] + "..."
                    st.caption(f"**Caption:** {caption}")

                    # Optimize label dropdown rendering
                    current_label = post.get('label', '')
                    try:
                        default_select_index = all_labels.index(current_label) if current_label else 0
                    except ValueError:
                        if current_label:
                            all_labels.append(current_label)
                            default_select_index = all_labels.index(current_label)
                        else:
                            default_select_index = 0

                    select_key = f"label_select_{post_id_key}"

                    # Use on_change to avoid unnecessary reruns
                    on_change_callback = partial(
                        self._handle_label_change,
                        post_id=post_id,
                        select_key=select_key
                    )

                    st.selectbox(
                        label="Label",
                        options=all_labels,
                        key=select_key,
                        index=default_select_index,
                        on_change=on_change_callback,
                        label_visibility="collapsed"
                    )

    def _render_stories_tab(self):
        """Streamlined stories tab with minimal UI"""
        col1, col2 = st.columns([1, 3])

        with col1:
            if st.button(f"{self.const.ICONS['update']} Update Stories", help="Fetch stories", use_container_width=True):
                with st.spinner("Fetching..."):
                    try:
                        success = self.backend.fetch_instagram_stories()
                        if success:
                            st.success(f"Stories updated!")
                        else:
                            st.error(f"Fetch failed")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col2:
            st.info("Story viewing functionality coming soon")

    def _render_fixed_responses_section(self):
        """Lightweight fixed responses section"""
        incoming_type = st.radio(
            "Response Type",
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
        try:
            responses = self.backend.get_fixed_responses(incoming=incoming_type)
            if responses:
                # Use an expandable container for each response to save vertical space
                for i, resp in enumerate(responses):
                    with st.expander(f"Response #{i+1}: {resp.get('trigger_keyword', 'Unnamed')}"):
                        self._render_response_card(resp, incoming_type)
            else:
                st.info(f"No {incoming_type.lower()} fixed responses available.")
        except RuntimeError as e:
            st.error(str(e))

    def _render_response_card(self, response, incoming_type):
        with st.container():
            updated_time = self.backend.format_updated_at(response.get("updated_at"))
            st.markdown(f"_Updated {updated_time}_")

            trigger = st.text_input(
                "Trigger",
                value=response["trigger_keyword"],
                key=f"trigger_{response['id']}"
            )

            if incoming_type == "Direct":
                self._render_direct_response(response, trigger)
            else:  # Comment type
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
            if st.button(f"{self.const.ICONS['save']} Save", key=f"save_{response['id']}", use_container_width=True):
                self._update_response(response, trigger, direct_text, None)
        with col2:
            self._render_delete_button(response["id"])

    def _render_comment_response(self, response, trigger):
        col_t1, col_t2 = st.columns(2)
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

        direct_text = None
        if direct_toggle:
            direct_text = st.text_area(
                "Direct Response",
                value=response["direct_response_text"] or "",
                key=f"direct_text_{response['id']}",
                height=100
            )

        comment_text = None
        if comment_toggle:
            comment_text = st.text_area(
                "Comment Response",
                value=response["comment_response_text"] or "",
                key=f"comment_text_{response['id']}",
                height=100
            )

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button(f"{self.const.ICONS['save']} Save", key=f"save_{response['id']}", use_container_width=True):
                self._update_response(response, trigger, direct_text, comment_text)
        with col_b2:
            self._render_delete_button(response["id"])

    def _render_delete_button(self, response_id):
        # Simple method for rendering delete button
        if st.button(f"{self.const.ICONS['delete']} Delete", key=f"delete_{response_id}", use_container_width=True):
            try:
                success = self.backend.delete_fixed_response(response_id)
                if success:
                    st.success("Response deleted successfully!")
                    st.rerun()
                else:
                    st.error("Failed to delete response.")
            except Exception as e:
                st.error(f"Error deleting response: {str(e)}")

    def _update_response(self, response, trigger, direct_text, comment_text):
        try:
            # Implementation depends on your backend
            success = self.backend.update_fixed_response(
                response["id"],
                trigger_keyword=trigger,
                direct_response_text=direct_text,
                comment_response_text=comment_text
            )

            if success:
                st.success("Response updated successfully!")
            else:
                st.error("Failed to update response.")
        except Exception as e:
            st.error(f"Error updating response: {str(e)}")

    def _render_new_response_form(self, incoming_type):
        with st.form(key=f"new_{incoming_type.lower()}_response_form"):
            trigger = st.text_input("Trigger Keyword", key="new_trigger")

            if incoming_type == "Direct":
                direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=150)
                comment_text = None
            else:  # Comment
                use_direct = st.checkbox("Include Direct Message", key="new_use_direct")
                direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=150) if use_direct else None

                use_comment = st.checkbox("Include Comment Reply", key="new_use_comment")
                comment_text = st.text_area("Comment Response Text", key="new_comment_text", height=150) if use_comment else None

            submitted = st.form_submit_button(f"{self.const.ICONS['add']} Add Response")

            if submitted:
                self._add_new_response(incoming_type, trigger, direct_text, comment_text)

    def _add_new_response(self, incoming_type, trigger, direct_text, comment_text):
        if not trigger:
            st.error("Trigger keyword is required!")
            return

        try:
            success = self.backend.add_fixed_response(
                trigger_keyword=trigger,
                incoming_type=incoming_type,
                direct_response_text=direct_text,
                comment_response_text=comment_text
            )

            if success:
                st.success("New response added successfully!")
                st.rerun()
            else:
                st.error("Failed to add new response.")

        except Exception as e:
            st.error(f"Error adding response: {str(e)}")

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
