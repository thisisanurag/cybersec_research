# AI Security & Privacy Analysis Tool

This tool allows researchers to analyze the historical cybersecurity and privacy posture of a given company and its AI algorithms. It works by performing a comprehensive web search for documentation that existed *before* a specified year and uses a Large Language Model (GPT-4o) to analyze the findings.

This guide provides a step-by-step process for setting up and running the tool, even if you have no prior coding experience.

## Prerequisites

Before you begin, you need to have two essential programs installed on your computer:

1.  **Git:** Used to copy the project files. [Download Git here](https://git-scm.com/downloads).
2.  **Python:** The programming language this tool is built on (version 3.8 or newer). [Download Python here](https://www.python.org/downloads/).
    *   **Important for Windows users:** During the Python installation, make sure to check the box that says **"Add Python to PATH"**.

## Setup Instructions

Follow these steps exactly. All commands can be copied and pasted into your terminal application (like Terminal on macOS/Linux or PowerShell/CMD on Windows).

---

### Step 1: Clone the Project

First, copy all the project files from the repository to your computer. This will include the main scripts and the `requirements.txt` file.

```bash
git clone <your-repository-url>
```
*(Replace `<your-repository-url>` with the actual URL of your Git repository)*

---

### Step 2: Navigate to the Project Directory

Move into the newly created folder.

```bash
cd <repository-folder-name>
```
*(The folder name is usually the last part of the repository URL)*

---

### Step 3: Create and Activate a Virtual Environment

This creates a clean, isolated space for this project's specific packages so they don't interfere with other Python projects.

**On macOS or Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate```
*After running the activate command, you should see `(venv)` at the beginning of your terminal prompt.*

---

### Step 4: Install the Required Packages

Now, install all the packages listed in the `requirements.txt` file that came with the project.

```bash
pip install -r requirements.txt
```

---

### Step 5: Set Up Your API Keys

The tool requires API keys from OpenAI and SerpApi to function. These keys are secret and should **never be shared publicly**.

1.  Create a new file named `.env` in the project directory.
2.  Copy and paste the following lines into the `.env` file:

    ```
    OPENAI_API_KEY="PASTE_YOUR_OPENAI_KEY_HERE"
    SERPAPI_KEY="PASTE_YOUR_SERPAPI_KEY_HERE"
    ```
3.  Replace the placeholder text with your actual keys:
    *   Get your OpenAI key from the [OpenAI API keys page](https://platform.openai.com/api-keys).
    *   Get your SerpApi key from the [SerpApi dashboard](https://serpapi.com/manage-api-key).

---

### Step 6: Run the Application

You are now ready to start the backend server.

1.  **Run the Backend:**
    In your terminal (make sure your `(venv)` is still active), run the following command:

    ```bash
    python updated_backend.py
    ```

2.  **Verify it's Running:**
    You should see output that looks like this, which means the server is running successfully:

    ```
     * Serving Flask app 'updated_backend'
     * Running on http://127.0.0.1:5000
    Press CTRL+C to quit
    ```

3.  **Access the Frontend:**
    Do not close the terminal. Open your web browser (like Chrome, Firefox, or Safari) and find the `index.html` file in your project folder. **Double-click the `index.html` file** to open it.

You can now use the tool in your browser!

---

### Step 7: Stopping the Server

When you are finished using the tool, go back to your terminal window and press **`Ctrl + C`** to stop the backend server.