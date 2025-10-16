import logging
import streamlit as st
from datetime import datetime, timedelta, timezone
from ...models.user import User
from ...models.client import Client
import pandas as pd
import plotly.express as px
import requests
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
        "broadcast": ":loudspeaker:",
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
        if 'broadcast_results' not in st.session_state:
            st.session_state.broadcast_results = None
        if 'broadcast_message_text' not in st.session_state:
            st.session_state.broadcast_message_text = ""
        if 'broadcast_image_url' not in st.session_state:
            st.session_state.broadcast_image_url = ""

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

    def _render_broadcast_panel(self):
        """Render a broadcast message panel in the chat tab with image support."""
        with st.container(border=True):
            st.markdown("### 📢 Broadcast Message")

            # Initialize session state for broadcast
            if 'broadcast_results' not in st.session_state:
                st.session_state.broadcast_results = None
            if 'broadcast_message_text' not in st.session_state:
                st.session_state.broadcast_message_text = ""
            if 'broadcast_image_url' not in st.session_state:
                st.session_state.broadcast_image_url = ""

            # Image upload/URL section
            st.markdown("#### Attach Image (Optional)")
            image_option = st.radio(
                "Image source:",
                ["No Image", "Upload Image", "Image URL"],
                horizontal=True,
                key="broadcast_image_option"
            )

            image_url = None
            uploaded_file = None

            if image_option == "Upload Image":
                uploaded_file = st.file_uploader(
                    "Choose an image file",
                    type=['jpg', 'jpeg', 'png', 'gif'],
                    key="broadcast_image_upload"
                )
                if uploaded_file:
                    # For now, we'll use a placeholder - in production you'd upload to a CDN
                    st.image(uploaded_file, caption="Preview", width=200)
                    st.info("Image upload functionality needs CDN integration for full implementation")
                    # In a real implementation, you'd upload to S3/Cloud Storage and get URL

            elif image_option == "Image URL":
                image_url = st.text_input(
                    "Image URL:",
                    placeholder="https://example.com/image.jpg",
                    key="broadcast_image_url_input"
                )
                if image_url:
                    try:
                        response = requests.head(image_url, timeout=10)
                        if response.status_code == 200:
                            st.image(image_url, caption="Preview", width=200)
                        else:
                            st.warning("⚠️ Could not load image from URL")
                    except:
                        st.warning("⚠️ Invalid image URL or cannot access")

            # Message input
            broadcast_text = st.text_area(
                "Message to broadcast to all Telegram users:",
                value=st.session_state.broadcast_message_text,
                height=100,
                key="broadcast_text_input",
                placeholder="Enter the message you want to send to all users..."
            )

            # Configuration options
            col1, col2 = st.columns(2)
            with col1:
                batch_size = st.slider(
                    "Messages per batch (to avoid rate limiting):",
                    min_value=10,
                    max_value=100,
                    value=50,
                    step=10,
                    key="broadcast_batch_size"
                )
            with col2:
                delay_between_batches = st.slider(
                    "Delay between batches (seconds):",
                    min_value=0,
                    max_value=5,
                    value=1,
                    step=1,
                    key="broadcast_delay"
                )

            # Action buttons
            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                if st.button(
                    f"{self.const.ICONS['broadcast']} Send Broadcast",
                    key="broadcast_send_button",
                    use_container_width=True,
                    type="primary"
                ):
                    if not broadcast_text.strip():
                        st.error("Please enter a message to broadcast.")
                    else:
                        # Determine image URL to use
                        final_image_url = None
                        if image_option == "Image URL" and image_url:
                            final_image_url = image_url
                        # Note: For file uploads, you'd need to handle file upload to CDN first

                        with st.spinner("Broadcasting message to all users..."):
                            try:
                                results = TelegramService.broadcast_message(
                                    text=broadcast_text,
                                    client_username=self.client_username,
                                    batch_size=batch_size,
                                    delay_between_batches=delay_between_batches,
                                    image_url=final_image_url
                                )
                                st.session_state.broadcast_results = results
                                st.session_state.broadcast_message_text = ""
                                st.session_state.broadcast_image_url = ""
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error during broadcast: {str(e)}")

            with col2:
                if st.button(
                    f"{self.const.ICONS['delete']} Clear",
                    key="broadcast_clear_button",
                    use_container_width=True
                ):
                    st.session_state.broadcast_message_text = ""
                    st.session_state.broadcast_image_url = ""
                    st.session_state.broadcast_results = None
                    st.rerun()

            with col3:
                if st.button(
                    f"{self.const.ICONS['update']} Reset",
                    key="broadcast_reset_button",
                    use_container_width=True
                ):
                    st.session_state.broadcast_results = None
                    st.rerun()

        # Display results if available - FIXED: Check if it exists and is not None
        if (hasattr(st.session_state, 'broadcast_results') and
            st.session_state.broadcast_results is not None):
            self._render_broadcast_results(st.session_state.broadcast_results)

    def _render_broadcast_results(self, results):
        """Render the results of a broadcast operation."""
        with st.container(border=True):
            st.markdown("### 📊 Broadcast Results")

            # Summary metrics
            total_users = results.get('total_users', 0)
            successful = results.get('successful', 0)
            failed = results.get('failed', 0)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Users", total_users)
            col2.metric(f"{self.const.ICONS['success']} Successful", successful, delta=None)
            col3.metric(f"{self.const.ICONS['error']} Failed", failed, delta=None)
            if total_users > 0:
                success_rate = (successful / total_users) * 100
                col4.metric("Success Rate", f"{success_rate:.1f}%")

            st.write("---")

            # Status indicators
            if successful == total_users and total_users > 0:
                st.success(f"✓ All {total_users} users received the message successfully!")
            elif failed == 0 and total_users == 0:
                st.info("No users available for broadcast.")
            elif successful > 0 and failed > 0:
                st.warning(f"⚠ Partial success: {successful}/{total_users} messages sent")
            elif failed == total_users and total_users > 0:
                st.error(f"✗ Failed to send message to all {total_users} users")

            # Failed users list (if any)
            if results.get('failed_users'):
                with st.expander(f"Failed User IDs ({len(results['failed_users'])})"):
                    failed_users_text = "\n".join(results['failed_users'])
                    st.code(failed_users_text, language="text")

            # Error messages (if any)
            if results.get('errors'):
                with st.expander(f"Error Details ({len(results['errors'])})"):
                    for idx, error in enumerate(results['errors'], 1):
                        st.write(f"{idx}. {error}")

            # Export option
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 Download Results as CSV", key="download_broadcast_csv"):
                    import json
                    csv_data = f"""Total Users,Successful,Failed,Success Rate
    {total_users},{successful},{failed},{(successful/total_users)*100 if total_users > 0 else 0:.1f}%

    Failed Users:
    {','.join(results.get('failed_users', []))}
    """
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"broadcast_results_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key="actual_download_csv"
                    )

            with col2:
                if st.button("🔄 New Broadcast", key="new_broadcast_button"):
                    st.session_state.broadcast_results = None
                    st.rerun()

    def _render_chat_history(self):
        """Render chat history with broadcast capability."""
        try:
            # Initialize session state variables at the beginning of the function
            if 'broadcast_results' not in st.session_state:
                st.session_state.broadcast_results = None
            if 'broadcast_message_text' not in st.session_state:
                st.session_state.broadcast_message_text = ""
            if 'broadcast_image_url' not in st.session_state:
                st.session_state.broadcast_image_url = ""

            # Create two main sections: broadcast panel and user chat
            broadcast_tab, user_chat_tab = st.tabs([
                f"{self.const.ICONS['broadcast']} Broadcast",
                f"{self.const.ICONS['chat']} Direct Messages"
            ])

            # Broadcast tab
            with broadcast_tab:
                self._render_broadcast_panel()

            # User chat tab
            with user_chat_tab:
                user_list_col, chat_display_col = st.columns([1, 2])
                with user_list_col:
                    self._render_user_sidebar()
                with chat_display_col:
                    if (hasattr(st.session_state, 'selected_telegram_user') and
                        hasattr(st.session_state, 'selected_telegram_user_data') and
                        st.session_state.selected_telegram_user and
                        st.session_state.selected_telegram_user_data):
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