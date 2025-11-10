# Email-Optimization-Assistant
Automates Gmail extraction and gives daily summaries using OpenAI API.

# 📧 Email Optimization Assistant

This project automates daily email summarization and organization using the Gmail and OpenAI APIs.

---

## 🧠 Overview
- Extracts Gmail emails from the previous day (24hrs) using Google API  
- Summarizes them using GPT-4 (OpenAI API)  
- Saves a concise daily report  
- Runs automatically via scheduler or GitHub Actions
- Deletes (moves to trash folder) some emails (subscriptions, spams, and promotions)
- At the beginning of every quarter, it empties all emails in the trash folder.  

---

## 🏗️ Architecture
```mermaid
flowchart TD
  A[Fetch Emails (Gmail API)] --> B[Summarize Text (OpenAI API)]
  B --> C[Save Summary File]
  C --> D[Automated Scheduler or CI/CD]
