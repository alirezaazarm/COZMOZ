import logging
import streamlit as st
from app.services.backend import Backend # Assuming this path is correct
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
        "folder": ":open_file_folder:",
        "dashboard": ":bar_chart:", # Added icon for dashboard
        "data": ":page_facing_up:", # Added icon for data
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
# --- (Keep AppStatusSection, ProductScraperSection, OpenAIManagementSection, InstagramSection as they are) ---
# Placeholder for your existing section classes:
# AppStatusSection, ProductScraperSection, OpenAIManagementSection, InstagramSection
# Ensure these classes are defined as they are in your ui.py file.
# For brevity, I'm not reproducing them here but they are essential.

class AppStatusSection(BaseSection): #
    """Handles application status settings""" #
    def render(self): 
        try:
            self._render_toggles() #
            st.write("---") #
        except RuntimeError as e: #
            st.error(f"Error managing app status: {str(e)}") #

    def _render_toggles(self): #
        """Render configuration toggles""" #
        settings = { #
            "assistant": f"{self.const.ICONS['success']} Enable Assistant", #
            "fixed_responses": f"{self.const.ICONS['success']} Enable Fixed Responses" #
        }

        for key, label in settings.items(): #
            current_status = self.backend.get_app_setting(key) #
            new_state = st.toggle(label, value=(current_status == "true"), key=f"{key}_toggle") #

            if new_state != (current_status == "true"): #
                self.backend.update_is_active(key, str(new_state).lower()) #
                status_msg = "enabled" if new_state else "disabled" #
                icon = self.const.ICONS['success'] if new_state else self.const.ICONS['error'] #
                st.success(f"{icon} {key.replace('_', ' ').title()} {status_msg} successfully!") #


class ProductScraperSection(BaseSection):
    """Handles product scraping functionality and additional info management."""
    def render(self):
        self._render_action_buttons()
        self._render_product_table_only()
        st.write("---")  # Separator between product table and additional info
        self._render_additional_info_section()
        st.write("---") # Original separator at the end of the section

    def _render_action_buttons(self):
        """Renders top action buttons like Update Products and Rebuild VS."""
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"{self.const.ICONS['update']} Update Products",
                        help="Add new products only", use_container_width=True):
                self._handle_scraping_action(self.backend.update_products) # Note: pass function reference

        with col2:
            if st.button(f"{self.const.ICONS['brain']} Rebuild VS",  # Changed icon
                        key="update_vs_btn_top",
                        help="Rebuild Vector Store for Additional Info. This may take time.",
                        use_container_width=True):
                try:
                    with st.spinner("Rebuilding Additional Info Vector Store... Please wait."):
                        success = self.backend.rebuild_files_and_vs()
                        if success:
                            st.success(f"{self.const.ICONS['success']} Additional info AI data rebuilt successfully!")
                        else:
                            st.error(f"{self.const.ICONS['error']} Failed to rebuild additional info AI data.")
                except Exception as e:
                    st.error(f"{self.const.ICONS['error']} Error during rebuild: {str(e)}")

    def _handle_scraping_action(self, action_function): # Renamed parameter for clarity
        """Handles the execution of scraping-related actions with spinner and messages."""
        try:
            # Assuming MESSAGES["scraping_start"] is generic enough, or use a specific one
            with st.spinner(self.const.MESSAGES.get("update_start", "Processing...")):
                action_function() # Call the passed function
                st.success(f"{self.const.ICONS['success']} Operation completed!")
                st.rerun()
        except Exception as e:
            logging.error(f"Scraping action failed: {e}", exc_info=True)
            st.error(f"{self.const.ICONS['error']} Operation failed: {str(e)}")

    def _render_product_table_only(self):
        """Renders only the product table."""
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
                st.info("No products found. Click 'Update Products' to get started or check your data source.")
        except Exception as e:
            logging.error(f"Failed to load products: {e}", exc_info=True)
            st.error(f"Failed to load products: {str(e)}")

    def _render_additional_info_section(self):
        """Renders the 'Additional info' section with tabs for editing and adding."""
        st.subheader(f"{self.const.ICONS['fixed_response']} Additional info")

        edit_tab, add_tab = st.tabs(["Edit Existing", "Add New"])

        with add_tab:
            with st.form(key="add_additionalinfo_form"):
                title = st.text_input("Title", key="app_setting_title",
                                      placeholder="Enter a descriptive title for the info")
                text = st.text_area("Text", key="app_setting_text", height=150, # Adjusted height
                                   placeholder="Enter your text content here")
                submit = st.form_submit_button(f"{self.const.ICONS['save']} Save Info", use_container_width=True)

            if submit:
                if not title.strip():
                    st.error("Title is required.")
                elif not text.strip():
                    st.error("Text content is required.")
                else:
                    with st.spinner("Saving..."):
                        success = self.backend.add_additionalinfo(title.strip(), text.strip())
                        if success:
                            st.success(f"'{title.strip()}' saved successfully!")
                            # Consider st.rerun() if the list on the edit tab should update immediately
                        else:
                            st.error(f"Failed to save '{title.strip()}'.")
        
        with edit_tab:
            app_settings = self.backend.get_additionalinfo()
            if not app_settings:
                st.info("No saved additional info found. Use the 'Add New' tab to create some.")
            else:
                if 'editing_app_setting_key' not in st.session_state:
                    st.session_state['editing_app_setting_key'] = None
                
                for setting in app_settings:
                    key = setting["key"]
                    value = setting["value"]
                    
                    if st.session_state.get('editing_app_setting_key') == key:
                        # Editing mode for this item
                        with st.container(border=True):
                            with st.form(key=f"edit_app_setting_form_{key}"):
                                st.subheader(f"Editing: {key}")
                                new_value = st.text_area("Content", value=value, key=f"edit_value_{key}",
                                                          height=200, label_visibility="collapsed")
                                
                                form_cols = st.columns(2)
                                with form_cols[0]:
                                    update_btn = st.form_submit_button(f"{self.const.ICONS['save']} Update",
                                                                    use_container_width=True)
                                with form_cols[1]:
                                    cancel_btn = st.form_submit_button("Cancel", type="secondary",
                                                                     use_container_width=True)
                            
                            if update_btn:
                                if not new_value.strip():
                                    st.error("Text content cannot be empty.")
                                else:
                                    with st.spinner(f"Updating '{key}'..."):
                                        success = self.backend.add_additionalinfo(key, new_value.strip()) # Assuming add_additionalinfo can also update
                                        if success:
                                            st.success(f"'{key}' updated successfully!")
                                            st.session_state['editing_app_setting_key'] = None
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to update '{key}'.")
                            elif cancel_btn:
                                st.session_state['editing_app_setting_key'] = None
                                st.rerun()
                    else:
                        # Display mode for this item (not being edited)
                        item_cols = st.columns([0.7, 0.15, 0.15]) # Key | Edit | Delete
                        with item_cols[0]:
                            st.markdown(f"**{key}**")
                            # Optionally, show a preview of the text if it's very short, or word/char count
                            # st.caption(f"{len(value.split())} words" if value else "Empty")

                        with item_cols[1]:
                            if st.button("Edit", key=f"edit_btn_{key}", use_container_width=True, type="secondary"):
                                st.session_state['editing_app_setting_key'] = key
                                st.rerun()
                        with item_cols[2]:
                            if st.button(f"{self.const.ICONS['delete']}", key=f"remove_btn_{key}", use_container_width=True, help=f"Delete '{key}'"):
                                with st.spinner(f"Deleting '{key}'..."):
                                    success = self.backend.delete_additionalinfo(key)
                                    if success:
                                        st.success(f"'{key}' deleted successfully!")
                                        if st.session_state.get('editing_app_setting_key') == key: # Clear editing state if deleted item was being edited
                                            st.session_state['editing_app_setting_key'] = None
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to delete '{key}'.")
                        st.divider()

class OpenAIManagementSection(BaseSection): #
    """Handles OpenAI processing with improved UX (all calls via Backend).""" #
    def render(self): #

        vs_id = self.backend.get_vs_id() #
        if vs_id is None: #
            st.warning("No vector store currently available. Please connect to a vector store before testing the assistant.") #

        settings_tab, chat_tab = st.tabs([ #
            f"{self.const.ICONS['brain']} Assistant Settings", #
            f"{self.const.ICONS['chat']} Test Assistant" #
        ]) #

        with settings_tab: #
            self._render_settings_section() #

        with chat_tab: #
            if vs_id is not None: #
                self._render_chat_testing_section() #
            else: #
                st.error("You need to connect to a vector store first before testing the assistant") #

        st.markdown("---") #

    def _render_settings_section(self): #
        current_instructions = self.backend.get_assistant_instructions() #
        current_temperature = self.backend.get_assistant_temperature() #
        current_top_p = self.backend.get_assistant_top_p() #

        new_instructions = st.text_area( #
            "Assistant Instructions", #
            value=current_instructions if current_instructions else "Enter instructions...", #
            height=600, #
            help="How the assistant should behave", #
            label_visibility="collapsed" #
        ) #

        col1, col2, col3 = st.columns([4, 2, 4]) #

        with col1: #
            new_temperature = st.slider( #
                "Temperature", #
                min_value=0.0, #
                max_value=2.0, #
                value=float(current_temperature), #
                step=0.01, #
                help="Randomness (0=strict, 2=creative)" #
            ) #

        with col2: #
            st.write("") # 
            update_btn = st.button( #
                f"{self.const.ICONS['update']} Update All", #
                use_container_width=True, #
                help="Save all settings" #
            ) #
            st.write("") # 

        with col3: #
            new_top_p = st.slider( #
                "Top-P", #
                min_value=0.0, #
                max_value=1.0, #
                value=float(current_top_p), #
                step=0.01, #
                help="Focus (1=broad, 0=narrow)" #
            ) #

        if update_btn: #
            with st.spinner("Saving..."): #
                results = { #
                    'instructions': self.backend.update_assistant_instructions(new_instructions), #
                    'temperature': self.backend.update_assistant_temperature(new_temperature), #
                    'top_p': self.backend.update_assistant_top_p(new_top_p) #
                } #

                if all(r['success'] for r in results.values()): #
                    st.success(f"{self.const.ICONS['success']} All settings saved!") #
                else: #
                    errors = [ #
                        f"{name}: {result['message']}" #
                        for name, result in results.items() #
                        if not result['success'] #
                    ] #
                    st.error(f"{self.const.ICONS['error']} Issues: {', '.join(errors)}") #

    def _render_chat_testing_section(self): #
        st.subheader("Test your assistant") #

        if 'thread_id' not in st.session_state: #
            try: #
                thread_id = self.backend.create_chat_thread() #
                st.session_state['thread_id'] = thread_id #
                st.session_state['messages'] = [] #
                st.session_state['user_message_sent'] = True #
                st.session_state['processed_file_ids'] = set() #
            except Exception as e: #
                st.error(f"Failed to create thread: {str(e)}") #
                return #
        if 'processed_file_ids' not in st.session_state: #
             st.session_state['processed_file_ids'] = set() #


        chat_container = st.container() #
        chat_container.height = 400 #

        input_container = st.container() #

        new_user_input = None #

        with input_container: #
            uploaded_file = st.file_uploader( #
                "Upload an image (optional)", #
                type=None, #
                key="chat_image_uploader" #
            ) #

            if uploaded_file is not None: #
                if uploaded_file.file_id not in st.session_state['processed_file_ids']: #
                    with st.spinner("Analyzing image..."): #
                        try: #
                            st.session_state['processed_file_ids'].add(uploaded_file.file_id) #

                            if uploaded_file.type.startswith('image/'): #
                                image_bytes = uploaded_file.getvalue() #
                                analysis_result = self.backend.process_uploaded_image(image_bytes) #
                                new_user_input = f"Analysis of uploaded image: {analysis_result}" #

                                with chat_container: #
                                    with st.chat_message("user"): #
                                        st.image(image_bytes, width=150) #
                                        st.write(new_user_input) #
                            else: #
                                st.error("Please upload an image file (JPG, PNG, etc.)") #
                                new_user_input = None #

                        except Exception as e: #
                            st.error(f"Error handling image upload: {str(e)}") #
                            new_user_input = None #


            user_text_input = st.chat_input("Type your message here...") #

            if user_text_input: #
                new_user_input = user_text_input #


        if new_user_input: #
            st.session_state['messages'].append({"role": "user", "content": new_user_input}) #
            st.session_state['user_message_sent'] = False #

        with chat_container: #
            for message in st.session_state.get('messages', []): #
                 with st.chat_message(message["role"]): #
                     st.write(message["content"]) #


        if not st.session_state.get('user_message_sent', True): #
            last_message = st.session_state['messages'][-1] if st.session_state['messages'] else None #

            if last_message and last_message["role"] == "user": #
                with st.spinner("Assistant is thinking..."): #
                    try: #
                        response = self.backend.send_message_to_thread( #
                            st.session_state['thread_id'], #
                            last_message["content"] #
                        ) #
                        st.session_state['messages'].append({"role": "assistant", "content": response}) #
                        st.session_state['user_message_sent'] = True #

                        st.rerun() #

                    except Exception as e: #
                        st.error(f"Error getting response: {str(e)}") #
                        st.session_state['user_message_sent'] = True #

class InstagramSection(BaseSection): #
    """Handles Instagram-related functionality including posts, stories, and fixed responses.""" #
    def __init__(self, backend): #
        super().__init__(backend) #
        if 'custom_labels' not in st.session_state: #
            st.session_state['custom_labels'] = [] #
        if 'post_page' not in st.session_state: #
            st.session_state['post_page'] = 0 #
        if 'posts_per_page' not in st.session_state: #
            st.session_state['posts_per_page'] = 8 #
        if 'post_filter' not in st.session_state: #
            st.session_state['post_filter'] = "All" #

    def render(self): 

        posts_tab, stories_tab, fixed_responses_tab = st.tabs([ #
            f"{self.const.ICONS['post']} Posts", #
            f"{self.const.ICONS['story']} Stories", #
            f"{self.const.ICONS['fixed_response']} Fixed Responses" #
        ]) #

        with posts_tab: #
            self._render_posts_tab() #

        with stories_tab: #
            self._render_stories_tab() #

        with fixed_responses_tab: #
            self._render_fixed_responses_section() #

        st.write("---") #

    def _render_posts_tab(self): #
        """Renders the section for managing and viewing Instagram posts with optimized performance.""" #
        col1, col2, col3 = st.columns([1, 1, 2]) #

        with col1: #
            if st.button(f"{self.const.ICONS['update']} Update Posts", help="Fetch and update Instagram posts", use_container_width=True): #
                with st.spinner("Fetching posts..."): #
                    try: #
                        success = self.backend.fetch_instagram_posts() #
                        if success: #
                            st.success(f"{self.const.ICONS['success']} Posts updated!") #
                            st.rerun() #
                        else: #
                            st.error(f"{self.const.ICONS['error']} Fetch failed") #
                    except Exception as e: #
                        st.error(f"Error: {str(e)}") #

        with col2: #
            if st.button(f"{self.const.ICONS['model']} AI Label", help="Auto-label posts with AI", use_container_width=True): #
                with st.spinner("AI labeling..."): #
                    try: #
                        if hasattr(self.backend, 'set_labels_by_model'): #
                            result = self.backend.set_labels_by_model() #
                            if result and result.get('success'): #
                                st.success(f"Labels updated!") #
                                st.rerun() #
                            else: #
                                st.error(f"Labeling failed") #
                        else: #
                            st.error(f"Function not found") #
                    except Exception as e: #
                        st.error(f"Error: {str(e)}") #

        with col3: #
            col3a, col3b = st.columns([3, 1]) #
            with col3a: #
                new_label = st.text_input( #
                    "New label", #
                    key="new_custom_label_input", #
                    placeholder="Add custom label", #
                    label_visibility="collapsed" #
                ) #
            with col3b: #
                if st.button(f"{self.const.ICONS['add']}", key="add_custom_label_button", help="Add new label", use_container_width=True): #
                    new_label_stripped = new_label.strip() #
                    if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']: #
                        st.session_state['custom_labels'].append(new_label_stripped) #
                        st.success(f"Added '{new_label_stripped}'") #
                        st.rerun() #
                    elif not new_label_stripped: #
                        st.warning("Label cannot be empty") #
                    else: #
                        st.warning(f"Label already exists") #

        try: #
            posts = self.backend.get_posts() #
            total_posts = len(posts) #

            if not posts: #
                st.info("No posts found. Click 'Update Posts' to fetch them.") #
                return #

            all_labels = sorted(list(set(post.get('label', '') for post in posts if post.get('label', '')))) #
            filter_options = ["All"] + all_labels #

            col_filter, col_per_page, col_pagination = st.columns([2, 1, 2]) #

            with col_filter: #
                selected_filter = st.selectbox( #
                    "Filter by label", #
                    options=filter_options, #
                    index=filter_options.index(st.session_state['post_filter']) if st.session_state['post_filter'] in filter_options else 0, #
                    key="post_filter_selector", #
                    on_change=lambda: self._handle_filter_change() #
                ) #
                st.session_state['post_filter'] = selected_filter #

            with col_per_page: #
                st.selectbox( #
                    "Posts per page", #
                    options=[4, 8, 12, 16], #
                    index=[4, 8, 12, 16].index(st.session_state['posts_per_page']) if st.session_state['posts_per_page'] in [4, 8, 12, 16] else 1, #
                    key="posts_per_page_selector", #
                    on_change=self._handle_page_size_change #
                ) #

            if st.session_state['post_filter'] != "All": #
                filtered_posts = [post for post in posts if post.get('label', '') == st.session_state['post_filter']] #
            else: #
                filtered_posts = posts #

            filtered_count = len(filtered_posts) #
            max_pages = (filtered_count - 1) // st.session_state['posts_per_page'] + 1 if filtered_count > 0 else 1 #

            if st.session_state['post_page'] >= max_pages: #
                st.session_state['post_page'] = max_pages - 1 #

            start_idx = st.session_state['post_page'] * st.session_state['posts_per_page'] #
            end_idx = min(start_idx + st.session_state['posts_per_page'], filtered_count) #
            current_page_posts = filtered_posts[start_idx:end_idx] #

            self._render_post_grid(current_page_posts) #

            if filtered_count > 0: #
                st.write("") # 
                
                row_cols = st.columns([1] + [1] * min(max_pages, 10) + [1]) #
                
                with row_cols[0]: #
                    prev_disabled = st.session_state['post_page'] <= 0 #
                    if st.button(f"{self.const.ICONS['previous']}", disabled=prev_disabled, key="prev_page_btn_bottom"): #
                        st.session_state['post_page'] -= 1 #
                        st.rerun() #
                
                for i in range(min(max_pages, 10)): #
                    page_num = i + 1 #
                    with row_cols[i + 1]: #
                        if i == st.session_state['post_page']: #
                            st.button(f"{page_num}", key=f"page_btn_{i}", disabled=True) #
                        else: #
                            if st.button(f"{page_num}", key=f"page_btn_{i}"): #
                                st.session_state['post_page'] = i #
                                st.rerun() #
                
                with row_cols[-1]: #
                    next_disabled = st.session_state['post_page'] >= max_pages - 1 #
                    if st.button(f"{self.const.ICONS['next']}", disabled=next_disabled, key="next_page_btn_bottom"): #
                        st.session_state['post_page'] += 1 #
                        st.rerun() #
                
                st.caption(f"Total: {filtered_count} posts") #

        except Exception as e: #
            st.error(f"Error loading post grid: {str(e)}") #

    def _handle_filter_change(self): #
        """Reset to first page when filter changes""" #
        st.session_state['post_page'] = 0 #

    def _handle_page_size_change(self): #
        """Reset to first page when posts per page changes""" #
        st.session_state['posts_per_page'] = st.session_state['posts_per_page_selector'] #
        st.session_state['post_page'] = 0 #

    def _handle_label_change(self, post_id, select_key): #
        """Optimized callback for label selection that avoids unnecessary reruns""" #
        selected_label = st.session_state.get(select_key, "-- Select --") #
        final_label_to_save = selected_label if selected_label != "-- Select --" else "" #

        if not post_id: #
            st.error("Cannot save label: Post ID is missing.") #
            return #

        if hasattr(self.backend, 'set_label'): #
            try: #
                success = self.backend.set_label(post_id, final_label_to_save) #
                if not success: #
                    st.warning(f"Could not save label for post {post_id}. Post might not exist.") #
            except Exception as e: #
                st.error(f"{self.const.ICONS['error']} Error saving label: {str(e)}") #
        else: #
            st.error("Backend function 'set_label' not found.") #

    def _render_post_grid(self, posts_to_display): #
        """Renders a paginated grid of Instagram posts with minimal UI""" #
        try: #
            products_data = self.backend.get_products() #
            product_titles = sorted([p['Title'] for p in products_data if p.get('Title')]) #
            custom_labels = st.session_state.get('custom_labels', []) #
            all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels))) #
        except Exception as e: #
            st.error(f"Error loading label options: {str(e)}") #
            return #

        num_columns = 4 #
        cols = st.columns(num_columns) #

        for index, post in enumerate(posts_to_display): #
            post_id = post.get('id') #
            if not post_id: #
                post_id_key = f"index_{index}" #
            else: #
                post_id_key = str(post_id) #

            col_index = index % num_columns #
            with cols[col_index]: #
                with st.container(border=True): #
                    media_url = post.get('media_url') #

                    if media_url: #
                        st.image(media_url, use_container_width=True) #
                    else: #
                        st.warning("No image") #

                    caption = post.get('caption', 'No caption') #
                    if len(caption) > 100: #
                        caption = caption[:97] + "..." #
                    st.caption(f"**Caption:** {caption}") #

                    current_label = post.get('label', '') #
                    try: #
                        default_select_index = all_labels.index(current_label) if current_label else 0 #
                    except ValueError: #
                        if current_label: #
                            all_labels.append(current_label) #
                            default_select_index = all_labels.index(current_label) #
                        else: #
                            default_select_index = 0 #

                    select_key = f"label_select_{post_id_key}" #

                    on_change_callback = partial( #
                        self._handle_label_change, #
                        post_id=post_id, #
                        select_key=select_key #
                    ) #

                    st.selectbox( #
                        label="Label", #
                        options=all_labels, #
                        key=select_key, #
                        index=default_select_index, #
                        on_change=on_change_callback, #
                        label_visibility="collapsed" #
                    ) #

    def _render_stories_tab(self): #
        """Streamlined stories tab with minimal UI""" #
        col1, col2 = st.columns([1, 3]) #

        with col1: #
            if st.button(f"{self.const.ICONS['update']} Update Stories", help="Fetch stories", use_container_width=True): #
                with st.spinner("Fetching..."): #
                    try: #
                        success = self.backend.fetch_instagram_stories() #
                        if success: #
                            st.success(f"Stories updated!") #
                        else: #
                            st.error(f"Fetch failed") #
                    except Exception as e: #
                        st.error(f"Error: {str(e)}") #

        with col2: #
            st.info("Story viewing functionality coming soon") #

    def _render_fixed_responses_section(self): #
        """Lightweight fixed responses section""" #
        incoming_type = st.radio( #
            "Response Type", #
            options=["Direct", "Comment"], #
            index=0, #
            horizontal=True, #
            key="incoming_type" #
        ) #

        existing_tab, add_new_tab = st.tabs(["Existing", "Add New"]) #

        with existing_tab: #
            self._render_existing_responses(incoming_type) #

        with add_new_tab: #
            self._render_new_response_form(incoming_type) #

    def _render_existing_responses(self, incoming_type): #
        try: #
            responses = self.backend.get_fixed_responses(incoming=incoming_type) #
            if responses: #
                for i, resp in enumerate(responses): #
                    with st.expander(f"Response {i+1}: {resp.get('trigger_keyword', 'Unnamed')}"): #
                        self._render_response_card(resp, incoming_type) #
            else: #
                st.info(f"No {incoming_type.lower()} fixed responses available.") #
        except RuntimeError as e: #
            st.error(str(e)) #

    def _render_response_card(self, response, incoming_type): #
        with st.container(): #
            updated_time = self.backend.format_updated_at(response.get("updated_at")) #
            st.markdown(f"_Updated {updated_time}_") #

            trigger = st.text_input( #
                "Trigger", #
                value=response["trigger_keyword"], #
                key=f"trigger_{response['id']}" #
            ) #

            if incoming_type == "Direct": #
                self._render_direct_response(response, trigger) #
            else: #
                self._render_comment_response(response, trigger) #

    def _render_direct_response(self, response, trigger): #
        direct_text = st.text_area( #
            "Direct Response Text", #
            value=response["direct_response_text"] or "", #
            key=f"direct_text_{response['id']}", #
            height=100 #
        ) #

        col1, col2 = st.columns([1, 1]) #
        with col1: #
            if st.button(f"{self.const.ICONS['save']} Save", key=f"save_{response['id']}", use_container_width=True): #
                self._update_response(response, trigger, direct_text, None) #
        with col2: #
            self._render_delete_button(response["id"]) #

    def _render_comment_response(self, response, trigger): #
        col_t1, col_t2 = st.columns(2) #
        with col_t1: #
            direct_toggle = st.toggle( #
                "Direct", #
                value=bool(response["direct_response_text"]), #
                key=f"direct_toggle_{response['id']}" #
            ) #
        with col_t2: #
            comment_toggle = st.toggle( #
                "Comment", #
                value=bool(response["comment_response_text"]), #
                key=f"comment_toggle_{response['id']}" #
            ) #

        direct_text = None #
        if direct_toggle: #
            direct_text = st.text_area( #
                "Direct Response", #
                value=response["direct_response_text"] or "", #
                key=f"direct_text_{response['id']}", #
                height=100 #
            ) #

        comment_text = None #
        if comment_toggle: #
            comment_text = st.text_area( #
                "Comment Response", #
                value=response["comment_response_text"] or "", #
                key=f"comment_text_{response['id']}", #
                height=100 #
            ) #

        col_b1, col_b2 = st.columns([1, 1]) #
        with col_b1: #
            if st.button(f"{self.const.ICONS['save']} Save", key=f"save_{response['id']}", use_container_width=True): #
                self._update_response(response, trigger, direct_text, comment_text) #
        with col_b2: #
            self._render_delete_button(response["id"]) #

    def _render_delete_button(self, response_id): #
        if st.button(f"{self.const.ICONS['delete']} Delete", key=f"delete_{response_id}", use_container_width=True): #
            try: #
                success = self.backend.delete_fixed_response(response_id) #
                if success: #
                    st.success("Response deleted successfully!") #
                    st.rerun() #
                else: #
                    st.error("Failed to delete response.") #
            except Exception as e: #
                st.error(f"Error deleting response: {str(e)}") #

    def _update_response(self, response, trigger, direct_text, comment_text): #
        try: #
            success = self.backend.update_fixed_response( #
                response["id"], #
                trigger_keyword=trigger, #
                direct_response_text=direct_text, #
                comment_response_text=comment_text #
            ) #

            if success: #
                st.success("Response updated successfully!") #
            else: #
                st.error("Failed to update response.") #
        except Exception as e: #
            st.error(f"Error updating response: {str(e)}") #

    def _render_new_response_form(self, incoming_type): #
        with st.form(key=f"new_{incoming_type.lower()}_response_form"): #
            trigger = st.text_input("Trigger Keyword", key="new_trigger") #

            if incoming_type == "Direct": #
                direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=150) #
                comment_text = None #
            else: #
                use_direct = st.checkbox("Include Direct Message", key="new_use_direct") #
                direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=150) if use_direct else None #

                use_comment = st.checkbox("Include Comment Reply", key="new_use_comment") #
                comment_text = st.text_area("Comment Response Text", key="new_comment_text", height=150) if use_comment else None #

            submitted = st.form_submit_button(f"{self.const.ICONS['add']} Add Response") #

            if submitted: #
                self._add_new_response(incoming_type, trigger, direct_text, comment_text) #

    def _add_new_response(self, incoming_type, trigger, direct_text, comment_text): #
        if not trigger: #
            st.error("Trigger keyword is required!") #
            return #

        try: #
            success = self.backend.add_fixed_response( #
                trigger_keyword=trigger, #
                incoming_type=incoming_type, #
                direct_response_text=direct_text, #
                comment_response_text=comment_text #
            ) #

            if success: #
                st.success("New response added successfully!") #
                st.rerun() #
            else: #
                st.error("Failed to add new response.") #

        except Exception as e: #
            st.error(f"Error adding response: {str(e)}") #

#===============================================================================================================================
class AdminUI:
    """Main application container"""
    def __init__(self):
        st.set_page_config(layout="wide") #
        try:
            self.backend = Backend() #
        except NameError: #
            st.error("Backend class definition not found. Please ensure it's defined or imported.") #
            # Define a DummyBackend to allow the UI to run for demonstration if Backend is missing
            class DummyBackend: #
                def __getattr__(self, name): #
                    def method(*args, **kwargs): #
                        print(f"DummyBackend: Method '{name}' called with args={args}, kwargs={kwargs}") #
                        if name == 'get_app_setting': return "true" #
                        if name == 'get_labels': return {} #
                        if name == 'get_posts': return [] #
                        if name == 'get_products': return [] #
                        if name == 'get_additionalinfo': return [] #
                        if name == 'get_vs_id': return "dummy_vs_id" #
                        if name == 'get_assistant_instructions': return "Dummy instructions" #
                        if name == 'get_assistant_temperature': return 0.7 #
                        if name == 'get_assistant_top_p': return 1.0 #
                        if name == 'create_chat_thread': return "dummy_thread_id" #
                        if name == 'get_fixed_responses': return [] #
                        if name == 'format_updated_at': return "recently" #
                        # Add other dummy methods as needed by your sections
                        return None #
                    return method #
            self.backend = DummyBackend() #

        # Map section titles to their respective classes
        self.section_mapping = {
            "Admin Dashboard": AppStatusSection(self.backend),
            "Data": ProductScraperSection(self.backend),
            "OpenAI Management": OpenAIManagementSection(self.backend),
            "Instagram Management": InstagramSection(self.backend)
        }
        # Initialize session state for the selected page if it doesn't exist
        if 'selected_page' not in st.session_state:
            st.session_state.selected_page = "Admin Dashboard" # Default page

    def render(self):
        """Render all application sections based on sidebar navigation"""
        st.sidebar.title("Navigation")
        
        # Create radio buttons in the sidebar for section selection
        # The key for st.radio will automatically update st.session_state.selected_page
        st.session_state.selected_page = st.sidebar.radio(
            "Go to",
            options=list(self.section_mapping.keys()),
            key="navigation_radio" # Use a distinct key if 'selected_page' is used elsewhere for st.radio
                                   # Or, rely on st.session_state.selected_page directly if not using st.radio's key for state
                                   # If using st.radio's key, it will be st.session_state.navigation_radio
                                   # For simplicity, let's ensure selected_page is updated by the radio
        )

        # Retrieve the selected section object
        selected_section_title = st.session_state.selected_page
        section_to_render = self.section_mapping.get(selected_section_title)

        # Render the selected section
        if section_to_render:
            # Set the main page title based on the selected section (optional)
            # st.title(selected_section_title) # You can remove this if section.render() sets its own header
            section_to_render.render()
        else:
            st.error("Page not found. Please select a section from the sidebar.")

if __name__ == "__main__":
    app = AdminUI() #
    app.render() #