```markdown
# Instagram Bot/Assistant

This project is a Flask-based application designed to interact with the Instagram platform, primarily through the Instagram Graph API webhooks and background jobs. It acts as an intelligent assistant, processing messages, comments, and reactions, and potentially automating responses or actions based on configured settings and integrations (like OpenAI for generating replies or image processing for content analysis).

## Features

*   **Instagram Webhook Integration:** Receives and processes real-time events from Instagram (messages, comments, reactions).
*   **Message Handling:** Processes direct messages, including text, media (images, reels, posts), and shared content.
*   **Comment Handling:** Processes comments on Instagram posts.
*   **Reaction Handling:** Processes message reactions.
*   **Intelligent Assistant:** Can act as an automated assistant to reply to messages (requires configuration with services like OpenAI).
*   **Image Processing:** Analyzes images shared in messages (potentially using a vision model).
*   **Background Jobs:** Uses APScheduler for scheduled tasks such as:
    *   Processing incoming messages queued in the database.
    *   Cleaning up old processed messages.
    *   Fetching recent posts.
    *   Fetching recent stories.
*   **Database Integration:** Uses MongoDB to store and manage data (messages, users, posts, stories, settings, etc.).
*   **Modular Design:** Structured into blueprints, services, repositories, models, and jobs.

## Project Structure

```
.
├── LICENSE
├── README.md
├── main.py               # Main application entry point
├── requirements.txt      # Python dependencies
├── ui.py                 # (Potentially a separate UI component or script)
├── .idx/                 # (IDE specific files)
├── .vscode/              # VS Code configuration
├── app/
│   ├── __init__.py
│   ├── config.py         # Configuration settings
│   ├── jobs/             # Background jobs/scheduled tasks
│   │   ├── __init__.py
│   │   ├── message_job.py
│   │   ├── post_story_job.py
│   │   └── scheduler.py
│   ├── models/           # Data models (for MongoDB)
│   │   ├── __init__.py
│   │   ├── additional_info.py
│   │   ├── appsettings.py
│   │   ├── database.py
│   │   ├── enums.py
│   │   ├── fixedresponse.py
│   │   ├── post.py
│   │   ├── product.py
│   │   ├── story.py
│   │   └── user.py
│   ├── repositories/     # Database interaction logic
│   │   ├── __init__.py
│   │   ├── assistant_repository.py
│   │   ├── message_repository.py
│   │   └── user_repository.py
│   ├── routes/           # Flask blueprints/API endpoints
│   │   ├── __init__.py
│   │   ├── update.py     # (Likely for manual updates or admin actions)
│   │   └── webhook.py    # Handles incoming Instagram webhook events
│   └── services/         # Business logic and external integrations
│       ├── __init__.py
│       ├── backend.py
│       ├── img_search.py # Image processing/analysis
│       ├── instagram_service.py # Interacts with Instagram API
│       ├── mediator.py   # (Likely orchestrates interactions between services/repos)
│       ├── message_service.py # Handles message processing logic
│       ├── openai_service.py # Interacts with OpenAI API
│       └── scraper.py    # (Potentially for fetching external data)
└── logs.txt              # Application logs
```

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_folder>
    ```

2.  **Set up a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    Create a `.env` file in the root directory or configure environment variables for sensitive information and configuration settings. Minimum required settings will likely include:
    *   `MONGO_URI`: Connection string for your MongoDB database.
    *   `PAGE_ID`: Your Instagram Business Account/Page ID.
    *   `ACCESS_TOKEN`: Your Instagram Graph API Access Token.
    *   `VERIFY_TOKEN`: A token you define for webhook verification.
    *   `APP_ID`: Your Facebook App ID.
    *   `APP_SECRET`: Your Facebook App Secret.
    *   `OPENAI_API_KEY`: Your OpenAI API key (if using the OpenAI service).

    Example `.env` file:
    ```env
    MONGO_URI=mongodb://localhost:27017/instagram_bot
    PAGE_ID=YOUR_PAGE_ID
    ACCESS_TOKEN=YOUR_ACCESS_TOKEN
    VERIFY_TOKEN=YOUR_VERIFY_TOKEN
    APP_ID=YOUR_APP_ID
    APP_SECRET=YOUR_APP_SECRET
    OPENAI_API_KEY=YOUR_OPENAI_API_KEY
    ```

5.  **Set up Instagram Webhooks:**
    Configure webhooks for your Facebook App connected to your Instagram Business Account. The webhook URL should point to your running application's `/webhook` endpoint (e.g., `https://your-domain.com/webhook`). Subscribe to the necessary fields (e.g., `messages`, `comments`, `live_comments`, `message_reactions`).

6.  **Set up MongoDB:**
    Ensure you have a MongoDB instance running and accessible via the `MONGO_URI`.

## How to Run

1.  **Activate your virtual environment:**
    ```bash
    source venv/bin/activate # On Windows use `venv\Scripts\activate`
    ```

2.  **Run the main application file:**
    ```bash
    python main.py
    ```

    The Flask application will start, and the APScheduler jobs will be initialized.

## Key Endpoints

*   `/webhook` (GET/POST): Handles Instagram webhook verification and incoming events.
*   `/update` (POST): (Likely for manual trigger or updates, details depend on implementation in `app/routes/update.py`)

## Background Jobs (via APScheduler)

*   `process_messages_job`: Periodically fetches and processes new messages from the database.
*   `cleanup_processed_messages`: Periodically cleans up old messages marked as processed.
*   `fetch_posts_job`: Periodically fetches recent posts from Instagram.
*   `fetch_stories_job`: Periodically fetches recent stories from Instagram.

## Technologies Used

*   Python
*   Flask
*   APScheduler
*   PyMongo (for MongoDB interaction)
*   Requests (likely for API calls)
*   OpenAI Python Client (if `openai_service` is used)
*   (Potentially other libraries for image processing, etc. - check `requirements.txt`)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```