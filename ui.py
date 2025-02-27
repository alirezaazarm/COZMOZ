import streamlit as st
from app.services.backend import Backend
from app.services.scraper import CozmozScraper
from app.services.openai_service import OpenAIService
import json

backend = Backend()
scraper = CozmozScraper()
openai_service = OpenAIService()
# ======================================= EMOJY SHORT CODES ====================================================== #
ICON_SCRAPER = ":building_construction:"  # 🏗️
ICON_SCRAPE = ":rocket:"          # 🚀
ICON_UPDATE = ":arrows_counterclockwise:"  # 🔄
ICON_VS = ":brain:"               # 🧠
ICON_DELETE = ":wastebasket:"     # 🗑️
ICON_ADD = ":heavy_plus_sign:"    # ➕
ICON_TRANSLATE = ":earth_asia:"   # 🌍
ICON_AI = ":robot_face:"          # 🤖
ICON_SUCCESS = ":white_check_mark:"  # ✅
ICON_ERROR = ":x:"                # ❌
ICON_PREVIEW = ":package:"        # 📦
# =========================================== APP SETTINGS ======================================================= #
st.header("App Status")

try:
    # Fetch current app settings
    assist_status = backend.get_app_setting("assistant")
    fixed_responses_status = backend.get_app_setting("fixed_responses")

    # Toggle for Assistant
    assistant_toggle = st.toggle(
        label=f"{ICON_SUCCESS} Enable Assistant",
        value=(assist_status == "true"),
        key="assistant_toggle"
    )
    if assistant_toggle and assist_status != "true":
        backend.update_is_active(key="assistant", value="true")
        st.success(f"{ICON_SUCCESS} Assistant enabled successfully!")
    elif not assistant_toggle and assist_status != "false":
        backend.update_is_active(key="assistant", value="false")
        st.success(f"{ICON_ERROR} Assistant disabled successfully!")

    # Toggle for Fixed Responses
    fixed_responses_toggle = st.toggle(
        label=f"{ICON_SUCCESS} Enable Fixed Responses",
        value=(fixed_responses_status == "true"),
        key="fixed_responses_toggle"
    )
    if fixed_responses_toggle and fixed_responses_status != "true":
        backend.update_is_active(key="fixed_responses", value="true")
        st.success(f"{ICON_SUCCESS} Fixed Responses enabled successfully!")
    elif not fixed_responses_toggle and fixed_responses_status != "false":
        backend.update_is_active(key="fixed_responses", value="false")
        st.success(f"{ICON_ERROR} Fixed Responses disabled successfully!")

except RuntimeError as e:
    st.error(f"Error managing app status: {str(e)}")
st.write("---")
# ========================================= PRODUCTS SCRAPER ============================================================== #
st.header(f"{ICON_SCRAPER} Product Scraper")
col1, col2 = st.columns(2)
with col1:
    if st.button(f"{ICON_SCRAPE} Scrape All Products", help="Scrape all products from scratch"):
        try:
            with st.spinner("Scraping all products. This may take several minutes..."):
                scraper.scrape_products()
                st.success(f"{ICON_SUCCESS} Scraping completed!")
                st.rerun()
        except Exception as e:
            st.error(f"{ICON_ERROR} Scraping failed: {str(e)}")

with col2:  # Update Products button
    if st.button(f"{ICON_UPDATE} Update Products", help="Add new products only"):
        try:
            with st.spinner("Checking for new products..."):
                scraper.update_products()
                st.success(f"{ICON_SUCCESS} Update completed!")
                st.rerun()
        except Exception as e:
            st.error(f"{ICON_ERROR} Update failed: {str(e)}")

# Update the product preview to show translations
st.subheader(f"{ICON_PREVIEW} Product table")
try:
    products = backend.get_products()
    if products:
        st.dataframe(
            products,
            column_config={
                "Link": st.column_config.LinkColumn("Product Link"),
                "Vector Store ID": "VS ID",
                "File ID": "File ID",
            },
            use_container_width=True,
            height=400
        )
    else:
        st.info("No products found. Click 'Scrape All Products' to get started!")
except Exception as e:
    st.error(f"Failed to load products: {str(e)}")

# ============================================= OPENAI ==================================================================== #
st.header(f"{ICON_AI} OpenAI Management")
openai_service = OpenAIService()

if st.button(f"{ICON_VS} Process All Products",
             help="Generate File IDs, Vector Store IDs, and Translated Titles for all products"):
    try:
        with st.spinner("Processing products - this may take several minutes..."):
            translate_success = openai_service.translate_titles()
            vs_success = openai_service.create_vs()

            if vs_success and translate_success:
                st.success(f"{ICON_SUCCESS} All products processed successfully!")
                st.rerun()
            else:
                st.error(f"{ICON_ERROR} Some operations failed. Check logs for details.")
    except Exception as e:
        st.error(f"Processing failed: {str(e)}")

st.write("---")
#=========================================== FIXED RESPONSES ===============================================================#
st.header("Fixed Responses")

# Incoming Toggle: Direct or Comment
incoming_type = st.radio(
    "Select Incoming Type",
    options=["Direct", "Comment"],
    index=0,
    horizontal=True,
    key="incoming_type"
)

# Tabs for Existing and Add New
existing_tab, add_new_tab = st.tabs(["Existing", "Add New"])
st.write("---")

# Existing Responses Subsection
with existing_tab:
    st.subheader(f"Existing {incoming_type} Fixed Responses")
    try:
        # Fetch fixed responses based on incoming type
        responses = backend.get_fixed_responses(incoming=incoming_type)

        if responses:
            for resp in responses:
                with st.container():
                    # Display the updated time
                    updated_time = backend.format_updated_at(resp.get("updated_at"))
                    st.markdown(f"Updated {updated_time}")

                    # Trigger keyword input
                    trigger = st.text_input(
                        "Trigger",
                        value=resp["trigger_keyword"],
                        key=f"trigger_{resp['id']}"
                    )

                    if incoming_type == "Direct":
                        # For Direct, only show the Direct Response Text field
                        direct_text = st.text_area(
                            "Direct Response Text",
                            value=resp["direct_response_text"] or "",
                            key=f"direct_text_{resp['id']}",
                            height=100
                        )
                        col1, col2 = st.columns([1, 1])

                        # Save button
                        with col1:
                            if st.button("Save", key=f"save_{resp['id']}"):
                                try:
                                    backend.update_fixed_response(
                                        resp["id"],
                                        trigger,
                                        comment_response_text=None,  # No comment for Direct
                                        direct_response_text=direct_text,
                                        incoming="Direct"
                                    )
                                    st.success("Fixed response updated successfully!")
                                    st.rerun()
                                except RuntimeError as e:
                                    st.error(str(e))

                        # Delete button
                        with col2:
                            if st.button(":wastebasket:", key=f"delete_{resp['id']}"):
                                try:
                                    backend.delete_fixed_response(resp["id"])
                                    st.success("Fixed response deleted successfully!")
                                    st.rerun()
                                except RuntimeError as e:
                                    st.error(str(e))

                    elif incoming_type == "Comment":
                        # For Comment, show toggles for Direct and Comment
                        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

                        # Toggles for Direct and Comment
                        with col1:
                            direct_toggle = st.toggle(
                                "Direct",
                                value=bool(resp["direct_response_text"]),  # Sync with database
                                key=f"direct_toggle_{resp['id']}"
                            )
                        with col2:
                            comment_toggle = st.toggle(
                                "Comment",
                                value=bool(resp["comment_response_text"]),  # Sync with database
                                key=f"comment_toggle_{resp['id']}"
                            )

                        # Dynamically show text fields based on toggles
                        if direct_toggle:
                            direct_text = st.text_area(
                                "Direct Response Text",
                                value=resp["direct_response_text"] or "",
                                key=f"direct_text_{resp['id']}",
                                height=100
                            )
                        else:
                            direct_text = None

                        if comment_toggle:
                            comment_text = st.text_area(
                                "Comment Response Text",
                                value=resp["comment_response_text"] or "",
                                key=f"comment_text_{resp['id']}",
                                height=100
                            )
                        else:
                            comment_text = None

                        # Save button
                        with col3:
                            if st.button("Save", key=f"save_{resp['id']}"):
                                try:
                                    backend.update_fixed_response(
                                        resp["id"],
                                        trigger,
                                        comment_response_text=comment_text,
                                        direct_response_text=direct_text,
                                        incoming="Comment"
                                    )
                                    st.success("Fixed response updated successfully!")
                                    st.rerun()
                                except RuntimeError as e:
                                    st.error(str(e))

                        # Delete button
                        with col4:
                            if st.button(":wastebasket:", key=f"delete_{resp['id']}"):
                                try:
                                    backend.delete_fixed_response(resp["id"])
                                    st.success("Fixed response deleted successfully!")
                                    st.rerun()
                                except RuntimeError as e:
                                    st.error(str(e))
                st.write("---")  # Divider between cards
        else:
            st.info(f"No {incoming_type.lower()} fixed responses available.")
    except RuntimeError as e:
        st.error(str(e))

# Add New Response Subsection
with add_new_tab:
    st.subheader(f"Add New {incoming_type} Response")
    new_trigger = st.text_input("New Trigger", key="new_trigger")

    if incoming_type == "Direct":
        # For Direct, only show the Direct Response Text field
        new_direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=100)
        new_comment_text = None  # No comment for Direct

    elif incoming_type == "Comment":
        # For Comment, show toggles for Direct and Comment
        col1, col2, _ = st.columns([1, 1, 1])
        with col1:
            new_direct_toggle = st.toggle("Direct", value=False, key="new_direct_toggle")
        with col2:
            new_comment_toggle = st.toggle("Comment", value=False, key="new_comment_toggle")

        # Dynamically show text fields based on toggles
        if new_direct_toggle:
            new_direct_text = st.text_area("Direct Response Text", key="new_direct_text", height=100)
        else:
            new_direct_text = None

        if new_comment_toggle:
            new_comment_text = st.text_area("Comment Response Text", key="new_comment_text", height=100)
        else:
            new_comment_text = None

    if st.button("Add Response", key="add_response_button"):
        if new_trigger:
            try:
                backend.add_fixed_response(
                    new_trigger,
                    comment_response_text=new_comment_text if incoming_type == "Comment" else None,
                    direct_response_text=new_direct_text,
                    incoming=incoming_type
                )
                st.rerun()
                st.success("Fixed response added successfully!")
            except RuntimeError as e:
                st.error(str(e))
        else:
            st.error("Trigger is required.")