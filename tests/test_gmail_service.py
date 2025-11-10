from src.gmail_service import get_emails

def test_get_emails_returns_list():
    emails = get_emails(days_back=2)
    assert isinstance(emails, list)
    assert len(emails) == 2
