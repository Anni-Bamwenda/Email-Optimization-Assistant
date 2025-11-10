import pytest
from unittest.mock import patch
from src.email_summarizer import summarize_emails

@patch("src.summarizer.OpenAI")
def test_summarize_emails_returns_text(mock_openai):
    mock_client = mock_openai.return_value
    mock_client.chat.completions.create.return_value.choices = [
        type("obj", (object,), {"message": type("obj", (object,), {"content": "Summary text"})()})
    ]
    result = summarize_emails(["email 1", "email 2"])
    assert isinstance(result, str)
