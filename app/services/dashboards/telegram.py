import logging
import streamlit as st
from datetime import datetime, timedelta, timezone
from ...models.user import User
from ...models.client import Client
import pandas as pd
import plotly.express as px
from ...services.platforms.telegram import TelegramService
from ...models.enums import MessageRole, UserStatus

logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
#===============================================================================================================================
class AppConstants:
    """Centralized configuration for icons and messages"""
    ICONS = {
        "scraper": ":building_construction:",
        "scrape": ":rocket:",
        "update": ":arrows_counterclockwise:",
        "ai": ":robot_face:",
        "delete": ":wastebasket:",
        "add": ":heavy_plus_sign:",
        "success": ":white_check_mark:",
        "error": ":x:",
        "preview": ":package:",
        "brain": ":brain:",
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
        "dashboard": ":bar_chart:",
        "data": ":page_facing_up:",
        "login": ":key:",
        "logout": ":door:",
        "user": ":bust_in_silhouette:", # Switched to shortcode for reliability
        "magic": ":magic_wand:",
        "controller": ":airplane:", # Added controller icon
        "default_user": "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_960_720.png"
    }

    MESSAGES = {
        "scraping_start": "Scraping all products. This may take several minutes...",
        "update_start": "Checking for new products...",
        "processing_start": "Processing products - this may take several minutes..."
    }

class TelegramBackend:
    """Backend logic for Telegram analytics."""
    def __init__(self, client_username=None):
        self.client_username = client_username
        logging.info(f"TelegramBackend initialized for client: {self.client_username}")

    def get_message_statistics_by_role_within_timeframe_by_platform(self, time_frame, start_datetime, end_datetime, platform):
        return User.get_message_statistics_by_role_within_timeframe_by_platform(
            time_frame, start_datetime, end_datetime, platform, self.client_username
        )

    def get_user_status_counts_within_timeframe_by_platform(self, start_datetime, end_datetime, platform):
        return User.get_user_status_counts_within_timeframe_by_platform(
            start_datetime, end_datetime, platform, self.client_username
        )

    def get_total_users_count_within_timeframe_by_platform(self, start_datetime, end_datetime, platform):
        return User.get_total_users_count_within_timeframe_by_platform(
            start_datetime, end_datetime, platform, self.client_username
        )

    def get_user_status_counts_by_platform(self, platform):
        return User.get_user_status_counts_by_platform(platform, self.client_username)

    def get_total_users_count_by_platform(self, platform):
        return User.get_total_users_count_by_platform(platform, self.client_username)

    def get_all_users(self):
        return User.get_users_by_platform_for_client("telegram", self.client_username)

    def get_user_messages(self, user_id):
        return User.get_user_messages(user_id, client_username=self.client_username, limit=100)
    
    def get_user_by_id(self, user_id):
        return User.get_by_id(user_id, client_username=self.client_username)

class BaseSection:
    """Base class for UI sections"""
    def __init__(self, client_username=None):
        self.client_username = client_username
        self.const = AppConstants()
        self.backend = TelegramBackend(client_username=self.client_username)
#===============================================================================================================================

class TelegramUI(BaseSection):
    def __init__(self, client_username=None):
        super().__init__(client_username)
        self.client_username = client_username
        if 'selected_telegram_user' not in st.session_state:
            st.session_state.selected_telegram_user = None
        if 'selected_telegram_user_data' not in st.session_state:
            st.session_state.selected_telegram_user_data = None

    def render(self):
        self._render_controller_panel()
        st.write("---")
        
        statistics_tab, chat_tab = st.tabs([f"{self.const.ICONS['dashboard']} Statistics", f"{self.const.ICONS['chat']} Chat"])
        
        with statistics_tab:
            # --- Centralized Controls ---
            col1, col2, col3 = st.columns([2, 2, 1])
            key_suffix = "telegram_stats"
            with col1:
                time_frame = st.selectbox("Time Frame", options=["daily", "hourly"], index=1, key=f"time_frame_{key_suffix}")
            with col2:
                duration_options = {"1 day": 1, "7 days": 7, "1 month": 30, "3 months": 90, "All time": 0}
                selected_duration = st.selectbox("Duration", options=list(duration_options.keys()), index=0, key=f"duration_{key_suffix}")
                days_back = duration_options[selected_duration]
            with col3:
                st.markdown("_")
                if st.button(f"{self.const.ICONS['update']} Refresh", key=f"refresh_{key_suffix}", width='stretch'):
                    st.rerun()
            
            end_datetime = datetime.now(timezone.utc)
            start_datetime = end_datetime - timedelta(days=days_back)
            # --- End of Centralized Controls ---

            st.write("---")
            self._render_message_analytics(time_frame, start_datetime, end_datetime, days_back)
            st.write("---")
            self._render_user_statistics(start_datetime, end_datetime, days_back)

        with chat_tab:
            self._render_chat_history()
        
    def _render_controller_panel(self):
        """Render Telegram platform controller panel with improved UI."""
        with st.container(border=True):
            
            try:
                platform_config = Client.get_client_platforms_config(self.client_username)
                telegram_config = platform_config.get('telegram', {})
                
                platform_enabled = telegram_config.get('enabled', False)
                new_platform_enabled = st.toggle(
                    "Enable Telegram Platform", 
                    value=platform_enabled, 
                    key="telegram_platform_enable"
                )
                
                if new_platform_enabled != platform_enabled:
                    if Client.update_platform_enabled_status(self.client_username, 'telegram', new_platform_enabled):
                        st.success(f"Telegram platform {'enabled' if new_platform_enabled else 'disabled'} successfully")
                        st.rerun()
                    else:
                        st.error("Failed to update Telegram platform status")
                
                if new_platform_enabled:
                    st.markdown("##### Module Controls")
                    modules = telegram_config.get('modules', {})
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fixed_response_enabled = modules.get('fixed_response', {}).get('enabled', False)
                        new_fixed_response = st.toggle(
                            "Fixed Response", 
                            value=fixed_response_enabled, 
                            key="telegram_fixed_response"
                        )
                        if new_fixed_response != fixed_response_enabled:
                            if Client.update_module_status(self.client_username, 'telegram', 'fixed_response', new_fixed_response):
                                st.success(f"Fixed Response {'enabled' if new_fixed_response else 'disabled'}")
                                st.rerun()
                            else:
                                st.error("Failed to update Fixed Response")
                    
                    with col2:
                        dm_assist_enabled = modules.get('dm_assist', {}).get('enabled', False)
                        new_dm_assist = st.toggle("DM Assist", value=dm_assist_enabled, key="telegram_dm_assist")
                        if new_dm_assist != dm_assist_enabled:
                            if Client.update_module_status(self.client_username, 'telegram', 'dm_assist', new_dm_assist):
                                st.success(f"DM Assist {'enabled' if new_dm_assist else 'disabled'}")
                                st.rerun()
                            else:
                                st.error("Failed to update DM Assist")
                else:
                    st.info("Enable the Telegram platform to access module controls.")
            except Exception as e:
                st.error(f"Error rendering controller panel: {str(e)}")

    def _render_message_analytics(self, time_frame, start_datetime, end_datetime, days_back):
        with st.container(border=True):
            if days_back == 0:
                st.info("Please select a specific duration (e.g., '1 day', '7 days') to view message analytics.")
                return
            
            try:
                message_stats = self.backend.get_message_statistics_by_role_within_timeframe_by_platform(time_frame, start_datetime, end_datetime, "telegram")
                
                if not message_stats:
                    st.info("No message data available for the selected time period.")
                    return

                df = pd.DataFrame(
                    [{"Date": date_str, "Role": role, "Count": count} for date_str, roles in message_stats.items() for role, count in roles.items()]
                )
                if df.empty:
                    st.info("No message data to display.")
                    return
                
                summary_counts = df.groupby('Role')['Count'].sum()
                
                user_msgs = int(summary_counts.get('user', 0))
                assistant_msgs = int(summary_counts.get('assistant', 0))
                admin_msgs = int(summary_counts.get('admin', 0))
                fixed_responses = int(summary_counts.get('fixed_response', 0))
                
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("User Messages", user_msgs)
                m_col2.metric("Assistant Messages", assistant_msgs)
                m_col3.metric("Admin Messages", admin_msgs)
                m_col4.metric("Fixed Responses", fixed_responses)
                st.write("---")
                # --- End of Summary Metrics ---
                
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.sort_values('Date')

                fig = px.bar(df, x='Date', y='Count', color='Role', title='Direct Messages by Role', color_discrete_map={'user': '#1f77b4', 'assistant': '#ff7f0e', 'admin': '#2ca02c', 'fixed_response': '#d62728'})
                
                if time_frame == "hourly":
                    fig.update_xaxes(tickformat="%Y-%m-%d %H:%M", title_text="Time")
                else:
                    fig.update_xaxes(tickformat="%Y-%m-%d", title_text="Date")
                
                fig.update_yaxes(title_text="Number of Messages")
                
                st.plotly_chart(fig, width='stretch')
                
            except Exception as e:
                st.error(f"Error rendering message analytics: {str(e)}")

    def _render_user_statistics(self, start_datetime, end_datetime, days_back):
        with st.container(border=True):
            try:
                if days_back > 0:
                    status_counts = self.backend.get_user_status_counts_within_timeframe_by_platform(start_datetime, end_datetime, "telegram")
                else:
                    status_counts = self.backend.get_user_status_counts_by_platform("telegram")

                filtered_counts = {k: v for k, v in (status_counts or {}).items() if k.upper() != 'SCRAPED'}
                if not filtered_counts:
                    st.info("No user status data available for the selected time period.")
                    return

                num_statuses = len(filtered_counts)
                if num_statuses > 0:
                    cols = st.columns(num_statuses)
                    for i, (status, count) in enumerate(filtered_counts.items()):
                        display_status = status.replace("_", " ").title()
                        cols[i].metric(label=display_status, value=count)
                st.write("---")
                # --- End of Summary Metrics ---

                status_df = pd.DataFrame(filtered_counts.items(), columns=['Status', 'Count'])
                fig = px.pie(status_df, values='Count', names='Status', title="User Status Distribution", color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, width='stretch')

            except Exception as e:
                st.error(f"Error rendering user statistics: {str(e)}")

    def _render_chat_history(self):
        try:
            user_list_col, chat_display_col = st.columns([1, 2])
            with user_list_col:
                self._render_user_sidebar()
            with chat_display_col:
                if st.session_state.selected_telegram_user and st.session_state.selected_telegram_user_data:
                    self._display_user_info(st.session_state.selected_telegram_user_data)
                    self._display_chat_messages(st.session_state.selected_telegram_user_data)
                else:
                    with st.container(border=True, height=700):
                        st.info("Select a conversation from the list to view the chat history.")
        except Exception as e:
            st.error(f"Error rendering chat history: {str(e)}")

    def _render_user_sidebar(self):
        with st.container(border=True):
            if st.button(f"{self.const.ICONS['update']} Refresh Users", width='stretch'):
                st.rerun()

            users = self.backend.get_all_users()
            if not users:
                st.info("No Telegram users found.")
                return

            with st.container(height=600):
                for user in users:
                    user_id = user["user_id"]
                    display_name = user.get("username") or f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user_id
                    
                    entry = st.container(border=True)
                    col1, col2 = entry.columns([1, 4])
                    
                    profile_pic = self.const.ICONS["default_user"]
                    col1.image(profile_pic, width=40, clamp=True)

                    if col2.button(display_name, key=f"user_select_{user_id}", width='stretch'):
                        st.session_state.selected_telegram_user = user_id
                        st.session_state.selected_telegram_user_data = self.backend.get_user_by_id(user_id)
                        st.rerun()
    
    def _display_user_info(self, user_data):
        with st.container(border=True):
            username = user_data.get("username", "N/A")
            first_name = user_data.get("first_name", "")
            last_name = user_data.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip() or "N/A"
            is_premium = "Yes" if user_data.get("is_premium") else "No"
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Username", username)
            col2.metric("Full Name", full_name)
            col3.metric("Premium", is_premium)
            

    def _display_chat_messages(self, user_data):
        display_name = user_data.get("username") or user_data.get("first_name", "User")
        
        chat_container = st.container(height=550, border=True)
        with chat_container:
            st.markdown(f"**Chat with {display_name}**")
            messages = self.backend.get_user_messages(user_data["user_id"])
            if not messages:
                st.warning("No messages found for this user.")
            else:
                for msg in messages:
                    role = msg.get("role", "user")
                    display_role = "assistant" if role != "user" else "user"
                    
                    with st.chat_message(display_role):
                        st.markdown(msg.get("text", "*No text content*"))
                        if msg.get("media_url"):
                            st.image(msg["media_url"])
                        
                        timestamp = msg.get("timestamp")
                        if timestamp:
                            st.caption(timestamp.astimezone().strftime('%Y-%m-%d %H:%M'))

        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            text_input = col1.text_input("Type a message...", key=f"chat_input_{user_data['user_id']}", label_visibility="collapsed")
            send_button = col2.button("Send", key=f"send_button_{user_data['user_id']}", width='stretch')

            if send_button and text_input:
                user_id = user_data["user_id"]
                if TelegramService.send_message(user_id, text_input, self.client_username):
                    message_doc = User.create_message_document(
                        text=text_input,
                        role=MessageRole.ADMIN.value
                    )
                    User.add_direct_message(user_id, message_doc, self.client_username)
                    User.update_status(user_id, UserStatus.ADMIN_REPLIED.value, self.client_username)
                    st.success("Message sent and user status updated!")
                    st.rerun()
                else:
                    st.error("Failed to send message.")