import io
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from mxtoai._logging import get_logger
from mxtoai.api import app

client = TestClient(app)
API_KEY = os.environ["X_API_KEY"]

logger = get_logger(__name__)


def prepare_form_data(**kwargs):
    form_data = {
        "from_email": "test@example.com",
        "to": "ask@mxtoai.com",
        "subject": "Test Subject",
        "textContent": "Test text content",
        "htmlContent": "<p>Test HTML content</p>",
        "messageId": f"test-message-id-{os.urandom(4).hex()}",
        "date": "2023-10-26T10:00:00Z",
        "emailId": f"original-email-id-{os.urandom(4).hex()}",
        "rawHeaders": '{"cc": "cc@example.com"}',
    }
    form_data.update(kwargs)
    return form_data


def make_post_request(form_data, endpoint, files=None, headers=None):
    request_headers = {"x-api-key": API_KEY}
    if headers is not None:
        request_headers.update(headers)
    if request_headers.get("x-api-key") is None and "x-api-key" in request_headers:
        del request_headers["x-api-key"]

    return client.post(endpoint, data=form_data, files=files, headers=request_headers)


def assert_successful_response(response, expected_attachments_saved=0):
    assert response.status_code == 200, f"Expected status 200, got {response.status_code}. Response: {response.text}"
    response_json = response.json()
    assert response_json["message"] == "Email received and queued for processing"
    assert "email_id" in response_json
    assert response_json["email_id"] is not None
    assert response_json["email_id"] != ""
    assert response_json["attachments_saved"] == expected_attachments_saved
    assert response_json["status"] == "processing"


def validate_send_task(
    form_data, mock_task_send, expected_attachment_count=0, expected_attachment_filename=None, temp_attachments_dir=None
):
    mock_task_send.assert_called_once()
    args_task_send, _ = mock_task_send.call_args
    sent_email_request_dump = args_task_send[0]
    email_attachments_dir_arg = args_task_send[1]
    processed_attachment_info_arg = args_task_send[2]

    assert sent_email_request_dump["from_email"] == form_data["from_email"]
    assert sent_email_request_dump["to"] == form_data["to"]
    assert sent_email_request_dump["subject"] == form_data["subject"]

    raw_headers_in_task = sent_email_request_dump.get("rawHeaders", {})
    expected_raw_headers = {}
    if form_data.get("rawHeaders"):
        try:
            expected_raw_headers = json.loads(form_data["rawHeaders"])
        except (json.JSONDecodeError, TypeError, ValueError):
            expected_raw_headers = {}

    assert raw_headers_in_task == expected_raw_headers

    expected_cc = []
    if isinstance(expected_raw_headers, dict) and "cc" in expected_raw_headers:
        cc_val = expected_raw_headers["cc"]
        if isinstance(cc_val, str):
            expected_cc = [addr.strip() for addr in cc_val.split(",") if addr.strip()]
        elif isinstance(cc_val, list):
            expected_cc = cc_val

    assert sent_email_request_dump.get("cc", []) == expected_cc

    assert len(processed_attachment_info_arg) == expected_attachment_count
    if expected_attachment_count > 0:
        assert email_attachments_dir_arg != ""
        if temp_attachments_dir:
            assert Path(email_attachments_dir_arg).parent == temp_attachments_dir, (
                f"Attachment directory {email_attachments_dir_arg} is not a child of tmp_path {temp_attachments_dir}"
            )

            id_component_from_path = Path(email_attachments_dir_arg).name
            assert id_component_from_path != "", "Generated email ID component in path is empty"

            if expected_attachment_filename:
                assert processed_attachment_info_arg[0]["filename"] == expected_attachment_filename
                expected_attachment_path = str(Path(email_attachments_dir_arg) / expected_attachment_filename)
                assert processed_attachment_info_arg[0]["path"] == expected_attachment_path, (
                    f"Attachment path mismatch: expected {expected_attachment_path}, got {processed_attachment_info_arg[0]['path']}"
                )
        else:
            assert email_attachments_dir_arg != ""
    else:
        assert email_attachments_dir_arg == "", f"Expected no attachment directory, but got {email_attachments_dir_arg}"


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_no_attachments_ask_handle(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response, expected_attachments_saved=0)

    mock_validate_email_whitelist.assert_called_once_with(
        form_data["from_email"], form_data["to"], form_data["subject"], form_data["messageId"]
    )
    validate_send_task(form_data, mock_task_send, expected_attachment_count=0)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_with_one_valid_attachment_ask_handle(
    mock_task_send, mock_validate_email_whitelist, tmp_path, monkeypatch
):
    monkeypatch.setattr("mxtoai.api.ATTACHMENTS_DIR", str(tmp_path))

    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    file_content_for_test = b"This is a test file content."
    file_name_for_test = "test_attachment.txt"
    content_type_for_test = "text/plain"

    files_for_request = [("files", (file_name_for_test, io.BytesIO(file_content_for_test), content_type_for_test))]

    response = make_post_request(form_data, "/process-email", files=files_for_request)
    assert_successful_response(response, expected_attachments_saved=1)

    mock_validate_email_whitelist.assert_called_once_with(
        form_data["from_email"], form_data["to"], form_data["subject"], form_data["messageId"]
    )
    validate_send_task(
        form_data,
        mock_task_send,
        expected_attachment_count=1,
        expected_attachment_filename=file_name_for_test,
        temp_attachments_dir=tmp_path,
    )


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_all_optional_fields_no_cc_ask_handle(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(
        to="ask@mxtoai.com",
        subject="Comprehensive Subject",
        textContent="Detailed text content here.",
        htmlContent="<h1>Detailed HTML</h1><p>With paragraphs.</p>",
        messageId="specific-msg-id-all-fields",
        date="2023-11-15T12:00:00Z",
        emailId="specific-email-id-all-fields",
        rawHeaders='{"X-Custom-Header": "value"}',
    )

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response, expected_attachments_saved=0)

    mock_validate_email_whitelist.assert_called_once_with(
        form_data["from_email"], form_data["to"], form_data["subject"], form_data["messageId"]
    )
    validate_send_task(form_data, mock_task_send, expected_attachment_count=0)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_invalid_api_key(mock_task_send, mock_validate_email_whitelist):
    form_data = prepare_form_data()
    invalid_api_key = "this-is-a-wrong-key"

    assert invalid_api_key != API_KEY, "Test setup error: Fallback API_KEY should not be the invalid_api_key"

    response = make_post_request(form_data, "/process-email", headers={"x-api-key": invalid_api_key})

    assert response.status_code == 401
    response_json = response.json()
    assert response_json["message"] == "Invalid API key"
    assert response_json["status"] == "error"
    mock_task_send.assert_not_called()


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_missing_api_key_header(mock_task_send, mock_validate_email_whitelist):
    form_data = prepare_form_data()

    response = make_post_request(form_data, "/process-email", headers={"x-api-key": None})

    assert response.status_code == 403
    response_json = response.json()
    assert response_json.get("detail") == "Not authenticated"
    mock_task_send.assert_not_called()


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_multiple_attachments_ask_handle(
    mock_task_send, mock_validate_email_whitelist, tmp_path, monkeypatch
):
    monkeypatch.setattr("mxtoai.api.ATTACHMENTS_DIR", str(tmp_path))
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    files_for_request = [
        ("files", ("test1.txt", io.BytesIO(b"Content 1"), "text/plain")),
        ("files", ("test2.pdf", io.BytesIO(b"Content 2"), "application/pdf")),
        ("files", ("test3.jpg", io.BytesIO(b"Content 3"), "image/jpeg")),
    ]

    response = make_post_request(form_data, "/process-email", files=files_for_request)
    assert_successful_response(response, expected_attachments_saved=3)
    validate_send_task(form_data, mock_task_send, expected_attachment_count=3, temp_attachments_dir=tmp_path)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_with_cc_recipients(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com", rawHeaders='{"cc": "cc1@example.com, cc2@example.com"}')

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_different_handle(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="summarize@mxtoai.com")

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_handle_alias(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="eli5@mxtoai.com")  # alias for simplify

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_invalid_handle(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="invalid@mxtoai.com")

    response = make_post_request(form_data, "/process-email")
    assert response.status_code == 400
    response_json = response.json()
    assert "Unsupported email handle" in response_json.get("message", "")
    mock_task_send.assert_not_called()


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_empty_attachment(mock_task_send, mock_validate_email_whitelist, tmp_path, monkeypatch):
    monkeypatch.setattr("mxtoai.api.ATTACHMENTS_DIR", str(tmp_path))
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    files_for_request = [("files", ("empty.txt", io.BytesIO(b""), "text/plain"))]

    response = make_post_request(form_data, "/process-email", files=files_for_request)
    assert response.status_code == 400
    response_json = response.json()
    assert "Empty attachment" in response_json.get("detail", "")
    mock_task_send.assert_not_called()


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_unsupported_file_type(
    mock_task_send, mock_validate_email_whitelist, tmp_path, monkeypatch
):
    monkeypatch.setattr("mxtoai.api.ATTACHMENTS_DIR", str(tmp_path))
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    files_for_request = [("files", ("test.exe", io.BytesIO(b"Content"), "application/x-msdownload"))]

    response = make_post_request(form_data, "/process-email", files=files_for_request)
    assert response.status_code == 400
    response_json = response.json()
    assert "Unsupported file type" in response_json.get("detail", "")
    mock_task_send.assert_not_called()


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_malformed_cc_headers(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com", rawHeaders='{"cc": "invalid-email, another@invalid"}')

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)  # Should still succeed as CC validation is not strict
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_failure_malformed_json_headers(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(
        to="ask@mxtoai.com",
        rawHeaders='{"cc": "invalid-json',  # Malformed JSON
    )

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)  # Should still succeed as header parsing is not strict
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_html_only_content(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(
        to="ask@mxtoai.com",
        textContent="",  # Empty text content
        htmlContent="<h1>HTML Only Content</h1><p>This is HTML content.</p>",
    )

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_text_only_content(mock_task_send, mock_validate_email_whitelist):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(
        to="ask@mxtoai.com",
        textContent="This is plain text content.",
        htmlContent="",  # Empty HTML content
    )

    response = make_post_request(form_data, "/process-email")
    assert_successful_response(response)
    validate_send_task(form_data, mock_task_send)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_special_characters_filename(
    mock_task_send, mock_validate_email_whitelist, tmp_path, monkeypatch
):
    monkeypatch.setattr("mxtoai.api.ATTACHMENTS_DIR", str(tmp_path))
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    files_for_request = [("files", ("test@file#name.txt", io.BytesIO(b"Content"), "text/plain"))]

    response = make_post_request(form_data, "/process-email", files=files_for_request)
    assert_successful_response(response, expected_attachments_saved=1)
    validate_send_task(form_data, mock_task_send, expected_attachment_count=1, temp_attachments_dir=tmp_path)


@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_long_filename(mock_task_send, mock_validate_email_whitelist, tmp_path, monkeypatch):
    monkeypatch.setattr("mxtoai.api.ATTACHMENTS_DIR", str(tmp_path))
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com")

    long_filename = "a" * 255 + ".txt"  # Maximum filename length
    files_for_request = [("files", (long_filename, io.BytesIO(b"Content"), "text/plain"))]

    response = make_post_request(form_data, "/process-email", files=files_for_request)
    assert_successful_response(response, expected_attachments_saved=1)
    validate_send_task(form_data, mock_task_send, expected_attachment_count=1, temp_attachments_dir=tmp_path)
