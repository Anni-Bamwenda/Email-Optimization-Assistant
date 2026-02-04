# Email Optimization Assistant

This ongoing project automates daily email summarization and organization using the Gmail and OpenAI APIs.

---

## Overview
- Extracts Gmail emails from the previous day (24hrs) using Google API  
- Deletes (moves to trash folder) unwanted emails (subscriptions, spams, social, promotions, notifications, and noreplys) to free up space
- Summarizes inbox emails using GPT-5 mini (OpenAI API)  
- Saves a concise daily report  
- Runs automatically via scheduler or GitHub Actions

---

## Architecture

```mermaid
flowchart TD
  A["Fetch Emails (Gmail API)"] --> B["Delete Unwanted Emails"]
  B --> C["Summarize Text (OpenAI API"]
  C --> D["Save Summary File"]
  D --> E["Automated Scheduler or CI/CD"]
```
