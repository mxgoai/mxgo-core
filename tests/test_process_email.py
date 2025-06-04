import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from mxtoai.email_handles import DEFAULT_EMAIL_HANDLES
from mxtoai.models import ProcessingInstructions
from mxtoai.schemas import (
    AttachmentsProcessingResult,
    DetailedEmailProcessingResult,
    EmailContentDetails,
    EmailSentStatus,
    ProcessingError,
    ProcessingMetadata,
)
from mxtoai.tasks import process_email_task

AttachmentFileContent = tuple[str, bytes, str]  # (filename, content_bytes, content_type)


@pytest.fixture
def prepare_email_request_data(tmp_path):
    def _prepare(
        to_email: str = "ask@mxtoai.com",
        from_email: str = "sender.test@example.com",
        subject: str = "Test Subject",
        text_content: str = "This is a test email.",
        html_content: str = "<p>This is a test email.</p>",
        message_id: str = "<test-message-id-default>",
        attachments_data: Optional[
            list[AttachmentFileContent]
        ] = None,  # List of (filename, content_bytes, content_type)
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        """
        Prepares email_data, email_attachments_dir_str, and attachment_info_list.
        `attachments_data` is a list of tuples: (filename, content_bytes, content_type)
        """
        attachments_dir_path = tmp_path / "attachments"
        attachments_dir_path.mkdir(exist_ok=True)

        email_attachments_schema_list: list[dict[str, Any]] = []
        attachment_info_list_for_task: list[dict[str, Any]] = []

        if attachments_data:
            for idx, (filename, content_bytes, content_type) in enumerate(attachments_data):
                dummy_file_path = attachments_dir_path / f"{idx}_{filename}"
                dummy_file_path.write_bytes(content_bytes)
                dummy_file_size = dummy_file_path.stat().st_size

                email_attachments_schema_list.append(
                    {"filename": filename, "contentType": content_type, "size": dummy_file_size}
                )
                attachment_info_list_for_task.append(
                    {"path": str(dummy_file_path), "filename": filename, "type": content_type, "size": dummy_file_size}
                )

        email_data = {
            "from_email": from_email,
            "to": to_email,
            "subject": subject,
            "textContent": text_content,
            "htmlContent": html_content,
            "messageId": message_id,
            "attachments": email_attachments_schema_list,
            "recipients": [to_email.split("@")[0] + "@mxtoai.com"],  # Simplified recipient
            "date": "2023-01-01T12:00:00Z",
        }

        return email_data, str(attachments_dir_path), attachment_info_list_for_task

    return _prepare


def _assert_basic_successful_processing(
    result: DetailedEmailProcessingResult,
    expected_handle: str,
    expect_reply_sent: bool = True,
    attachments_cleaned_up_dir: Optional[str] = None,
):
    """Helper function for common assertions on successful processing results."""
    assert isinstance(result, DetailedEmailProcessingResult), "Return type mismatch"
    assert result.metadata.mode == expected_handle, f"Expected handle {expected_handle}, got {result.metadata.mode}"
    assert not result.metadata.errors, f"Expected no errors, but got: {result.metadata.errors}"

    assert result.email_content is not None
    assert result.email_content.text is not None and len(result.email_content.text) > 0, "Reply text is empty"
    assert result.email_content.html is not None and len(result.email_content.html) > 0, "Reply HTML is empty"

    if expect_reply_sent:
        assert result.metadata.email_sent.status == "sent", "Email not marked as sent"
        assert result.metadata.email_sent.message_id == "mocked_message_id_happy_path", "Message ID mismatch"
    else:
        # Could be 'pending' or 'skipped' etc. depending on other factors not covered by this basic assert
        assert result.metadata.email_sent.status != "error", "Email marked as error when not expected"

    if attachments_cleaned_up_dir:
        assert not Path(attachments_cleaned_up_dir).exists(), (
            f"Attachments directory '{attachments_cleaned_up_dir}' was not cleaned up."
        )


# --- Existing Happy Path Test (adapted to use new fixture) ---
def test_process_email_task_happy_path_with_attachment(prepare_email_request_data):
    """
    Tests the happy path for process_email_task with an attachment.
    Only EmailSender.send_reply is mocked.
    """
    attachment_content = ("test_attachment.txt", b"This is a test attachment.", "text/plain")
    email_data, email_attachments_dir_str, attachment_info = prepare_email_request_data(
        to_email="ask@mxtoai.com", attachments_data=[attachment_content]
    )

    assert Path(email_attachments_dir_str).exists()
    assert (Path(email_attachments_dir_str) / f"0_{attachment_content[0]}").exists()  # Check specific file

    with patch("mxtoai.tasks.EmailSender") as MockEmailSender:
        mock_sender_instance = MockEmailSender.return_value

        async def mock_async_send_reply(*args, **kwargs):
            return {"MessageId": "mocked_message_id_happy_path", "status": "sent"}

        mock_sender_instance.send_reply = MagicMock(side_effect=mock_async_send_reply)

        returned_result = process_email_task.fn(
            email_data=email_data, email_attachments_dir=email_attachments_dir_str, attachment_info=attachment_info
        )

        mock_sender_instance.send_reply.assert_called_once()
        call_args = mock_sender_instance.send_reply.call_args
        original_email_details_arg = call_args[0][0]
        assert original_email_details_arg["from"] == email_data["from_email"]

        _assert_basic_successful_processing(
            returned_result, expected_handle="ask", attachments_cleaned_up_dir=email_attachments_dir_str
        )


# --- New Test Cases ---


def test_process_email_task_unsupported_handle(prepare_email_request_data):
    """Tests behavior when an unsupported email handle is provided."""
    unsupported_handle = "nonexistenthandle@mxtoai.com"
    email_data, email_attachments_dir_str, attachment_info = prepare_email_request_data(to_email=unsupported_handle)

    # No mocks needed as it should fail before agent or sender
    returned_result = process_email_task.fn(
        email_data=email_data, email_attachments_dir=email_attachments_dir_str, attachment_info=attachment_info
    )

    assert isinstance(returned_result, DetailedEmailProcessingResult)
    assert returned_result.metadata.mode == unsupported_handle.split("@")[0]
    assert len(returned_result.metadata.errors) == 1
    assert "Unsupported email handle" in returned_result.metadata.errors[0].message
    assert returned_result.metadata.email_sent.status == "error"
    assert "Unsupported email handle" in returned_result.metadata.email_sent.error
    # The error detail from the exception should be in the returned result
    assert "This email handle is not supported" in returned_result.metadata.errors[0].details

    # Attachments dir might be created but should not be cleaned if processing stops early
    # or if it was never relevant. If it was created, it might still exist.
    # For this test, the main focus is the error state.


def test_process_email_task_agent_exception(prepare_email_request_data):
    """Tests behavior when EmailAgent.process_email returns a result indicating an internal error."""
    email_data, email_attachments_dir_str, attachment_info = prepare_email_request_data(to_email="ask@mxtoai.com")
    now_iso = datetime.now().isoformat()  # For constructing mock error response

    # Prepare a mock error response that EmailAgent.process_email would return
    mock_agent_error_result = DetailedEmailProcessingResult(
        metadata=ProcessingMetadata(
            processed_at=now_iso,
            mode="ask",
            errors=[
                ProcessingError(
                    message="Critical error during agent processing", details="Simulated agent internal crash"
                )
            ],
            email_sent=EmailSentStatus(status="error", error="Simulated agent internal crash", timestamp=now_iso),
        ),
        email_content=EmailContentDetails(text=None, html=None, enhanced=None),
        attachments=AttachmentsProcessingResult(processed=[]),
        calendar_data=None,
        research=None,
    )

    with (
        patch(
            "mxtoai.tasks.EmailAgent.process_email", return_value=mock_agent_error_result
        ) as mock_agent_process_email,
        patch("mxtoai.tasks.EmailSender") as MockEmailSender,
    ):
        mock_sender_instance = MockEmailSender.return_value

        async def mock_async_send_reply(*args, **kwargs):
            return {"MessageId": "should_not_be_called", "status": "sent"}

        mock_sender_instance.send_reply = MagicMock(side_effect=mock_async_send_reply)

        returned_task_result = process_email_task.fn(
            email_data=email_data, email_attachments_dir=email_attachments_dir_str, attachment_info=attachment_info
        )

    assert isinstance(returned_task_result, DetailedEmailProcessingResult)
    # The result from the task should be the same as what the agent returned in its error state
    assert len(returned_task_result.metadata.errors) > 0
    assert returned_task_result.metadata.errors[0].message == "Critical error during agent processing"
    assert returned_task_result.metadata.errors[0].details == "Simulated agent internal crash"
    assert returned_task_result.metadata.email_sent.status == "error"
    assert returned_task_result.metadata.email_sent.error == "Simulated agent internal crash"

    mock_agent_process_email.assert_called_once()
    mock_sender_instance.send_reply.assert_not_called()  # Reply should not be attempted if agent indicates error

    assert not Path(email_attachments_dir_str).exists(), (
        f"Attachments directory '{email_attachments_dir_str}' was not cleaned up even after agent error."
    )


# Parametrized test for each handle
@pytest.mark.parametrize("handle_instructions", DEFAULT_EMAIL_HANDLES)
def test_process_email_task_for_handle(
    handle_instructions: ProcessingInstructions,
    prepare_email_request_data,
    tmp_path,  # For schedule handle specific file creation
):
    """
    Tests successful processing for each defined email handle.
    Only EmailSender.send_reply is mocked.
    This is an integration test for the task and the agent's processing for each handle.
    """
    to_email_address = f"{handle_instructions.handle}@mxtoai.com"

    attachments_for_test: Optional[list[AttachmentFileContent]] = None
    is_schedule_handle = handle_instructions.handle == "schedule"

    # Specific setup for schedule handle to provide context for scheduling
    subject_for_test = f"Test for {handle_instructions.handle}"
    text_content_for_test = f"This is a test email for the '{handle_instructions.handle}' handle."
    if is_schedule_handle:
        text_content_for_test = "Please schedule a meeting titled 'Project Kickoff' for January 5th, 2024, at 2:00 PM EST to discuss the project milestones. My email is sender.test@example.com and please invite colleague@example.com."
        # Add a dummy file if process_attachments is True for schedule, though it might not be used
        if handle_instructions.process_attachments:
            attachments_for_test = [("schedule_context.txt", b"Meeting context document.", "text/plain")]

    email_data, email_attachments_dir_str, attachment_info = prepare_email_request_data(
        to_email=to_email_address,
        subject=subject_for_test,
        text_content=text_content_for_test,
        attachments_data=attachments_for_test,
    )

    # Set SKIP_EMAIL_DELIVERY for specific handles if they don't typically result in a direct reply "sent"
    # or to simplify testing by not needing to validate a complex LLM-generated reply.
    # For now, assume all handles in DEFAULT_EMAIL_HANDLES are expected to try to send a reply.
    expect_reply_actually_sent = True

    # For "schedule" handle, we will mock send_reply but also check if an ICS was generated.
    # For other handles, we mainly check if a reply was attempted.
    # Note: Since EmailAgent is not mocked beyond EmailSender, the actual content of the reply
    # will depend on the LLM and the prompt templates. This test primarily verifies
    # that the pipeline for each handle type runs and attempts a reply.

    with (
        patch("mxtoai.tasks.EmailSender") as MockEmailSender,
        patch.dict(os.environ, {"SKIP_EMAIL_DELIVERY": ""}),
    ):  # Ensure SKIP_EMAIL_DELIVERY is not set globally for this test run
        mock_sender_instance = MockEmailSender.return_value

        async def mock_async_send_reply(*args, **kwargs):
            # Check for ICS attachment if it's the schedule handle
            if is_schedule_handle:
                sent_attachments = kwargs.get("attachments", [])
                assert any(att["filename"] == "invite.ics" for att in sent_attachments), (
                    "ICS attachment was not prepared for sending by the schedule handle."
                )
                assert any(att["mimetype"] == "text/calendar" for att in sent_attachments)

            # Check for PDF attachment if it's the PDF handle
            if handle_instructions.handle == "pdf":
                sent_attachments = kwargs.get("attachments", [])
                assert len(sent_attachments) > 0, "PDF handle should have attachments"
                pdf_attachment = None
                for att in sent_attachments:
                    if att["filename"].endswith(".pdf"):
                        pdf_attachment = att
                        break
                assert pdf_attachment is not None, "PDF attachment was not prepared for sending by the PDF handle"
                assert pdf_attachment["mimetype"] == "application/pdf", "PDF attachment should have correct mimetype"
                assert len(pdf_attachment["content"]) > 0, "PDF attachment should have content"

            return {"MessageId": "mocked_message_id_happy_path", "status": "sent"}

        mock_sender_instance.send_reply = MagicMock(side_effect=mock_async_send_reply)

        returned_result = process_email_task.fn(
            email_data=email_data, email_attachments_dir=email_attachments_dir_str, attachment_info=attachment_info
        )

        if expect_reply_actually_sent:
            mock_sender_instance.send_reply.assert_called_once()
            _assert_basic_successful_processing(
                returned_result,
                expected_handle=handle_instructions.handle,
                attachments_cleaned_up_dir=email_attachments_dir_str
                if attachments_for_test
                else None,  # Only check cleanup if dir was used
            )
            # Specific assertion for schedule handle's calendar_data
            if is_schedule_handle:
                assert returned_result.calendar_data is not None, "Calendar data should be present for schedule handle"
                assert (
                    returned_result.calendar_data.ics_content is not None
                    and len(returned_result.calendar_data.ics_content) > 0
                ), "ICS content is missing or empty for schedule handle"

            # Specific assertions for PDF handle
            if handle_instructions.handle == "pdf":
                assert returned_result.pdf_export is not None, "PDF export result should be present for PDF handle"
                assert returned_result.pdf_export.filename.endswith(".pdf"), "PDF export should have .pdf filename"
                assert returned_result.pdf_export.file_size > 0, "PDF export should have non-zero file size"
                assert returned_result.pdf_export.mimetype == "application/pdf", "PDF export should have correct mimetype"
                assert returned_result.pdf_export.title is not None, "PDF export should have a title"
                assert returned_result.pdf_export.pages_estimated >= 1, "PDF export should have at least 1 page estimated"
        else:
            # If not expecting a sent reply (e.g. if we were to use SKIP_EMAIL_DELIVERY for some handles)
            mock_sender_instance.send_reply.assert_not_called()
            assert returned_result.metadata.email_sent.status == "skipped"  # or "pending" depending on logic
            # Further assertions for non-sent cases might be needed.

        # General check: No errors in metadata for any handle type on happy path
        assert not returned_result.metadata.errors, (
            f"Handle '{handle_instructions.handle}' produced errors: {returned_result.metadata.errors}"
        )

        # Ensure deep_research_mandatory flag was respected (qualitative check via EmailAgent logs if verbose, hard to assert directly without deeper mocks)
        # We trust EmailAgent tests for this part.
        # Here, we are testing the task's integration with the agent for each handle.


# --- PDF Export Specific Tests ---


def test_pdf_export_tool_direct():
    """Test the PDFExportTool directly to ensure it generates valid PDFs."""
    from mxtoai.tools.pdf_export_tool import PDFExportTool

    tool = PDFExportTool()

    # Test basic content export
    result = tool.forward(
        content="# Test Document\n\nThis is a test document with some content.\n\n- Item 1\n- Item 2\n- Item 3",
        title="Test PDF Document"
    )

    assert result["success"] is True, f"PDF export failed: {result.get('error', 'Unknown error')}"
    assert result["filename"] == "Test_PDF_Document.pdf"
    assert result["file_size"] > 0
    assert result["mimetype"] == "application/pdf"
    assert result["title"] == "Test PDF Document"
    assert result["pages_estimated"] >= 1

    # Verify the file actually exists and has content
    pdf_path = result["file_path"]
    assert os.path.exists(pdf_path), "PDF file should exist"

    # Read and verify PDF content
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
    assert len(pdf_content) > 100, "PDF should have substantial content"
    assert pdf_content[:4] == b"%PDF", "File should start with PDF magic bytes"

    # Clean up
    os.unlink(pdf_path)


def test_pdf_export_tool_with_research_findings():
    """Test PDF export with research findings and attachments summary."""
    from mxtoai.tools.pdf_export_tool import PDFExportTool

    tool = PDFExportTool()

    result = tool.forward(
        content="# Email Newsletter Summary\n\nThis is the main content of the email.",
        title="Weekly Newsletter Export",
        research_findings="## Research Results\n\n1. Finding one\n2. Finding two\n3. Finding three",
        attachments_summary="## Attachments Processed\n\n- attachment1.pdf\n- attachment2.docx",
        include_attachments=True
    )

    assert result["success"] is True
    assert result["filename"] == "Weekly_Newsletter_Export.pdf"
    assert result["file_size"] > 0

    # Verify the file exists
    pdf_path = result["file_path"]
    assert os.path.exists(pdf_path), "PDF file should exist"

    # Clean up
    os.unlink(pdf_path)


def test_pdf_export_content_cleaning():
    """Test that PDF export properly cleans email headers and formats content."""
    from mxtoai.tools.pdf_export_tool import PDFExportTool

    tool = PDFExportTool()

    # Content with email headers that should be removed
    email_content = """From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 01 Jan 2024 12:00:00 +0000

# Important Newsletter

This is the actual content that should be preserved.

## Section 1
- Important point 1
- Important point 2

## Section 2
More important content here.
"""

    result = tool.forward(content=email_content)

    assert result["success"] is True
    assert result["file_size"] > 0

    # The cleaned content should not contain email headers
    # We can't easily verify the internal content without parsing the PDF,
    # but we can verify the tool runs successfully

    # Clean up
    os.unlink(result["file_path"])


def test_pdf_handle_full_integration():
    """Test the full PDF handle integration with a more comprehensive email."""
    from mxtoai.tasks import process_email_task
    from unittest.mock import patch, MagicMock
    import tempfile
    import shutil

    # Create comprehensive test email content
    email_data = {
        "to": "pdf@mxtoai.com",
        "from_email": "test@example.com",
        "subject": "Weekly AI Newsletter - Export to PDF",
        "textContent": """# Weekly AI Newsletter

## Top Stories This Week

1. **Breaking**: New AI model achieves breakthrough in natural language understanding
   - Improved accuracy by 15% over previous models
   - Reduced computational requirements
   - Available for public research

2. **Industry News**: Major tech companies announce AI partnerships
   - Focus on ethical AI development
   - Shared research initiatives
   - Open source commitments

3. **Research Highlights**: Recent papers in machine learning
   - Novel architectures for transformer models
   - Advances in computer vision
   - Multimodal learning approaches

## Tools and Resources

- New dataset for training language models
- Updated frameworks and libraries
- Community challenges and competitions

## Upcoming Events

- AI Conference 2024 (March 15-17)
- Workshop on Ethical AI (April 2)
- Research symposium (April 20)

This newsletter provides a comprehensive overview of recent developments in AI research and industry trends.
""",
        "messageId": "<test-pdf-message-id>",
        "date": "2024-01-01T12:00:00Z",
        "recipients": ["pdf@mxtoai.com"],
        "cc": None,
        "bcc": None,
        "references": None,
        "attachments": []
    }

    # Create temporary directory for attachments
    temp_dir = tempfile.mkdtemp()

    try:
        with (
            patch("mxtoai.tasks.EmailSender") as MockEmailSender,
        ):
            mock_sender_instance = MockEmailSender.return_value

            # Track the PDF attachment that gets sent
            captured_pdf_attachment = None

            async def mock_async_send_reply(*args, **kwargs):
                nonlocal captured_pdf_attachment
                sent_attachments = kwargs.get("attachments", [])

                # Find the PDF attachment
                for att in sent_attachments:
                    if att["filename"].endswith(".pdf"):
                        captured_pdf_attachment = att
                        break

                return {"MessageId": "test-pdf-message-id", "status": "sent"}

            mock_sender_instance.send_reply = MagicMock(side_effect=mock_async_send_reply)

            # Run the task
            result = process_email_task.fn(
                email_data=email_data,
                email_attachments_dir=temp_dir,
                attachment_info=[]
            )

            # Verify successful processing
            assert isinstance(result, DetailedEmailProcessingResult)
            # Note: email status will be 'skipped' because test@example.com is in SKIP_EMAIL_DELIVERY
            assert result.metadata.email_sent.status == "skipped"
            assert len(result.metadata.errors) == 0, f"Processing errors: {result.metadata.errors}"

            # Verify PDF export result
            assert result.pdf_export is not None, "PDF export result should be present"
            assert result.pdf_export.filename.endswith(".pdf")
            assert result.pdf_export.file_size > 1000, "PDF should be reasonably sized for the content"
            assert result.pdf_export.mimetype == "application/pdf"
            assert "Weekly AI Newsletter" in result.pdf_export.title or "AI Newsletter" in result.pdf_export.title
            assert result.pdf_export.pages_estimated >= 1

            # Email should not be attempted to be sent due to SKIP_EMAIL_DELIVERY
            mock_sender_instance.send_reply.assert_not_called()

            # The PDF was generated but not attached due to skipped email delivery
            # In this test case, we're focusing on verifying that PDF export works
            # and that the result contains the expected PDF data

            # Verify email response content
            assert result.email_content is not None
            assert result.email_content.text is not None
            assert len(result.email_content.text) > 0
            assert result.email_content.html is not None
            assert len(result.email_content.html) > 0

    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_pdf_export_error_handling():
    """Test PDF export tool error handling for invalid inputs."""
    from mxtoai.tools.pdf_export_tool import PDFExportTool

    tool = PDFExportTool()

    # Test with empty content
    result = tool.forward(content="")
    assert result["success"] is True  # Should still work with empty content
    assert result["title"] == "Document"  # Should use default title

    # Clean up if file was created
    if "file_path" in result and os.path.exists(result["file_path"]):
        os.unlink(result["file_path"])

    # Test with very long title
    long_title = "A" * 200  # Very long title
    result = tool.forward(content="Test content", title=long_title)
    assert result["success"] is True
    # Filename should be truncated
    assert len(result["filename"]) <= 55  # 50 chars + ".pdf"

    # Clean up
    if "file_path" in result and os.path.exists(result["file_path"]):
        os.unlink(result["file_path"])


if __name__ == "__main__":
    # Run only PDF tests if executed directly
    pytest.main([__file__ + "::test_pdf_export_tool_direct", "-v"])
    pytest.main([__file__ + "::test_pdf_export_tool_with_research_findings", "-v"])
    pytest.main([__file__ + "::test_pdf_export_content_cleaning", "-v"])
    pytest.main([__file__ + "::test_pdf_handle_full_integration", "-v"])
    pytest.main([__file__ + "::test_pdf_export_error_handling", "-v"])
