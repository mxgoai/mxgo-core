import PostalMime from 'postal-mime';
import { EmailMessage } from "cloudflare:email";
import { createMimeMessage } from "mimetext";

// Helper function to calculate size of base64 string
function base64Size(base64String) {
  // Calculate size of decoded base64 - each 4 base64 chars represent 3 bytes
  // Account for padding characters
  const padding = base64String.endsWith('==') ? 2 : base64String.endsWith('=') ? 1 : 0;
  return Math.floor(base64String.length / 4) * 3 - padding;
}

export default {
  // Add a fetch handler for HTTP requests
  async fetch(request, env, ctx) {
    return new Response("Email Worker is running", {
      status: 200,
      headers: { "Content-Type": "text/plain" }
    });
  },

  async email(message, env, ctx) {
    // Log basic info and headers
    console.log("Received email from:", message.from, "to:", message.to);
    console.log("Raw CC Header Value:", message.headers.get('cc'));
    // Convert headers Map to a plain object for logging/sending
    const rawHeaders = Object.fromEntries(message.headers);
    console.log("Raw Headers:", JSON.stringify(rawHeaders, null, 2)); // Pretty print JSON

    // Extract basic email fields
    const sender = message.from;
    const recipient = message.to;
    const subject = message.headers.get("subject") || "";

    try {
      // Parse the email using PostalMime
      const parsedEmail = await PostalMime.parse(message.raw, {
        // Specify base64 as the attachment encoding directly
        attachmentEncoding: "base64"
      });

      // Process attachments - with PostalMime's base64 encoding option
      const attachments = [];
      if (parsedEmail.attachments && parsedEmail.attachments.length > 0) {
        for (const attachment of parsedEmail.attachments) {
          // The content is already base64 encoded by PostalMime
          attachments.push({
            filename: attachment.filename,
            contentType: attachment.mimeType,
            contentDisposition: attachment.disposition,
            contentId: attachment.contentId,
            cid: attachment.contentId ? attachment.contentId.replace(/[<>]/g, '') : null,
            content: attachment.content, // Already base64
            size: base64Size(attachment.content) // Calculate original size without using Buffer
          });
        }
      }

      // Forward the email to the API
      const formData = new FormData();

      // Add basic fields
      formData.append('from_email', sender);
      formData.append('to', recipient);
      formData.append('subject', parsedEmail.subject || subject);
      formData.append('textContent', parsedEmail.text || "");
      formData.append('htmlContent', parsedEmail.html || "");
      formData.append('messageId', message.headers.get("message-id") || "");
      formData.append('date', message.headers.get("date") || "");
      // Add raw headers as a JSON string
      formData.append('rawHeaders', JSON.stringify(rawHeaders));

      // Add attachments as files
      if (parsedEmail.attachments && parsedEmail.attachments.length > 0) {
        for (const attachment of parsedEmail.attachments) {
          try {
            // Create blob directly from base64 string
            const byteString = atob(attachment.content);
            const arrayBuffer = new ArrayBuffer(byteString.length);
            const uint8Array = new Uint8Array(arrayBuffer);

            for (let i = 0; i < byteString.length; i++) {
              uint8Array[i] = byteString.charCodeAt(i);
            }

            // Create blob with proper mime type
            const blob = new Blob([arrayBuffer], { type: attachment.mimeType });

            // Add file to form data with original filename
            formData.append('files', blob, attachment.filename);
            console.log(`Successfully processed attachment: ${attachment.filename} (${attachment.mimeType})`);
          } catch (attachmentError) {
            console.error(`Error processing attachment ${attachment.filename}:`, attachmentError);
            // Continue with other attachments even if one fails
            continue;
          }
        }
      }

      // Determine which API endpoint and key to use based on recipient
      const isLocalRequest = recipient.includes('+local');
      const baseUrl = isLocalRequest ? env.local_base_url?.replace(/\/$/, '') : env.base_url;
      const selectedEndpoint = `${baseUrl}/process-email`;
      const apiKey = isLocalRequest ? env.local_api_key : env.x_api_key;

      const response = await fetch(selectedEndpoint, {
        method: "POST",
        headers: {
          'x-api-key': apiKey
        },
        body: formData
      });

      let responseText;

      if (response.status === 200) {
        responseText = "Your query is being processed.";
      } else if (response.status === 401) {
        responseText = "Please sign up first to use our service.";
      } else if (response.status === 413) {
        responseText = "Your email and attachments combined are too large to process. Please try with smaller attachments or contact support.";

        // Send reply email for 413 error
        try {
          const replyMsg = createMimeMessage();
          replyMsg.setHeader("In-Reply-To", message.headers.get("Message-ID"));
          replyMsg.setSender({ name: "MXGo Support", addr: message.to });
          replyMsg.setRecipient(message.from);
          replyMsg.setSubject(`Re: ${subject}`);
          replyMsg.addMessage({
            contentType: 'text/plain',
            data: responseText
          });

          const replyMessage = new EmailMessage(
            message.to,
            message.from,
            replyMsg.asRaw()
          );

          await message.reply(replyMessage);
          console.log("Sent 413 error reply email to:", message.from);
        } catch (replyError) {
          console.error("Error sending reply email:", replyError);
        }
      } else {
        responseText = "There was an error processing your request. Please try again later.";
      }

      // Return a simple response to Cloudflare
      console.log(`Email processed. API returned ${response.status}. Message: ${responseText}`);

      return {
        forward: false, // Don't forward the email
        seen: true,     // Mark as seen
      };
    } catch (error) {
      console.error("Error processing email:", error);

      // If parsing fails, still try to send basic information
      try {
        // Fallback to the basic data
        const formData = new FormData();
        formData.append('from_email', sender);
        formData.append('to', recipient);
        formData.append('subject', subject);
        formData.append('textContent', "");
        formData.append('htmlContent', "");
        // Add raw headers to fallback as well
        const fallbackHeaders = Object.fromEntries(message.headers);
        formData.append('rawHeaders', JSON.stringify(fallbackHeaders));

        // Still try to send to the API (use same endpoint and key selection logic)
        const isLocalRequest = recipient.includes('+local');
        const baseUrl = isLocalRequest ? env.local_base_url?.replace(/\/$/, '') : env.base_url;
        const selectedEndpoint = `${baseUrl}/process-email`;
        const apiKey = isLocalRequest ? env.local_api_key : env.x_api_key;

        await fetch(selectedEndpoint, {
          method: "POST",
          headers: {
            'x-api-key': apiKey
          },
          body: formData
        });
      } catch (fallbackError) {
        console.error("Error in fallback handling:", fallbackError);
      }

      return {
        forward: false,
        seen: true,
      };
    }
  }
};
