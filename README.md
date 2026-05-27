# Ultimate-data-science-AI-tool

# 🌊 DataFlow AI: Enterprise-Grade Autonomous Analytics Platform

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=FastAPI&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![Machine Learning](https://img.shields.io/badge/Machine_Learning-FF6F00?style=for-the-badge&logo=scikit-learn&logoColor=white)

## 📌 Executive Summary
DataFlow AI is an end-to-end, full-stack data analytics platform powered by an autonomous, self-healing AI agent. Designed to replace tedious manual data wrangling, the platform allows users to upload raw datasets (CSV, Excel) and interact with their data using natural language. 

The backend dynamically writes, executes, and validates Python code in real-time to perform data cleaning, statistical analysis, and predictive modeling, directly returning actionable insights and downloadable assets to a custom-built, responsive frontend.

## ✨ Key Features & Technical Highlights

* **🤖 Autonomous "Self-Healing" AI Agent:** The core of the application relies on an LLM (LLaMA 3.3 via Groq) acting as a reasoning engine. If the AI generates Python code that throws an execution error, the system catches the traceback and feeds it back to the agent in an autonomous loop, allowing it to "self-heal" and fix its own code without user intervention.
* **🧹 Advanced ML Data Cleaning Pipeline:**
  Moving beyond standard `.dropna()`, the platform features a dedicated prescriptive cleaning engine utilizing:
  * **Isolation Forest** for machine learning-based anomaly detection.
  * **K-Nearest Neighbors (KNN)** & **Linear Regression** for predictive missing value imputation.
  * **Z-Score & IQR** for robust statistical outlier capping.
* **🧵 Threaded Conversation Memory:**
  Built a Gemini/ChatGPT-style session management system using **PostgreSQL (Neon DB)** and **SQLAlchemy**. Conversations are stateful, grouped by UUIDs, and reliably persist context across sessions.
* **📊 Predictive Forecasting & Visualization:**
  Integrated with `Prophet` and `Seaborn` to autonomously generate high-resolution visual charts, future trendlines, and prescriptive growth strategies based on historical data.
* **🚀 Custom Vanilla Full-Stack Architecture:**
  Intentionally avoided low-code UI wrappers (like Streamlit) to build a robust, decoupled architecture. The frontend is built with pure HTML/CSS/JS, utilizing asynchronous `fetch` calls, Markdown parsing, and dynamic DOM manipulation to interface with a high-performance **FastAPI** backend.

## 🛠️ Technology Stack

| Component | Technologies Used |
| :--- | :--- |
| **Backend API** | FastAPI, Python, Uvicorn |
| **Database & ORM** | PostgreSQL (Neon Serverless), SQLAlchemy |
| **AI / LLM Layer** | Groq API, LLaMA 3.3 70B Versatile |
| **Data Science** | Pandas, Scikit-Learn, Prophet, Numpy |
| **Visualization** | Matplotlib (Agg), Seaborn, Apache Superset |
| **Frontend UI** | HTML5, CSS3, Vanilla JavaScript, Marked.js |

## ⚙️ System Architecture Workflow

1. **User Input:** User uploads a dataset and prompts the AI via the frontend UI.
2. **Context Assembly:** FastAPI handles the multipart form data, securely saves the file, and retrieves the user's historical conversational context from PostgreSQL.
3. **Smart Routing:** The system determines if the prompt is conversational or analytical.
4. **Agentic Execution:** For analytical tasks, the prompt is sent to the LLM with strict systemic rules. The LLM generates executable Python code targeting the uploaded dataset.
5. **Validation Loop:** The code is executed in an isolated backend buffer. If it fails, the error is fed back to the LLM for correction (max 3 retries).
6. **Output Delivery:** Successful outputs, charts, and modified CSV paths are converted to Markdown and rendered interactively on the frontend.
