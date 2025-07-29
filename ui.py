import logging
import streamlit as st
from app.services.backend import Backend # Assuming this path is correct
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone, timedelta

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
        "paper_and_pen": ":memo:",
        "previous": ":arrow_left:",
        "next": ":arrow_right:",
        "label": ":label:",
        "save": ":floppy_disk:",
        "model": ":brain:",
        "folder": ":open_file_folder:",
        "dashboard": ":bar_chart:", # Added icon for dashboard
        "data": ":page_facing_up:", # Added icon for data
        "login": ":key:", # Added icon for login
        "logout": ":door:", # Added icon for logout
        "user": ":bust_in_silhouette:", # Added icon for user management
        "magic": ":magic_wand:", # Added icon for auto-labeling
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
class AppStatusSection(BaseSection): #
    """Handles application status settings and analytics""" #
    def render(self):
        try:
            self._render_toggles() #
            st.write("---") #
            self._render_analytics_dashboard() #
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
            # Normalize current_status to boolean
            current_status_bool = bool(current_status)
            if isinstance(current_status, str):
                current_status_bool = current_status.lower() == "true"
            new_state = st.toggle(label, value=current_status_bool, key=f"{key}_toggle") #
            if new_state != current_status_bool: #
                self.backend.update_is_active(key, new_state) #
                status_msg = "enabled" if new_state else "disabled" #
                icon = self.const.ICONS['success'] if new_state else self.const.ICONS['error'] #
                st.success(f"{icon} {key.replace('_', ' ').title()} {status_msg} successfully!") #

    def _render_analytics_dashboard(self): #
        """Render analytics dashboard with charts and statistics""" #
        st.subheader(f"{self.const.ICONS['dashboard']} Analytics Dashboard") #
        
        # Create tabs for different analytics views
        message_tab, user_tab = st.tabs([
            f"{self.const.ICONS['chat']} Message Analytics",
            f"{self.const.ICONS['user']} User Statistics"
        ])
        
        with message_tab:
            self._render_message_analytics()
            
        with user_tab:
            self._render_user_statistics()

    def _render_message_analytics(self): #
        """Render message analytics with histogram charts""" #
        try:
            # Time frame and date range selectors
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
            
            with col1:
                time_frame = st.selectbox(
                    "Time Frame",
                    options=["daily", "hourly"],
                    index=0,
                    key="message_time_frame"
                )
            
            with col2:
                # Default to last 7 days
                default_start = datetime.now(timezone.utc) - timedelta(days=7)
                start_date = st.date_input(
                    "Start Date",
                    value=default_start.date(),
                    key="message_start_date"
                )
            
            with col3:
                start_time = st.time_input(
                    "Start Time",
                    value=default_start.time(),
                    key="message_start_time"
                )
            
            with col4:
                # Default to now
                default_end = datetime.now(timezone.utc)
                end_date = st.date_input(
                    "End Date",
                    value=default_end.date(),
                    key="message_end_date"
                )
                
                end_time = st.time_input(
                    "End Time",
                    value=default_end.time(),
                    key="message_end_time"
                )
            
            with col5:
                if st.button(f"{self.const.ICONS['update']} Refresh Data", key="refresh_message_data"):
                    st.rerun()
            
            # Combine date and time
            start_datetime = datetime.combine(start_date, start_time).replace(tzinfo=timezone.utc)
            end_datetime = datetime.combine(end_date, end_time).replace(tzinfo=timezone.utc)
            
            # Validate date range
            if start_datetime >= end_datetime:
                st.error("Start date/time must be before end date/time.")
                return
            
            # Fetch message statistics using the new timeframe method
            message_stats = self.backend.get_message_statistics_by_role_within_timeframe(time_frame, start_datetime, end_datetime)
            
            if not message_stats:
                st.info("No message data available for the selected time period.")
                return
            
            # Prepare data for plotting
            # Convert statistics to DataFrame
            data_rows = []
            for date_str, roles in message_stats.items():
                for role, count in roles.items():
                    data_rows.append({
                        'Date': date_str,
                        'Role': role,
                        'Count': count
                    })
            
            if not data_rows:
                st.info("No message data to display.")
                return
                
            df = pd.DataFrame(data_rows)
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date')
            
            # Create histogram chart
            date_range_str = f"{start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%Y-%m-%d %H:%M')} UTC"
            fig = px.bar(
                df, 
                x='Date', 
                y='Count', 
                color='Role',
                title=f'Direct Messages by Role ({time_frame.title()} View - {date_range_str})',
                labels={'Count': 'Number of Messages', 'Date': 'Time Period'},
                color_discrete_map={
                    'user': '#1f77b4',
                    'assistant': '#ff7f0e', 
                    'admin': '#2ca02c',
                    'fixed_response': '#d62728'
                }
            )
            
            fig.update_layout(
                xaxis_title="Time Period",
                yaxis_title="Number of Messages",
                legend_title="Message Role",
                height=500,
                showlegend=True
            )
            
            # Format x-axis based on time frame
            if time_frame == "hourly":
                fig.update_xaxes(tickformat="%Y-%m-%d %H:%M")
            else:
                fig.update_xaxes(tickformat="%Y-%m-%d")
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Summary statistics
            st.subheader("Summary Statistics")
            
            # Calculate totals by role
            role_totals = df.groupby('Role')['Count'].sum().sort_values(ascending=False)
            
            cols = st.columns(len(role_totals))
            for i, (role, total) in enumerate(role_totals.items()):
                with cols[i]:
                    st.metric(
                        label=f"{role.replace('_', ' ').title()} Messages",
                        value=f"{total:,}"
                    )
            
            # Show raw data table
            with st.expander("View Raw Data"):
                st.dataframe(df, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error rendering message analytics: {str(e)}")

    def _render_user_statistics(self): #
        """Render user statistics and status counts""" #
        try:
            # Time window selector
            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
            
            with col1:
                # Default to last 7 days
                default_start = datetime.now(timezone.utc) - timedelta(days=7)
                start_date = st.date_input(
                    "Start Date",
                    value=default_start.date(),
                    key="user_stats_start_date"
                )
            
            with col2:
                start_time = st.time_input(
                    "Start Time",
                    value=default_start.time(),
                    key="user_stats_start_time"
                )
            
            with col3:
                # Default to now
                default_end = datetime.now(timezone.utc)
                end_date = st.date_input(
                    "End Date",
                    value=default_end.date(),
                    key="user_stats_end_date"
                )
            
            with col4:
                end_time = st.time_input(
                    "End Time",
                    value=default_end.time(),
                    key="user_stats_end_time"
                )
            
            # Combine date and time
            start_datetime = datetime.combine(start_date, start_time).replace(tzinfo=timezone.utc)
            end_datetime = datetime.combine(end_date, end_time).replace(tzinfo=timezone.utc)
            
            # Validate date range
            if start_datetime >= end_datetime:
                st.error("Start date/time must be before end date/time.")
                return
            
            # Refresh button and time window toggle
            col1, col2, col3 = st.columns([1, 1, 4])
            with col1:
                if st.button(f"{self.const.ICONS['update']} Refresh", key="refresh_user_stats"):
                    st.rerun()
            
            with col2:
                use_time_window = st.checkbox(
                    "Use Time Window",
                    value=True,
                    key="use_time_window",
                    help="Filter users by their last update time within the selected window"
                )
            
            # Fetch user statistics based on time window selection
            if use_time_window:
                status_counts = self.backend.get_user_status_counts_within_timeframe(start_datetime, end_datetime)
                total_users = self.backend.get_total_users_count_within_timeframe(start_datetime, end_datetime)
                time_info = f"({start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%Y-%m-%d %H:%M')} UTC)"
            else:
                status_counts = self.backend.get_user_status_counts()
                total_users = self.backend.get_total_users_count()
                time_info = "(All time)"
            
            # Display total users with time info
            st.metric(
                label=f"Total Users {time_info}",
                value=f"{total_users:,}"
            )
            
            if not status_counts:
                st.info("No user status data available for the selected time period.")
                return
            
            # Filter out SCRAPED status
            filtered_status_counts = {
                status: count for status, count in status_counts.items() 
                if status.upper() != 'SCRAPED'
            }
            
            if not filtered_status_counts:
                st.info("No user status data available (excluding SCRAPED users) for the selected time period.")
                return
            
            # Create two columns for charts and metrics
            chart_col, metrics_col = st.columns([2, 1])
            
            with chart_col:
                # Create pie chart for user status distribution
                # Prepare data for pie chart (excluding SCRAPED)
                status_df = pd.DataFrame([
                    {'Status': status, 'Count': count} 
                    for status, count in filtered_status_counts.items()
                ])
                
                fig = px.pie(
                    status_df,
                    values='Count',
                    names='Status',
                    title=f'User Status Distribution {time_info}',
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                
                # Show only percentages, no labels
                fig.update_traces(textposition='inside', textinfo='percent')
                fig.update_layout(height=400)
                
                st.plotly_chart(fig, use_container_width=True)
            
            with metrics_col:
                st.subheader("Status Breakdown")
                
                # Sort statuses by count (descending) - excluding SCRAPED
                sorted_statuses = sorted(filtered_status_counts.items(), key=lambda x: x[1], reverse=True)
                
                for status, count in sorted_statuses:
                    # Format status name for display
                    display_status = status.replace('_', ' ').title()
                    
                    # Remove percentage display as requested
                    st.metric(
                        label=display_status,
                        value=f"{count:,}"
                    )
            
        except Exception as e:
            st.error(f"Error rendering user statistics: {str(e)}")


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
                # Convert to DataFrame if not already
                if not isinstance(products, pd.DataFrame):
                    products = pd.DataFrame(products)
                # Convert 'Price' column to string if it contains dicts
                if 'Price' in products.columns:
                    products['Price'] = products['Price'].apply(lambda x: str(x) if isinstance(x, dict) else x)
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
        st.subheader(f"{self.const.ICONS['paper_and_pen']} Additional info")

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
    """Handles Instagram-related functionality including posts, stories""" #
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
        # Story-related session state
        if 'story_page' not in st.session_state:
            st.session_state['story_page'] = 0
        if 'stories_per_page' not in st.session_state:
            st.session_state['stories_per_page'] = 6
        if 'selected_story_id' not in st.session_state:
            st.session_state['selected_story_id'] = None
        if 'story_filter' not in st.session_state:
            st.session_state['story_filter'] = "All"

    def render(self):

        posts_tab, stories_tab = st.tabs([ #
            f"{self.const.ICONS['post']} Posts", #
            f"{self.const.ICONS['story']} Stories", #
        ]) #

        with posts_tab: #
            self._render_posts_tab() #

        with stories_tab: #
            self._render_stories_tab() #

        st.write("---") #

    def _render_posts_tab(self): #
        """Renders the section for managing and viewing Instagram posts with optimized performance.""" #

        # Check if we have a selected post and show the detail view directly
        if 'selected_post_id' in st.session_state and st.session_state['selected_post_id']:
            self._render_post_detail(st.session_state['selected_post_id'])
            return

        # Only show action buttons in the grid view
        col1, col2, col3, col4, col5 = st.columns(5) #

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
                        if hasattr(self.backend, 'set_post_labels_by_model'): #
                            result = self.backend.set_post_labels_by_model() #
                            if result and result.get('success'): #
                                st.success(f"Labels updated!") #
                                st.rerun() #
                            else: #
                                st.error(f"Labeling failed") #
                        else: #
                            st.error(f"Function not found") #
                    except Exception as e: #
                        st.error(f"Error: {str(e)}") #

        with col3:
            if st.button(f"{self.const.ICONS['folder']} Download", help="Download post labels as JSON", use_container_width=True):
                try:
                    # Get labeled posts data from backend
                    labeled_data = self.backend.download_post_labels()

                    # Check if we got valid data
                    if isinstance(labeled_data, dict) and not labeled_data.get("error"):
                        # Convert dict to JSON string with ensure_ascii=False to properly handle Farsi/Persian characters
                        import json
                        json_data = json.dumps(labeled_data, indent=2, ensure_ascii=False)

                        # Create download link
                        import base64
                        json_bytes = json_data.encode('utf-8')
                        b64 = base64.b64encode(json_bytes).decode()
                        href = f'<a href="data:application/json;charset=utf-8;base64,{b64}" download="post_labels.json">Download JSON file</a>'

                        # Display download link
                        st.markdown(href, unsafe_allow_html=True)
                        st.success("JSON file ready for download!")
                    else:
                        st.error("Failed to prepare data for download")
                except Exception as e:
                    st.error(f"Error preparing download: {str(e)}")

        with col4:
            if st.button(f"{self.const.ICONS['delete']} Remove Labels", help="Remove all labels from posts", use_container_width=True):
                try:
                    with st.spinner("Removing all labels..."):
                        updated_count = self.backend.unset_all_post_labels()
                        if updated_count > 0:
                            st.success(f"Successfully removed labels from {updated_count} posts!")
                            st.rerun()
                        else:
                            st.info("No labels were removed.")
                except Exception as e:
                    st.error(f"Error removing labels: {str(e)}")

        with col5:
            try:
                posts = self.backend.get_posts()
                all_labels = sorted(list(set(post.get('label', '') for post in posts if post.get('label', ''))))
                filter_options = ["All"] + all_labels

                selected_filter = st.selectbox(
                    f"{self.const.ICONS['label']} Filter",
                    options=filter_options,
                    index=filter_options.index(st.session_state['post_filter']) if st.session_state['post_filter'] in filter_options else 0,
                    key="post_filter_selector",
                    label_visibility="collapsed"
                )

                # Apply filter change immediately instead of using on_change
                if selected_filter != st.session_state['post_filter']:
                    st.session_state['post_filter'] = selected_filter
                    st.session_state['post_page'] = 0  # Reset to first page when filter changes
                    st.rerun()
            except Exception as e:
                st.error(f"Error loading labels: {str(e)}")

        try:
            posts = self.backend.get_posts()
            total_posts = len(posts)

            if not posts:
                st.info("No posts found. Click 'Update Posts' to fetch them.")
                return

            # Fix posts per page at 12 (remove selector)
            st.session_state['posts_per_page'] = 12

            if st.session_state['post_filter'] != "All":
                filtered_posts = [post for post in posts if post.get('label', '') == st.session_state['post_filter']]
            else:
                filtered_posts = posts

            filtered_count = len(filtered_posts)
            max_pages = (filtered_count - 1) // st.session_state['posts_per_page'] + 1 if filtered_count > 0 else 1

            if st.session_state['post_page'] >= max_pages:
                st.session_state['post_page'] = max_pages - 1

            start_idx = st.session_state['post_page'] * st.session_state['posts_per_page']
            end_idx = min(start_idx + st.session_state['posts_per_page'], filtered_count)
            current_page_posts = filtered_posts[start_idx:end_idx]

            self._render_post_grid(current_page_posts)

            if filtered_count > 0:
                # Add CSS for minimal pagination
                st.markdown("""
                <style>
                .minimal-pagination {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 5px;
                    margin: 15px 0;
                }
                .page-btn {
                    min-width: 30px !important;
                    height: 30px !important;
                    padding: 0 !important;
                    font-size: 12px !important;
                    display: inline-flex !important;
                    align-items: center;
                    justify-content: center;
                    border-radius: 4px !important;
                }
                .page-nav-btn {
                    min-width: 35px !important;
                    height: 30px !important;
                    padding: 0 8px !important;
                    font-size: 12px !important;
                }
                </style>
                """, unsafe_allow_html=True)

                # Display pagination in a single row with minimal styling
                st.markdown('<div class="minimal-pagination">', unsafe_allow_html=True)
                cols = st.columns([1, 6, 1])

                with cols[0]:
                    prev_disabled = st.session_state['post_page'] <= 0
                    if st.button(f"{self.const.ICONS['previous']}",
                                disabled=prev_disabled,
                                key="prev_page_btn",
                                help="Previous page",
                                use_container_width=True):
                        st.session_state['post_page'] -= 1
                        st.rerun()

                with cols[1]:
                    # Create a multi-column layout for page numbers
                    if max_pages <= 10:
                        # If few pages, show all page numbers
                        page_cols = st.columns(max_pages)
                        for i in range(max_pages):
                            with page_cols[i]:
                                current = i == st.session_state['post_page']
                                if st.button(f"{i+1}",
                                           key=f"page_btn_{i}",
                                           disabled=current,
                                           type="primary" if current else "secondary"):
                                    st.session_state['post_page'] = i
                                    st.rerun()
                    else:
                        # For more pages, use a smart pagination layout
                        # Always show: first page, current page, last page, and pages around current
                        current_page = st.session_state['post_page']
                        pages_to_show = {0, current_page, max_pages - 1}  # First, current, last

                    # Add pages around current page
                        for i in range(max(0, current_page - 2), min(max_pages, current_page + 3)):
                            pages_to_show.add(i)

                    # Convert to sorted list
                        pages_to_show = sorted(list(pages_to_show))

                        # Calculate where to add "..."
                        gaps = []
                        for i in range(len(pages_to_show) - 1):
                            if pages_to_show[i+1] - pages_to_show[i] > 1:
                                gaps.append(i)

                        # Add the gaps to the display sequence
                        display_sequence = []
                        for i, page in enumerate(pages_to_show):
                            display_sequence.append(page)
                            if i in gaps:
                                display_sequence.append("...")

                        # Create columns for each page number or ellipsis
                        page_cols = st.columns(len(display_sequence))

                        for i, item in enumerate(display_sequence):
                            with page_cols[i]:
                                if item == "...":
                                    st.markdown("...")
                                else:
                                    current = item == current_page
                                    if st.button(f"{item+1}",
                                              key=f"page_btn_{item}",
                                              disabled=current,
                                              type="primary" if current else "secondary"):
                                        st.session_state['post_page'] = item
                                        st.rerun()

                with cols[2]:
                    next_disabled = st.session_state['post_page'] >= max_pages - 1
                    if st.button(f"{self.const.ICONS['next']}",
                                disabled=next_disabled,
                                key="next_page_btn",
                                help="Next page",
                                use_container_width=True):
                        st.session_state['post_page'] += 1
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

                # Display post count information as a small caption
                st.caption(f"Showing {start_idx+1}-{end_idx} of {filtered_count} posts")

        except Exception as e: #
            st.error(f"Error loading post grid: {str(e)}") #

    def _render_stories_tab(self):
        """Renders the stories tab with consistent grid layout and functionality as posts"""
        # Check if we have a selected story and show detail view
        if st.session_state['selected_story_id']:
            self._render_story_detail(st.session_state['selected_story_id'])
            return

        # Action buttons row (same structure as posts)
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            if st.button(f"{self.const.ICONS['update']} Update Stories",
                        help="Fetch and update Instagram stories",
                        use_container_width=True):
                with st.spinner("Fetching stories..."):
                    try:
                        success = self.backend.fetch_instagram_stories()
                        if success:
                            st.success(f"{self.const.ICONS['success']} Stories updated!")
                            st.rerun()
                        else:
                            st.error(f"{self.const.ICONS['error']} Fetch failed")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col2:
            if st.button(f"{self.const.ICONS['model']} AI Label",
                        help="Auto-label stories with AI",
                        use_container_width=True):
                with st.spinner("AI labeling..."):
                    try:
                        result = self.backend.set_story_labels_by_model()
                        if result and result.get('success'):
                            st.success(f"Labels updated!")
                            st.rerun()
                        else:
                            st.error(f"Labeling failed")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col3:
            if st.button(f"{self.const.ICONS['folder']} Download",
                        help="Download story labels as JSON",
                        use_container_width=True):
                try:
                    labeled_data = self.backend.download_story_labels()
                    if isinstance(labeled_data, dict) and not labeled_data.get("error"):
                        import json
                        json_data = json.dumps(labeled_data, indent=2, ensure_ascii=False)
                        import base64
                        json_bytes = json_data.encode('utf-8')
                        b64 = base64.b64encode(json_bytes).decode()
                        href = f'<a href="data:application/json;charset=utf-8;base64,{b64}" download="story_labels.json">Download JSON file</a>'
                        st.markdown(href, unsafe_allow_html=True)
                        st.success("JSON file ready for download!")
                    else:
                        st.error("Failed to prepare data for download")
                except Exception as e:
                    st.error(f"Error preparing download: {str(e)}")

        with col4:
            if st.button(f"{self.const.ICONS['delete']} Remove Labels",
                        help="Remove all labels from stories",
                        use_container_width=True):
                try:
                    with st.spinner("Removing all labels..."):
                        updated_count = self.backend.unset_all_story_labels()
                        if updated_count > 0:
                            st.success(f"Successfully removed labels from {updated_count} stories!")
                            st.rerun()
                        else:
                            st.info("No labels were removed.")
                except Exception as e:
                    st.error(f"Error removing labels: {str(e)}")

        with col5:
            try:
                stories = self.backend.get_stories()
                all_labels = sorted(list(set(story.get('label', '') for story in stories if story.get('label', ''))))
                filter_options = ["All"] + all_labels

                selected_filter = st.selectbox(
                    f"{self.const.ICONS['label']} Filter",
                    options=filter_options,
                    index=filter_options.index(st.session_state['story_filter']) if st.session_state['story_filter'] in filter_options else 0,
                    key="story_filter_selector",
                    label_visibility="collapsed"
                )

                if selected_filter != st.session_state['story_filter']:
                    st.session_state['story_filter'] = selected_filter
                    st.session_state['story_page'] = 0
                    st.rerun()
            except Exception as e:
                st.error(f"Error loading labels: {str(e)}")

        try:
            stories = self.backend.get_stories()
            total_stories = len(stories)

            if not stories:
                st.info("No stories found. Click 'Update Stories' to fetch them.")
                return

            st.session_state['stories_per_page'] = 12

            if st.session_state['story_filter'] != "All":
                filtered_stories = [story for story in stories if story.get('label', '') == st.session_state['story_filter']]
            else:
                filtered_stories = stories

            filtered_count = len(filtered_stories)
            max_pages = (filtered_count - 1) // st.session_state['stories_per_page'] + 1 if filtered_count > 0 else 1

            if st.session_state['story_page'] >= max_pages:
                st.session_state['story_page'] = max_pages - 1

            start_idx = st.session_state['story_page'] * st.session_state['stories_per_page']
            end_idx = min(start_idx + st.session_state['stories_per_page'], filtered_count)
            current_page_stories = filtered_stories[start_idx:end_idx]

            self._render_story_grid(current_page_stories)

            if filtered_count > 0:
                # Pagination controls (same as posts)
                st.markdown("""
                <style>
                .minimal-pagination {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 5px;
                    margin: 15px 0;
                }
                .page-btn {
                    min-width: 30px !important;
                    height: 30px !important;
                    padding: 0 !important;
                    font-size: 12px !important;
                    display: inline-flex !important;
                    align-items: center;
                    justify-content: center;
                    border-radius: 4px !important;
                }
                .page-nav-btn {
                    min-width: 35px !important;
                    height: 30px !important;
                    padding: 0 8px !important;
                    font-size: 12px !important;
                }
                </style>
                """, unsafe_allow_html=True)

                st.markdown('<div class="minimal-pagination">', unsafe_allow_html=True)
                cols = st.columns([1, 6, 1])

                with cols[0]:
                    prev_disabled = st.session_state['story_page'] <= 0
                    if st.button(f"{self.const.ICONS['previous']}",
                                disabled=prev_disabled,
                                key="prev_story_page_btn",
                                help="Previous page",
                                use_container_width=True):
                        st.session_state['story_page'] -= 1
                        st.rerun()

                with cols[1]:
                    if filtered_count <= 10:
                        page_cols = st.columns(filtered_count)
                        for i in range(filtered_count):
                            with page_cols[i]:
                                current = i == st.session_state['story_page']
                                if st.button(f"{i+1}",
                                           key=f"story_page_btn_{i}",
                                           disabled=current,
                                           type="primary" if current else "secondary"):
                                    st.session_state['story_page'] = i
                                    st.rerun()
                    else:
                        current_page = st.session_state['story_page']
                        pages_to_show = {0, current_page, filtered_count - 1}
                        for i in range(max(0, current_page - 2), min(filtered_count, current_page + 3)):
                            pages_to_show.add(i)
                        pages_to_show = sorted(list(pages_to_show))

                        gaps = []
                        for i in range(len(pages_to_show) - 1):
                            if pages_to_show[i+1] - pages_to_show[i] > 1:
                                gaps.append(i)

                        display_sequence = []
                        for i, page in enumerate(pages_to_show):
                            display_sequence.append(page)
                            if i in gaps:
                                display_sequence.append("...")

                        page_cols = st.columns(len(display_sequence))

                        for i, item in enumerate(display_sequence):
                            with page_cols[i]:
                                if item == "...":
                                    st.markdown("...")
                                else:
                                    current = item == current_page
                                    if st.button(f"{item+1}",
                                              key=f"story_page_btn_{item}",
                                              disabled=current,
                                              type="primary" if current else "secondary"):
                                        st.session_state['story_page'] = item
                                        st.rerun()

                with cols[2]:
                    next_disabled = st.session_state['story_page'] >= max_pages - 1
                    if st.button(f"{self.const.ICONS['next']}",
                                disabled=next_disabled,
                                key="next_story_page_btn",
                                help="Next page",
                                use_container_width=True):
                        st.session_state['story_page'] += 1
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

                st.caption(f"Showing {start_idx+1}-{end_idx} of {filtered_count} stories")

        except Exception as e:
            st.error(f"Error loading story grid: {str(e)}")

    def _render_story_grid(self, stories_to_display):
        """Renders a paginated grid of Instagram stories matching post grid style"""
        if 'selected_story_id' not in st.session_state:
            st.session_state['selected_story_id'] = None

        num_columns = 4
        cols = st.columns(num_columns)

        # Custom CSS for the grid (same as posts)
        st.markdown("""
        <style>
        .story-grid {
            margin-bottom: 20px;
        }
        .story-image-container {
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .story-image-container:hover {
            transform: translateY(-5px);
        }
        .story-image-container img {
            width: 100%;
            aspect-ratio: 1;
            object-fit: cover;
            display: block;
        }
        .story-label {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background-color: rgba(0,0,0,0.7);
            color: white;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 12px;
            max-width: 80%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .story-view-btn {
            width: 100% !important;
            margin-top: 0 !important;
            padding: 4px 0 !important;
            font-size: 13px !important;
            border-radius: 6px !important;
            background-color: #0095f6 !important;
            color: white !important;
            border: none !important;
            font-weight: 500 !important;
            cursor: pointer;
        }
        </style>
        """, unsafe_allow_html=True)

        for index, story in enumerate(stories_to_display):
            story_id = story.get('id')
            if not story_id:
                story_id_key = f"index_{index}"
            else:
                story_id_key = str(story_id)

            col_index = index % num_columns
            with cols[col_index]:
                with st.container():
                    media_url = story.get('media_url')
                    thumbnail_url = story.get('thumbnail_url')
                    label = story.get('label', '')

                    st.markdown(f"""
                    <div class="story-image-container">
                        <img src="{thumbnail_url or media_url}" alt="Instagram story">
                        {f'<div class="story-label">{label}</div>' if label else ''}
                    </div>
                    """, unsafe_allow_html=True)

                    view_btn = st.button("View Details", key=f"view_story_btn_{story_id_key}", use_container_width=True)

                    if view_btn:
                        st.session_state['selected_story_id'] = story_id
                        st.rerun()

    def _render_story_detail(self, story_id):
        """Renders the detail view for a single Instagram story matching post detail style"""
        try:
            stories = self.backend.get_stories()

            # Get all stories with the same label if filtered view is active
            if st.session_state['story_filter'] != "All":
                filtered_stories = [story for story in stories if story.get('label', '') == st.session_state['story_filter']]
            else:
                filtered_stories = stories

            # Find the current story
            story = next((s for s in filtered_stories if s.get('id') == story_id), None)

            # Get the index of the current story in the filtered list
            if story:
                current_index = filtered_stories.index(story)
                total_stories = len(filtered_stories)
                prev_index = (current_index - 1) % total_stories if total_stories > 1 else None
                next_index = (current_index + 1) % total_stories if total_stories > 1 else None

                prev_story_id = filtered_stories[prev_index]['id'] if prev_index is not None else None
                next_story_id = filtered_stories[next_index]['id'] if next_index is not None else None
            else:
                current_index = None
                total_stories = len(filtered_stories)
                prev_story_id = None
                next_story_id = None

            if not story:
                st.error(f"Story not found with ID: {story_id}")
                if st.button("Back to grid", use_container_width=True):
                    st.session_state['selected_story_id'] = None
                    st.rerun()
                return

            # Apply styling for the details page (same as posts)
            st.markdown("""
            <style>
            .story-detail-image {
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .story-detail-section {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 16px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            }
            .story-caption {
                max-height: 200px;
                overflow-y: auto;
                padding: 10px;
                background-color: white;
                border-radius: 6px;
                border: 1px solid #eee;
                margin-top: 5px;
            }
            .story-fixed-response-field {
                background-color: white;
                border-radius: 6px;
                border: 1px solid #eee;
                padding: 10px;
                margin-top: 5px;
            }
            .story-detail-navigation {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 15px;
            }
            .story-pagination-counter {
                text-align: center;
                font-size: 14px;
                color: #666;
            }
            .story-mini-header {
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 8px;
            }
            </style>
            """, unsafe_allow_html=True)

            # Navigation header with back, prev, next buttons
            cols = st.columns([1, 3, 1])

            with cols[0]:
                if st.button("Back", key="back_to_story_grid_btn", help="Back to grid", use_container_width=True):
                    st.session_state['selected_story_id'] = None
                    st.rerun()

            with cols[2]:
                nav_cols = st.columns(2)
                with nav_cols[0]:
                    prev_disabled = prev_story_id is None
                    if st.button(f"{self.const.ICONS['previous']}",
                               key="detail_prev_story_btn",
                               disabled=prev_disabled,
                               help="Previous story",
                               use_container_width=True):
                        if prev_story_id:
                            st.session_state['selected_story_id'] = prev_story_id
                            st.rerun()

                with nav_cols[1]:
                    next_disabled = next_story_id is None
                    if st.button(f"{self.const.ICONS['next']}",
                               key="detail_next_story_btn",
                               disabled=next_disabled,
                               help="Next story",
                               use_container_width=True):
                        if next_story_id:
                            st.session_state['selected_story_id'] = next_story_id
                            st.rerun()

                if current_index is not None:
                    st.markdown(
                        f'<div style="text-align: center; font-size: 0.9em; color: #666; margin-top: 10px;">'
                        f'Story <span style="font-size: 1.2em; font-weight: bold;">{current_index + 1}</span> of {total_stories}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            # Layout for story details
            col1, col2 = st.columns([2, 3])

            with col1:
                # Media display
                st.markdown('<div class="story-detail-image">', unsafe_allow_html=True)
                media_url = story.get('media_url')
                thumbnail_url = story.get('thumbnail_url')
                media_type = story.get('media_type', '').lower()

                if media_type == "video":
                    try:
                        st.video(media_url)
                    except Exception as e:
                        st.error(f"Unable to play video: {str(e)}")
                        if thumbnail_url:
                            st.image(thumbnail_url, use_container_width=True)
                            st.caption("Video thumbnail (video playback unavailable)")
                        else:
                            st.warning("Video playback unavailable")
                elif media_url:
                    st.image(media_url, use_container_width=True)
                else:
                    st.warning("No media available")

                st.markdown('</div>', unsafe_allow_html=True)

                # Label selector section
                with st.container():
                    try:
                        products_data = self.backend.get_products()
                        product_titles = sorted([p['Title'] for p in products_data if p.get('Title')])
                        custom_labels = st.session_state.get('custom_labels', [])
                        all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels)))

                        current_label = story.get('label', '')
                        try:
                            default_select_index = all_labels.index(current_label) if current_label else 0
                        except ValueError:
                            if current_label:
                                all_labels.append(current_label)
                                default_select_index = all_labels.index(current_label)
                            else:
                                default_select_index = 0

                        label_col, ai_col, remove_col = st.columns([3, 1, 1])

                        with label_col:
                            select_key = f"story_label_select_detail_{story_id}"
                            selected_label = st.selectbox(
                                "Select Label",
                                options=all_labels,
                                key=select_key,
                                index=default_select_index
                            )

                        with ai_col:
                            st.write("")
                            if st.button(f"{self.const.ICONS['brain']}", key=f"story_auto_label_btn_{story_id}", help="Auto-label using AI"):
                                with st.spinner("Analyzing image..."):
                                    result = self.backend.set_single_story_label_by_model(story_id)
                                    if result and result.get("success"):
                                        st.success(f"Image labeled as: {result.get('label')}")
                                        st.rerun()
                                    else:
                                        error_msg = result.get('message', 'Unknown error') if result else 'Unknown error'
                                        st.error(f"Failed to label image: {error_msg}")
                                        if "Model confidence too low" in error_msg:
                                            st.info("The AI model wasn't confident enough to determine a label for this image.")

                        with remove_col:
                            st.write("")
                            if st.button(f"{self.const.ICONS['delete']}", key=f"story_remove_label_btn_{story_id}", help="Remove label"):
                                if self.backend.remove_story_label(story_id):
                                    st.success("Label removed successfully")
                                    st.rerun()
                                else:
                                    st.error("Failed to remove label")

                        if selected_label != current_label and selected_label != "-- Select --":
                            try:
                                label_success = self.backend.set_story_label(story_id, selected_label)
                                if label_success:
                                    st.success(f"{self.const.ICONS['success']} Label updated")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"{self.const.ICONS['error']} Error saving label: {str(e)}")
                    except Exception as e:
                        st.error(f"Error loading labels: {str(e)}")

                    label_input_col, label_btn_col = st.columns([3, 1])
                    with label_input_col:
                        new_label = st.text_input(
                            "Add custom label",
                            key=f"story_detail_new_custom_label_{story_id}",
                            placeholder="Add custom label",
                            label_visibility="collapsed"
                        )

                    with label_btn_col:
                        if st.button(f"{self.const.ICONS['add']}", key=f"story_detail_add_label_btn_{story_id}", help="Add label", use_container_width=True):
                            new_label_stripped = new_label.strip()
                            if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']:
                                st.session_state['custom_labels'].append(new_label_stripped)
                                st.success(f"Added '{new_label_stripped}'")
                                st.rerun()
                            elif not new_label_stripped:
                                st.warning("Label cannot be empty")
                            else:
                                st.warning(f"Label already exists")

            with col2:
                # Story details - Caption
                st.write("")
                st.markdown('<div class="story-mini-header">Caption</div>', unsafe_allow_html=True)
                caption = story.get('caption', 'No caption available')

                st.markdown(f'<div style="margin-bottom:20px;">{caption}</div>', unsafe_allow_html=True)

                # Admin Explanation section
                st.write("")

                try:
                    current_explanation = self.backend.get_story_admin_explanation(story_id)

                    with st.form(key=f"story_admin_explanation_form_{story_id}", border=False):
                        explanation = st.text_area(
                            "Explain",
                            value=current_explanation if current_explanation else "",
                            placeholder="Add an explanation for this story",
                            key=f"story_admin_explanation_{story_id}"
                        )

                        exp_col1, exp_col2 = st.columns(2)

                        with exp_col1:
                            save_exp_button = st.form_submit_button(
                                f"{self.const.ICONS['save']} Save Explanation",
                                use_container_width=True
                            )

                        with exp_col2:
                            remove_exp_button = st.form_submit_button(
                                f"{self.const.ICONS['delete']} Remove Explanation",
                                type="secondary",
                                use_container_width=True
                            )

                        if save_exp_button:
                            if explanation.strip():
                                try:
                                    success = self.backend.set_story_admin_explanation(story_id, explanation.strip())
                                    if success:
                                        st.success(f"{self.const.ICONS['success']} Explanation saved!")
                                        st.rerun()
                                    else:
                                        st.error(f"{self.const.ICONS['error']} Failed to save explanation")
                                except Exception as e:
                                    st.error(f"{self.const.ICONS['error']} Error saving explanation: {str(e)}")
                            else:
                                st.warning("Explanation cannot be empty")

                        if remove_exp_button:
                            try:
                                success = self.backend.remove_story_admin_explanation(story_id)
                                if success:
                                    st.success("Explanation removed")
                                    st.rerun()
                                else:
                                    st.error("Failed to remove explanation")
                            except Exception as e:
                                st.error(f"Error removing explanation: {str(e)}")

                except Exception as e:
                    st.error(f"Error loading admin explanation: {str(e)}")

                # Fixed response editing functionality
                st.write("")
                st.markdown('<div class="story-mini-header">Fixed Response</div>', unsafe_allow_html=True)

                try:
                    raw_responses_data = self.backend.get_story_fixed_responses(story_id)
                except Exception as e:
                    raw_responses_data = None
                    st.error(f"Error loading fixed responses: {str(e)}")

                exist_tab, add_tab = st.tabs(["Existing", "Add New"])

                with exist_tab:
                    fixed_responses_to_display = []
                    if isinstance(raw_responses_data, list):
                        fixed_responses_to_display = raw_responses_data
                    elif isinstance(raw_responses_data, dict) and raw_responses_data:
                        fixed_responses_to_display = [raw_responses_data]

                    if not fixed_responses_to_display:
                        st.info("No fixed response exists for this story. Use the 'Add New' tab to create one.")
                    else:
                        for index, response_item in enumerate(fixed_responses_to_display):
                            if not isinstance(response_item, dict):
                                st.warning(f"Skipping an invalid fixed response item (item {index + 1}).")
                                continue

                            st.markdown("---")
                            form_key = f"story_existing_response_form_{story_id}_{index}"
                            original_trigger_keyword = response_item.get("trigger_keyword", "")

                            with st.form(key=form_key, border=True):
                                st.markdown(f"**Response for Trigger: \"{original_trigger_keyword}\"**" if original_trigger_keyword else f"**Response Item {index+1}**")

                                trigger_keyword_input = st.text_input(
                                    "Trigger keyword",
                                    value=original_trigger_keyword,
                                    key=f"trigger_{form_key}"
                                )
                                dm_response_input = st.text_area(
                                    "DM reply",
                                    value=response_item.get("direct_response_text", ""),
                                    key=f"dm_{form_key}"
                                )
                                col_update, col_delete = st.columns(2)
                                with col_update:
                                    update_button = st.form_submit_button(f"{self.const.ICONS['save']} Update This Response", use_container_width=True)
                                with col_delete:
                                    delete_button = st.form_submit_button(
                                        f"{self.const.ICONS['delete']} Remove This Response",
                                        type="secondary",
                                        use_container_width=True
                                    )

                                if update_button:
                                    new_trigger_keyword = trigger_keyword_input.strip()
                                    if not new_trigger_keyword:
                                        st.error("Trigger keyword is required.")
                                    else:
                                        success = self.backend.create_or_update_story_fixed_response(
                                            story_id=story_id,
                                            trigger_keyword=new_trigger_keyword,
                                            direct_response_text=dm_response_input.strip() or None
                                        )
                                        if success:
                                            st.success(f"Response for '{new_trigger_keyword}' processed successfully!")
                                            if original_trigger_keyword and original_trigger_keyword != new_trigger_keyword:
                                                st.info(f"Content previously associated with '{original_trigger_keyword}' is now under '{new_trigger_keyword}'. The old trigger entry might still exist if not explicitly managed by the backend as a 'rename'.")
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to process response for '{new_trigger_keyword}'.")

                                if delete_button:
                                    if not original_trigger_keyword:
                                        st.error("Cannot delete response: Original trigger keyword is missing.")
                                    else:
                                        try:
                                            success = self.backend.delete_story_fixed_response(story_id, original_trigger_keyword)
                                            if success:
                                                st.success(f"Response for '{original_trigger_keyword}' removed successfully.")
                                                st.rerun()
                                            else:
                                                st.error(f"Failed to remove response for '{original_trigger_keyword}'.")
                                        except Exception as e:
                                            st.error(f"Error removing response: {str(e)}")

                with add_tab:
                    try:
                        with st.form(key=f"story_new_response_form_{story_id}", border=False):
                            new_trigger_keyword = st.text_input(
                                "Trigger keyword",
                                placeholder="Enter words that will trigger this response"
                            )
                            new_dm_response = st.text_area(
                                "DM reply",
                                placeholder="Response sent as DM when someone messages with trigger words"
                            )
                            new_submit_button = st.form_submit_button(f"{self.const.ICONS['add']} Create", use_container_width=True)
                            if new_submit_button:
                                try:
                                    if new_trigger_keyword.strip():
                                        new_success = self.backend.create_or_update_story_fixed_response(
                                            story_id=story_id,
                                            trigger_keyword=new_trigger_keyword.strip(),
                                            direct_response_text=new_dm_response.strip() if new_dm_response.strip() else None
                                        )
                                        if new_success:
                                            st.success(f"{self.const.ICONS['success']} Created!")
                                            st.rerun()
                                    else:
                                        st.error("Trigger keyword is required")
                                except Exception as e:
                                    st.error(f"{self.const.ICONS['error']} Error creating: {str(e)}")
                    except Exception as e:
                        st.error(f"Error loading form: {str(e)}")

        except Exception as e:
            st.error(f"Error loading story details: {str(e)}")
            if st.button("Back to grid", use_container_width=True):
                st.session_state['selected_story_id'] = None
                st.rerun()

    def _render_post_grid(self, posts_to_display): #
        """Renders a paginated grid of Instagram posts with minimal UI""" #
        if 'selected_post_id' not in st.session_state:
            st.session_state['selected_post_id'] = None

        num_columns = 4 #
        cols = st.columns(num_columns) #

        # Custom CSS for the Instagram-like grid
        st.markdown("""
        <style>
        .post-grid {
            margin-bottom: 20px;
        }
        .post-image-container {
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .post-image-container:hover {
            transform: translateY(-5px);
        }
        .post-image-container img {
            width: 100%;
            aspect-ratio: 1;
            object-fit: cover;
            display: block;
        }
        .post-label {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background-color: rgba(0,0,0,0.7);
            color: white;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 12px;
            max-width: 80%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .view-btn {
            width: 100% !important;
            margin-top: 0 !important;
            padding: 4px 0 !important;
            font-size: 13px !important;
            border-radius: 6px !important;
            background-color: #0095f6 !important;
            color: white !important;
            border: none !important;
            font-weight: 500 !important;
            cursor: pointer;
        }
        </style>
        """, unsafe_allow_html=True)

        # Use Streamlit columns for the grid
        for index, post in enumerate(posts_to_display): #
            post_id = post.get('id') #
            if not post_id: #
                post_id_key = f"index_{index}" #
            else: #
                post_id_key = str(post_id) #

            col_index = index % num_columns #
            with cols[col_index]: #
                # Create a container for the post
                with st.container():
                    # Get media URLs and label for post
                    media_url = post.get('media_url') #
                    thumbnail_url = post.get('thumbnail_url')
                    label = post.get('label', '')

                    # Show the image in a container
                    st.markdown(f"""
                    <div class="post-image-container">
                        <img src="{thumbnail_url or media_url}" alt="Instagram post">
                        {f'<div class="post-label">{label}</div>' if label else ''}
                    </div>
                    """, unsafe_allow_html=True)

                    # Use a regular button styled to be small and flat
                    view_btn = st.button("View Details", key=f"view_btn_{post_id_key}", use_container_width=True)

                    # Handle click
                    if view_btn:
                        st.session_state['selected_post_id'] = post_id
                        st.rerun()

    def _render_post_detail(self, post_id):
        """Renders the detail view for a single Instagram post"""
        posts = self.backend.get_posts()

        # Get all posts with the same label if filtered view is active
        if st.session_state['post_filter'] != "All":
            filtered_posts = [post for post in posts if post.get('label', '') == st.session_state['post_filter']]
        else:
            filtered_posts = posts

        # Find the current post
        post = next((p for p in filtered_posts if p.get('id') == post_id), None)

        # Get the index of the current post in the filtered list
        if post:
            current_index = filtered_posts.index(post)
            total_posts = len(filtered_posts)
            prev_index = (current_index - 1) % total_posts if total_posts > 1 else None
            next_index = (current_index + 1) % total_posts if total_posts > 1 else None

            prev_post_id = filtered_posts[prev_index]['id'] if prev_index is not None else None
            next_post_id = filtered_posts[next_index]['id'] if next_index is not None else None
        else:
            # Post not found in current filter
            current_index = None
            total_posts = len(filtered_posts)
            prev_post_id = None
            next_post_id = None

        if not post:
            st.error(f"Post not found with ID: {post_id}")
            if st.button("Back to grid", use_container_width=True):
                st.session_state['selected_post_id'] = None
                st.rerun()
            return

        # Apply some styling for the details page
        st.markdown("""
        <style>
        .post-detail-image {
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .post-detail-section {
            background-color: #f8f9fa;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        }
        .post-caption {
            max-height: 200px;
            overflow-y: auto;
            padding: 10px;
            background-color: white;
            border-radius: 6px;
            border: 1px solid #eee;
            margin-top: 5px;
        }
        .fixed-response-field {
            background-color: white;
            border-radius: 6px;
            border: 1px solid #eee;
            padding: 10px;
            margin-top: 5px;
        }
        .detail-navigation {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }
        .pagination-counter {
            text-align: center;
            font-size: 14px;
            color: #666;
        }
        .mini-header {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        </style>
        """, unsafe_allow_html=True)

        # Simplified navigation header with only back, prev, next buttons
        cols = st.columns([1, 3, 1])

        with cols[0]:
            # Back button
            if st.button("Back", key="back_to_grid_btn", help="Back to grid", use_container_width=True):
                st.session_state['selected_post_id'] = None
                st.rerun()

        with cols[2]:
            # Navigation buttons container
            nav_cols = st.columns(2)
            with nav_cols[0]:
                # Previous button
                prev_disabled = prev_post_id is None
                if st.button(f"{self.const.ICONS['previous']}",
                           key="detail_prev_post_btn",
                           disabled=prev_disabled,
                           help="Previous post",
                           use_container_width=True):
                    if prev_post_id:
                        st.session_state['selected_post_id'] = prev_post_id
                        st.rerun()

            with nav_cols[1]:
                # Next button
                next_disabled = next_post_id is None
                if st.button(f"{self.const.ICONS['next']}",
                           key="detail_next_post_btn",
                           disabled=next_disabled,
                           help="Next post",
                           use_container_width=True):
                    if next_post_id:
                        st.session_state['selected_post_id'] = next_post_id
                        st.rerun()

            # Add post counter below navigation buttons
            if current_index is not None:
                st.markdown(
                    f'<div style="text-align: center; font-size: 0.9em; color: #666; margin-top: 10px;">'
                    f'Post <span style="font-size: 1.2em; font-weight: bold;">{current_index + 1}</span> of {total_posts}'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # Layout for post details
        col1, col2 = st.columns([2, 3])

        with col1:
            # Image display with custom class
            st.markdown('<div class="post-detail-image">', unsafe_allow_html=True)
            media_url = post.get('media_url')
            thumbnail_url = post.get('thumbnail_url')
            media_type = post.get('media_type', '').lower()

            if media_type == "video":
                try:
                    # For videos, use the native video player
                    st.video(media_url)
                except Exception as e:
                    # If video player fails, show error and fallback
                    st.error(f"Unable to play video: {str(e)}")
                    if thumbnail_url:
                        st.image(thumbnail_url, use_container_width=True)
                        st.caption("Video thumbnail (video playback unavailable)")
                    else:
                        st.warning("Video playback unavailable")
            elif media_url:
                # For images, display the image
                st.image(media_url, use_container_width=True)
            else:
                st.warning("No media available")

            st.markdown('</div>', unsafe_allow_html=True)

            # Add custom label input section below the image
            with st.container():
                # Get product titles for dropdown (moved from settings section)
                try:
                    products_data = self.backend.get_products()
                    product_titles = sorted([p['Title'] for p in products_data if p.get('Title')])
                    custom_labels = st.session_state.get('custom_labels', [])
                    all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels)))

                    current_label = post.get('label', '')
                    try:
                        default_select_index = all_labels.index(current_label) if current_label else 0
                    except ValueError:
                        if current_label:
                            all_labels.append(current_label)
                            default_select_index = all_labels.index(current_label)
                        else:
                            default_select_index = 0

                    # Add columns for label selection and buttons
                    label_col, ai_col, remove_col = st.columns([3, 1, 1])

                    with label_col:
                        # Label selector
                        select_key = f"label_select_detail_{post_id}"
                        selected_label = st.selectbox(
                            "Select Label",  # Added label parameter
                            options=all_labels,
                            key=select_key,
                            index=default_select_index
                        )

                    with ai_col:
                        # Auto-label button
                        st.write("") # Add space to align with selectbox
                        if st.button(f"{self.const.ICONS['brain']}", key=f"auto_label_btn_{post_id}", help="Auto-label using AI"):
                            with st.spinner("Analyzing image..."):
                                # Call backend method to set label using vision model
                                result = self.backend.set_single_post_label_by_model(post_id)
                                if result and result.get("success"):
                                    st.success(f"Image labeled as: {result.get('label')}")
                                    st.rerun()
                                else:
                                    error_msg = result.get('message', 'Unknown error') if result else 'Unknown error'
                                    st.error(f"Failed to label image: {error_msg}")
                                    # If the error is about model confidence, show a more user-friendly message
                                    if "Model confidence too low" in error_msg:
                                        st.info("The AI model wasn't confident enough to determine a label for this image.")

                    with remove_col:
                        # Remove label button
                        st.write("") # Add space to align with selectbox
                        if st.button(f"{self.const.ICONS['delete']}", key=f"remove_label_btn_{post_id}", help="Remove label"):
                            if self.backend.remove_post_label(post_id):
                                st.success("Label removed successfully")
                                st.rerun()
                            else:
                                st.error("Failed to remove label")

                    # Handle label update when selection changes
                    if selected_label != current_label and selected_label != "-- Select --":
                        try:
                            label_success = self.backend.set_post_label(post_id, selected_label)
                            if label_success:
                                st.success(f"{self.const.ICONS['success']} Label updated")
                                st.rerun()
                        except Exception as e:
                            st.error(f"{self.const.ICONS['error']} Error saving label: {str(e)}")
                except Exception as e:
                    st.error(f"Error loading labels: {str(e)}")

                # Custom label input field
                label_input_col, label_btn_col = st.columns([3, 1])
                with label_input_col:
                    new_label = st.text_input(
                        "Add custom label",
                        key=f"detail_new_custom_label_{post_id}",
                        placeholder="Add custom label",
                        label_visibility="collapsed"
                    )

                with label_btn_col:
                    if st.button(f"{self.const.ICONS['add']}", key=f"detail_add_label_btn_{post_id}", help="Add label", use_container_width=True):
                        new_label_stripped = new_label.strip()
                        if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']:
                            st.session_state['custom_labels'].append(new_label_stripped)
                            st.success(f"Added '{new_label_stripped}'")
                            st.rerun()
                        elif not new_label_stripped:
                            st.warning("Label cannot be empty")
                        else:
                            st.warning(f"Label already exists")

        with col2:
            # Post details - Caption
            st.write("")  # Add some spacing
            st.markdown('<div class="mini-header">Caption</div>', unsafe_allow_html=True)
            caption = post.get('caption', 'No caption available')

            st.markdown(f'<div style="margin-bottom:20px;">{caption}</div>', unsafe_allow_html=True)

            # Admin Explanation section
            st.write("")  # Add some spacing

            # Get existing admin explanation
            try:
                current_explanation = self.backend.get_post_admin_explanation(post_id)

                # Create a form for the admin explanation
                with st.form(key=f"admin_explanation_form_{post_id}", border=False):
                    # Text area for explanation
                    explanation = st.text_area(
                        "Explain",
                        value=current_explanation if current_explanation else "",
                        placeholder="Add an explanation for this post",
                        key=f"admin_explanation_{post_id}"
                    )

                    # Buttons row
                    exp_col1, exp_col2 = st.columns(2)

                    with exp_col1:
                        # Save button
                        save_exp_button = st.form_submit_button(
                            f"{self.const.ICONS['save']} Save Explanation",
                            use_container_width=True
                        )

                    with exp_col2:
                        # Remove button
                        remove_exp_button = st.form_submit_button(
                            f"{self.const.ICONS['delete']} Remove Explanation",
                            type="secondary",
                            use_container_width=True
                        )

                    if save_exp_button:
                        if explanation.strip():
                            try:
                                success = self.backend.set_post_admin_explanation(post_id, explanation.strip())
                                if success:
                                    st.success(f"{self.const.ICONS['success']} Explanation saved!")
                                    st.rerun()
                                else:
                                    st.error(f"{self.const.ICONS['error']} Failed to save explanation")
                            except Exception as e:
                                st.error(f"{self.const.ICONS['error']} Error saving explanation: {str(e)}")
                        else:
                            st.warning("Explanation cannot be empty")

                    if remove_exp_button:
                        try:
                            success = self.backend.remove_post_admin_explanation(post_id)
                            if success:
                                st.success("Explanation removed")
                                st.rerun()
                            else:
                                st.error("Failed to remove explanation")
                        except Exception as e:
                            st.error(f"Error removing explanation: {str(e)}")

            except Exception as e:
                st.error(f"Error loading admin explanation: {str(e)}")

            # Fixed response editing functionality (moved below metadata)
            st.write("")  # Add some spacing
            st.markdown('<div class="mini-header">Fixed Response</div>', unsafe_allow_html=True)

            # Get existing fixed response using backend
            try:
                # This is expected to be a list of response dictionaries
                raw_responses_data = self.backend.get_post_fixed_responses(post_id)
            except Exception as e:
                raw_responses_data = None # Ensure it's None on error
                st.error(f"Error loading fixed responses: {str(e)}")

            # Create tabs for existing and adding responses
            exist_tab, add_tab = st.tabs(["Existing", "Add New"])

            with exist_tab:
                fixed_responses_to_display = []
                if isinstance(raw_responses_data, list):
                    fixed_responses_to_display = raw_responses_data
                elif isinstance(raw_responses_data, dict) and raw_responses_data: # Handle if backend returns a single dict
                    fixed_responses_to_display = [raw_responses_data]

                if not fixed_responses_to_display:
                    st.info("No fixed responses exist for this post. Use the 'Add New' tab to create one.")
                else:
                    for index, response_item in enumerate(fixed_responses_to_display):
                        if not isinstance(response_item, dict):
                            st.warning(f"Skipping an invalid fixed response item (item {index + 1}).")
                            continue

                        st.markdown("---") # Visual separator for each response
                        # Use a unique key for each form, including post_id and index
                        form_key = f"existing_response_form_{post_id}_{index}"
                        original_trigger_keyword = response_item.get("trigger_keyword", "")

                        with st.form(key=form_key, border=True):
                            st.markdown(f"**Response for Trigger: \"{original_trigger_keyword}\"**" if original_trigger_keyword else f"**Response Item {index+1}**")

                            trigger_keyword_input = st.text_input(
                                "Trigger keyword",
                                value=original_trigger_keyword,
                                key=f"trigger_{form_key}"
                            )
                            comment_response_input = st.text_area(
                                "Comment reply",
                                value=response_item.get("comment_response_text", ""),
                                key=f"comment_{form_key}"
                            )
                            dm_response_input = st.text_area(
                                "DM reply",
                                value=response_item.get("direct_response_text", ""),
                                key=f"dm_{form_key}"
                            )

                            # Row for buttons
                            col_update, col_delete = st.columns(2)
                            with col_update:
                                update_button = st.form_submit_button(f"{self.const.ICONS['save']} Update This Response", use_container_width=True)
                            with col_delete:
                                delete_button = st.form_submit_button(
                                    f"{self.const.ICONS['delete']} Remove This Response",
                                    type="secondary",
                                    use_container_width=True
                                )

                            if update_button:
                                new_trigger_keyword = trigger_keyword_input.strip()
                                if not new_trigger_keyword:
                                    st.error("Trigger keyword is required.")
                                else:
                                    success = self.backend.create_or_update_post_fixed_response(
                                        post_id=post_id,
                                        trigger_keyword=new_trigger_keyword,
                                        comment_response_text=comment_response_input.strip() or None,
                                        direct_response_text=dm_response_input.strip() or None
                                    )
                                    if success:
                                        st.success(f"Response for '{new_trigger_keyword}' processed successfully!")
                                        if original_trigger_keyword and original_trigger_keyword != new_trigger_keyword:
                                            st.info(f"Content previously associated with '{original_trigger_keyword}' is now under '{new_trigger_keyword}'. The old trigger entry might still exist if not explicitly managed by the backend as a 'rename'.")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to process response for '{new_trigger_keyword}'.")

                            if delete_button:
                                if not original_trigger_keyword:
                                    st.error("Cannot delete response: Original trigger keyword is missing.")
                                else:
                                    try:
                                        success = self.backend.delete_post_fixed_response(post_id, original_trigger_keyword)
                                        if success:
                                            st.success(f"Response for '{original_trigger_keyword}' removed successfully.")
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to remove response for '{original_trigger_keyword}'.")
                                    except Exception as e:
                                        st.error(f"Error removing response: {str(e)}")

            with add_tab:
                # Form for adding new fixed response
                try:
                    # Set up form
                    with st.form(key=f"new_response_form_{post_id}", border=False):

                        # Trigger keyword
                        new_trigger_keyword = st.text_input(
                            "Trigger keyword",
                            placeholder="Enter words that will trigger this response"
                        )

                        # Comment response
                        new_comment_response = st.text_area(
                            "Comment reply",
                            placeholder="Response to post when someone comments with trigger words"
                        )

                        # Direct message response
                        new_dm_response = st.text_area(
                            "DM reply",
                            placeholder="Response sent as DM when someone messages with trigger words"
                        )

                        # Submit button to save fixed response
                        new_submit_button = st.form_submit_button(f"{self.const.ICONS['add']} Create", use_container_width=True)

                        if new_submit_button:
                            # Handle adding new fixed response using backend
                            try:
                                if new_trigger_keyword.strip():
                                    new_success = self.backend.create_or_update_post_fixed_response(
                                        post_id=post_id,
                                        trigger_keyword=new_trigger_keyword.strip(),
                                        comment_response_text=new_comment_response.strip() if new_comment_response.strip() else None,
                                        direct_response_text=new_dm_response.strip() if new_dm_response.strip() else None
                                    )
                                    if new_success:
                                        st.success(f"{self.const.ICONS['success']} Created!")
                                        st.rerun()
                                else:
                                    st.error("Trigger keyword is required")
                            except Exception as e:
                                st.error(f"{self.const.ICONS['error']} Error creating: {str(e)}")

                except Exception as e:
                    st.error(f"Error loading form: {str(e)}")


#===============================================================================================================================
class AdminUI:
    """Main application container"""
    def __init__(self, client_username):
        st.set_page_config(layout="wide", page_title="Admin Dashboard")

        # Initialize session state variables for authentication
        if 'authenticated' not in st.session_state:
            st.session_state['authenticated'] = False
        if 'username' not in st.session_state:
            st.session_state['username'] = None

        try:
            # Determine backend context: admin or client
            username = st.session_state.get('username')
            if username and username != 'admin':
                self.backend = Backend(client_username=username)
            else:
                self.backend = Backend()

            # Initialize the default admin user if needed
            self.backend.ensure_default_admin()

            # Check for authentication token on startup
            self._check_auth_token()
        except NameError:
            st.error("Backend class definition not found. Please ensure it's defined or imported.")
            # Define a DummyBackend to allow the UI to run for demonstration if Backend is missing
            class DummyBackend:
                def __getattr__(self, name):
                    def method(*args, **kwargs):
                        print(f"DummyBackend: Method '{name}' called with args={args}, kwargs={kwargs}")
                        if name == 'get_app_setting': return "true"
                        if name == 'get_labels': return {}
                        if name == 'get_posts': return []
                        if name == 'get_products': return []
                        if name == 'get_additionalinfo': return []
                        if name == 'get_vs_id': return "dummy_vs_id"
                        if name == 'get_assistant_instructions': return "Dummy instructions"
                        if name == 'get_assistant_temperature': return 0.7
                        if name == 'get_assistant_top_p': return 1.0
                        if name == 'create_chat_thread': return "dummy_thread_id"
                        if name == 'format_updated_at': return "recently"
                        if name == 'authenticate_admin': return True
                        if name == 'get_admin_users': return []
                        if name == 'create_admin_user': return True
                        if name == 'update_admin_password': return True
                        if name == 'update_admin_status': return True
                        if name == 'delete_admin_user': return True
                        if name == 'ensure_default_admin': return True
                        if name == 'create_auth_token': return "dummy_token"
                        if name == 'verify_auth_token': return None
                        # Add other dummy methods as needed by your sections
                        return None
                    return method
            self.backend = DummyBackend()

        # Map section titles to their respective classes
        self.section_mapping = {
            "Dashboard": AppStatusSection(self.backend),
            "Data": ProductScraperSection(self.backend),
            "GPT": OpenAIManagementSection(self.backend),
            "Instagram": InstagramSection(self.backend)
        }

        # Initialize session state for the selected page if it doesn't exist
        if 'selected_page' not in st.session_state:
            st.session_state.selected_page = "Dashboard" # Default page

    def _check_auth_token(self):
        """Check if an authentication token is present and valid"""
        if 'auth_token' in st.session_state:
            # For security reasons, prioritize session state over cookies
            return

        auth_token = st.query_params.get('auth_token')
        if auth_token and len(auth_token) > 0:
            username = self.backend.verify_auth_token(auth_token)
            if username:
                st.session_state['authenticated'] = True
                st.session_state['username'] = username
                st.session_state['auth_token'] = auth_token

    def render(self):
        """Render all application sections based on authentication status"""
        # Check if user is authenticated
        if not st.session_state['authenticated']:
            self._render_login_page()
        else:
            # Set auth token in query params if not already there
            if 'auth_token' in st.session_state:
                if 'auth_token' not in st.query_params:
                    st.query_params['auth_token'] = st.session_state['auth_token']
            self._render_authenticated_ui()

    def _render_login_page(self):
        """Display login page for unauthenticated users"""
        const = AppConstants()

        st.title(f"{const.ICONS['login']} Admin Login")

        # Center the login form
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            with st.form("login_form"):
                st.subheader("Please sign in")
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Login", use_container_width=True)

                if submitted:
                    if not username or not password:
                        st.error("Please enter both username and password.")
                    else:
                        # Authenticate user via backend
                        if self.backend.authenticate_admin(username, password):
                            # Create authentication token
                            auth_token = self.backend.create_auth_token(username)

                            # Store in session state
                            st.session_state['authenticated'] = True
                            st.session_state['username'] = username
                            st.session_state['auth_token'] = auth_token

                            # Set in query params for persistence
                            st.query_params['auth_token'] = auth_token

                            # After successful login, clear the toggle keys
                            for key in ['assistant_toggle', 'fixed_responses_toggle']:
                                if key in st.session_state:
                                    del st.session_state[key]

                            st.rerun()
                        else:
                            st.error("Invalid username or password.")

            # Add a note about default credentials
            st.info("If this is your first time logging in, use the default credentials:\nUsername: admin\nPassword: admin123\n\nPlease change the password immediately after login.")

    def _render_authenticated_ui(self):
        """Render the main UI for authenticated users"""
        # Add custom CSS for sidebar
        st.markdown("""
        <style>
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
            padding-top: 1.5rem;
        }
        div[role="radiogroup"] {
            margin-top: 1.5rem !important;
        }
        div[role="radiogroup"] label {
            padding: 0.6rem 0 !important;
            font-weight: 600 !important;
            font-size: 1.05rem !important;
            margin-bottom: 0.5rem !important;
        }
        .sidebar-header {
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 1rem;
            color: #4b4b4b;
        }
        .sidebar-welcome {
            font-size: 0.9rem;
            margin-bottom: 0.7rem;
            color: #5a5a5a;
            font-weight: 500;
        }
        .sidebar-divider {
            margin-top: 1.5rem;
            margin-bottom: 1.5rem;
            border-top: 1px solid #e0e0e0;
        }
        .logout-button {
            margin-top: 0.5rem;
        }
        </style>
        """, unsafe_allow_html=True)

        # Add logout button to sidebar
        const = AppConstants()

        # Use styled headers instead of built-in title
        st.sidebar.markdown('<div class="sidebar-header">Navigation</div>', unsafe_allow_html=True)

        # Welcome message with styled text
        st.sidebar.markdown(f'<div class="sidebar-welcome">Welcome, {st.session_state["username"]}!</div>', unsafe_allow_html=True)

        # Logout button with custom styling
        logout_col = st.sidebar.columns(1)[0]
        with logout_col:
            if st.button(f"{const.ICONS['logout']} Logout", key="logout_button", use_container_width=True, type="secondary"):
                # Reset authentication state
                st.session_state['authenticated'] = False
                st.session_state['username'] = None
                if 'auth_token' in st.session_state:
                    del st.session_state['auth_token']
                # Clear query params
                st.query_params.clear()
                # After logout, clear the toggle keys
                for key in ['assistant_toggle', 'fixed_responses_toggle']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

        # Add a visual divider
        st.sidebar.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        # Create radio buttons in the sidebar for section selection
        st.session_state.selected_page = st.sidebar.radio(
            "Navigation Menu",  # Provide descriptive label for accessibility
            options=list(self.section_mapping.keys()),
            key="navigation_radio",
            label_visibility="collapsed"  # Hide the label completely
        )

        # Retrieve the selected section object
        selected_section_title = st.session_state.selected_page
        section_to_render = self.section_mapping.get(selected_section_title)

        # Render the selected section
        if section_to_render:
            section_to_render.render()
        else:
            st.error("Page not found. Please select a section from the sidebar.")

if __name__ == "__main__":
    app = AdminUI(client_username="your_username")
    app.render()