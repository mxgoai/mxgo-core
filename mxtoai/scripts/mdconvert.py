# This is copied from Magentic-one's great repo: https://github.com/microsoft/autogen/blob/v0.4.4/python/packages/autogen-magentic-one/src/autogen_magentic_one/markdown_browser/mdconvert.py
# Thanks to Microsoft researchers for open-sourcing this!
# type: ignore
import base64
import contextlib
import copy
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse

import mammoth
import markdownify
import pandas as pd
import pdfminer
import pdfminer.high_level
import pptx

# File-format detection
import puremagic
import pydub
import requests
import speech_recognition as sr
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter

from mxtoai._logging import get_logger

logger = get_logger(__name__)


class _CustomMarkdownify(markdownify.MarkdownConverter):
    """
    A custom version of markdownify's MarkdownConverter. Changes include:

    - Altering the default heading style to use '#', '##', etc.
    - Removing javascript hyperlinks.
    - Truncating images with large data:uri sources.
    - Ensuring URIs are properly escaped, and do not conflict with Markdown syntax
    """

    def __init__(self, **options: Any):
        options["heading_style"] = options.get("heading_style", markdownify.ATX)
        # Explicitly cast options to the expected type if necessary
        super().__init__(**options)

    def convert_hn(self, n: int, el: Any, text: str, *, convert_as_inline: bool) -> str:
        """Same as usual, but be sure to start with a new line"""
        if not convert_as_inline and not re.search(r"^\n", text):
            return "\n" + super().convert_hn(n, el, text, convert_as_inline=convert_as_inline)  # type: ignore

        return super().convert_hn(n, el, text, convert_as_inline=convert_as_inline)  # type: ignore

    def convert_a(self, el: Any, text: str) -> str:
        """Same as usual converter, but removes Javascript links and escapes URIs."""
        prefix, suffix, text = markdownify.chomp(text)  # type: ignore
        if not text:
            return ""
        href = el.get("href")
        title = el.get("title")

        # Escape URIs and skip non-http or file schemes
        if href:
            try:
                parsed_url = urlparse(href)  # type: ignore
                if parsed_url.scheme and parsed_url.scheme.lower() not in ["http", "https", "file"]:  # type: ignore
                    return f"{prefix}{text}{suffix}"
                href = urlunparse(parsed_url._replace(path=quote(unquote(parsed_url.path))))  # type: ignore
            except ValueError:  # It's not clear if this ever gets thrown
                return f"{prefix}{text}{suffix}"

        # For the replacement see #29: text nodes underscores are escaped
        if (
            self.options["autolinks"]
            and text.replace(r"\_", "_") == href
            and not title
            and not self.options["default_title"]
        ):
            # Shortcut syntax
            return f"<{href}>"
        if self.options["default_title"] and not title:
            title = href
        title_part = ' "{}"'.format(title.replace('"', r"\"")) if title else ""
        return f"{prefix}[{text}]({href}{title_part}){suffix}" if href else text

    def convert_img(self, el: Any, *, convert_as_inline: bool = False) -> str:
        """Same as usual converter, but removes data URIs"""
        alt = el.attrs.get("alt", None) or ""
        src = el.attrs.get("src", None) or ""
        title = el.attrs.get("title", None) or ""
        title_part = ' "{}"'.format(title.replace('"', r"\"")) if title else ""
        if convert_as_inline and el.parent.name not in self.options["keep_inline_images_in"]:
            return alt

        # Remove dataURIs
        if src.startswith("data:"):
            src = src.split(",")[0] + "..."

        return f"![{alt}]({src}{title_part})"

    def convert_soup(self, soup: Any) -> str:
        return super().convert_soup(soup)  # type: ignore


class DocumentConverterResult:
    """The result of converting a document to text."""

    def __init__(self, title: Union[str, None] = None, text_content: str = ""):
        self.title: Union[str, None] = title
        self.text_content: str = text_content


class DocumentConverter:
    """Abstract superclass of all DocumentConverters."""

    def convert(self, local_path: str, **kwargs: Any) -> Union[None, DocumentConverterResult]:
        raise NotImplementedError


class PlainTextConverter(DocumentConverter):
    """Anything with content type text/plain"""

    def convert(self, local_path: str, **kwargs: Any) -> Union[None, DocumentConverterResult]:
        # Guess the content type from any file extension that might be around
        content_type, _ = mimetypes.guess_type("__placeholder" + kwargs.get("file_extension", ""))

        # Only accept text files
        if content_type is None or not content_type.startswith("text/"):
            return None

        # Try to detect if file is binary
        try:
            with Path(local_path).open("rb") as file:
                # Read first chunk of the file
                chunk = file.read(1024)
                if b"\0" in chunk:  # Binary file detection
                    return None

                # Try to decode as UTF-8
                try:
                    chunk.decode("utf-8")
                except UnicodeDecodeError:
                    return None
        except Exception:
            return None

        # If we got here, it's safe to read as text
        try:
            with Path(local_path).open(encoding="utf-8") as fh:
                text_content = fh.read()
            return DocumentConverterResult(
                title=None,
                text_content=text_content,
            )
        except UnicodeDecodeError:
            return None


class HtmlConverter(DocumentConverter):
    """Anything with content type text/html"""

    def convert(self, local_path: str, **kwargs: Any) -> Union[None, DocumentConverterResult]:
        # Bail if not html
        extension = kwargs.get("file_extension", "")
        if extension.lower() not in [".html", ".htm"]:
            return None

        with Path(local_path).open(encoding="utf-8") as fh:
            return self._convert(fh.read())

    def _convert(self, html_content: str) -> Union[None, DocumentConverterResult]:
        """Helper function that converts and HTML string."""
        # Parse the string
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove javascript and style blocks
        for script in soup(["script", "style"]):
            script.extract()

        # Print only the main content
        body_elm = soup.find("body")
        webpage_text = ""
        if body_elm:
            webpage_text = _CustomMarkdownify().convert_soup(body_elm)
        else:
            webpage_text = _CustomMarkdownify().convert_soup(soup)

        # assert isinstance(webpage_text, str)

        return DocumentConverterResult(
            title=None if soup.title is None else soup.title.string, text_content=webpage_text
        )


class WikipediaConverter(DocumentConverter):
    """Handle Wikipedia pages separately, focusing only on the main document content."""

    def convert(self, local_path: str, **kwargs: Any) -> Union[None, DocumentConverterResult]:
        # Bail if not Wikipedia
        extension = kwargs.get("file_extension", "")
        if extension.lower() not in [".html", ".htm"]:
            return None
        url = kwargs.get("url", "")
        if not re.search(r"^https?:\/\/[a-zA-Z]{2,3}\.wikipedia.org\/", url):
            return None

        # Parse the file
        soup = None
        with Path(local_path).open(encoding="utf-8") as fh:
            soup = BeautifulSoup(fh.read(), "html.parser")

        # Remove javascript and style blocks
        for script in soup(["script", "style"]):
            script.extract()

        # Print only the main content
        body_elm = soup.find("div", {"id": "mw-content-text"})
        title_elm = soup.find("span", {"class": "mw-page-title-main"})

        webpage_text = ""
        main_title = None if soup.title is None else soup.title.string

        if body_elm:
            # What's the title
            if title_elm and len(title_elm) > 0:
                main_title = title_elm.string  # type: ignore
                # assert isinstance(main_title, str)

            # Convert the page
            webpage_text = f"# {main_title}\n\n" + _CustomMarkdownify().convert_soup(body_elm)
        else:
            webpage_text = _CustomMarkdownify().convert_soup(soup)

        return DocumentConverterResult(
            title=main_title,
            text_content=webpage_text,
        )


class YouTubeConverter(DocumentConverter):
    """Handle YouTube specially, focusing on the video title, description, and transcript."""

    def _parse_ytinitialdata_from_script(self, script_content: str, metadata: dict[str, str]):
        """Parses ytInitialData from script content and updates metadata."""
        if not script_content or "ytInitialData" not in script_content:
            return

        try:
            # Simplified JSON extraction, assuming it's a valid JS object assignment
            match = re.search(r"var\s+ytInitialData\s*=\s*({.*?});", script_content, re.DOTALL)
            if not match:
                match = re.search(r"window\[\"ytInitialData\"\]\s*=\s*({.*?});", script_content, re.DOTALL)

            if match:
                json_str = match.group(1)
                data = json.loads(json_str)
                attrdesc_node = self._find_key(data, "attributedDescriptionBodyText")
                if attrdesc_node and isinstance(attrdesc_node, dict) and "content" in attrdesc_node:
                    metadata["description"] = str(attrdesc_node["content"])

                video_details_node = self._find_key(data, "videoDetails")
                if isinstance(video_details_node, dict):
                    if video_details_node.get("viewCount"):
                        metadata["interactionCount"] = video_details_node["viewCount"]
                    if video_details_node.get("keywords") and isinstance(video_details_node["keywords"], list):
                        metadata["keywords"] = ", ".join(video_details_node["keywords"])
                    if video_details_node.get("lengthSeconds"):
                        secs = int(video_details_node["lengthSeconds"])
                        mins, secs = divmod(secs, 60)
                        hours, mins = divmod(mins, 60)
                        duration_str = "PT"
                        if hours > 0:
                            duration_str += f"{hours}H"
                        if mins > 0 or hours > 0:
                            duration_str += f"{mins}M"
                        duration_str += f"{secs}S"
                        metadata["duration"] = duration_str
        except Exception:
            logger.debug("Ignoring exception in YouTube ytInitialData parsing", exc_info=True)

    def _extract_youtube_metadata_from_soup(self, soup: BeautifulSoup) -> dict[str, str]:
        metadata: dict[str, str] = {"title": soup.title.string if soup.title else "Untitled"}
        for meta in soup.find_all("meta"):
            for attr_name in ["itemprop", "property", "name"]:
                if meta.has_attr(attr_name):
                    metadata[meta[attr_name]] = meta.get("content", "")
                    break
        # Removed try-except block for script processing, moved to helper
        for script in soup.find_all("script"):
            script_text_content = script.string # Use .string to get script content
            if script_text_content: # Ensure content exists before passing
                self._parse_ytinitialdata_from_script(script_text_content, metadata)
                # If description or other key data is found, we could break early,
                # but multiple script tags might contain parts of ytInitialData or other relevant JSONs.
                # For now, iterate all as before, helper decides if data is relevant.

        return metadata

    def _format_youtube_video_info(self, metadata: dict[str,str]) -> tuple[str, str]:
        webpage_text_parts = []
        title = self._get(metadata, ["title", "og:title", "name"])
        if title:
            webpage_text_parts.append(f"## {title}\n")

        stats_parts = []
        views = self._get(metadata, ["interactionCount"])
        if views:
            stats_parts.append(f"- **Views:** {views}")
        keywords = self._get(metadata, ["keywords"])
        if keywords:
            stats_parts.append(f"- **Keywords:** {keywords}")
        runtime = self._get(metadata, ["duration"])
        if runtime:
            stats_parts.append(f"- **Runtime:** {runtime}")

        if stats_parts:
            webpage_text_parts.append("### Video Metadata")
            webpage_text_parts.extend(stats_parts)
            webpage_text_parts.append("") # Add a newline after stats

        description = self._get(metadata, ["description", "og:description"])
        if description:
            webpage_text_parts.append("### Description")
            webpage_text_parts.append(description)
            webpage_text_parts.append("") # Add a newline after description

        return "\n".join(webpage_text_parts), title or "Untitled YouTube Video"

    def _fetch_youtube_transcript(self, url: str) -> str:
        transcript_text = ""
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        if params.get("v"):
            video_id = str(params["v"][0])
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                transcript_text = SRTFormatter().format_transcript(transcript_list)
            except Exception:
                logger.debug("Ignoring exception in YouTube transcript fetching/formatting", exc_info=True)
        return transcript_text

    def convert(self, local_path: str, **kwargs: Any) -> Union[None, DocumentConverterResult]:
        extension = kwargs.get("file_extension", "")
        url = kwargs.get("url", "")
        if not (extension.lower() in [".html", ".htm"] and url.startswith("https://www.youtube.com/watch?")):
            return None

        try:
            with Path(local_path).open(encoding="utf-8") as fh:
                soup = BeautifulSoup(fh.read(), "html.parser")
        except Exception as e:
            logger.error(f"Failed to read or parse local HTML file {local_path}: {e}")
            return None

        metadata = self._extract_youtube_metadata_from_soup(soup)
        formatted_info, primary_title = self._format_youtube_video_info(metadata)
        transcript_text = self._fetch_youtube_transcript(url)

        webpage_text_parts = ["# YouTube", formatted_info]
        if transcript_text:
            webpage_text_parts.append("### Transcript")
            webpage_text_parts.append(transcript_text)

        final_text_content = "\n".join(filter(None, webpage_text_parts))

        # Ensure title is a string, fallback to soup.title or a generic title
        final_title = primary_title
        if not final_title and soup.title and soup.title.string:
            final_title = soup.title.string
        elif not final_title:
            final_title = "YouTube Video"

        return DocumentConverterResult(
            title=str(final_title), # Ensure title is always a string
            text_content=final_text_content,
        )

    def _get(self, metadata: dict[str, str], keys: list[str], default: Union[str, None] = None) -> Union[str, None]:
        for k in keys:
            if k in metadata:
                return metadata[k]
        return default

    def _find_key(self, json_obj: Any, key: str) -> Union[str, None]:  # TODO: Fix json type
        if isinstance(json_obj, list):
            for elm in json_obj:
                ret = self._find_key(elm, key)
                if ret is not None:
                    return ret
        elif isinstance(json_obj, dict):
            for k in json_obj:
                if k == key:
                    return json_obj[k]
                ret = self._find_key(json_obj[k], key)
                if ret is not None:
                    return ret
        return None


class PdfConverter(DocumentConverter):
    """
    Converts PDFs to Markdown. Most style information is ignored, so the results are essentially plain-text.
    """

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        # Bail if not a PDF
        extension = kwargs.get("file_extension", "")
        if extension.lower() != ".pdf":
            return None

        return DocumentConverterResult(
            title=None,
            text_content=pdfminer.high_level.extract_text(local_path),
        )


class DocxConverter(HtmlConverter):
    """
    Converts DOCX files to Markdown. Style information (e.g.m headings) and tables are preserved where possible.
    """

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        # Bail if not a DOCX
        extension = kwargs.get("file_extension", "")
        if extension.lower() != ".docx":
            return None

        result = None
        with Path(local_path).open("rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)
            html_content = result.value
            return self._convert(html_content)


class XlsxConverter(HtmlConverter):
    """
    Converts XLSX files to Markdown, with each sheet presented as a separate Markdown table.
    """

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        # Bail if not a XLSX
        extension = kwargs.get("file_extension", "")
        if extension.lower() not in [".xlsx", ".xls"]:
            return None

        sheets = pd.read_excel(local_path, sheet_name=None)
        md_content = ""
        for s in sheets:
            md_content += f"## {s}\n"
            html_content = sheets[s].to_html(index=False)
            md_content += self._convert(html_content).text_content.strip() + "\n\n"

        return DocumentConverterResult(
            title=None,
            text_content=md_content.strip(),
        )


class PptxConverter(HtmlConverter):
    """
    Converts PPTX files to Markdown. Supports heading, tables and images with alt text.
    """

    def _process_pptx_shape(self, shape: pptx.shapes.autoshape.Shape, slide_title_shape: Optional[pptx.shapes.autoshape.Shape]) -> str:
        """Processes a single shape from a PPTX slide and returns its markdown representation."""
        shape_md_parts = []
        # Pictures
        if self._is_picture(shape):
            alt_text = ""
            with contextlib.suppress(Exception):
                alt_text = shape._element._nvXxPr.cNvPr.attrib.get("descr", "")  # noqa: SLF001
            filename = re.sub(r"\W", "", shape.name) + ".jpg" # A placeholder name
            shape_md_parts.append(f"![{alt_text if alt_text else shape.name}]({filename})")

        # Tables
        elif self._is_table(shape):
            html_table = "<html><body><table>"
            first_row = True
            for row in shape.table.rows:
                html_table += "<tr>"
                for cell in row.cells:
                    html_table += f"<{'th' if first_row else 'td'}>{html.escape(cell.text)}</{'th' if first_row else 'td'}>"
                html_table += "</tr>"
                first_row = False
            html_table += "</table></body></html>"
            # Assuming self._convert is available from HtmlConverter inheritance
            converted_table = self._convert(html_table)
            if converted_table and converted_table.text_content:
                shape_md_parts.append(converted_table.text_content.strip())

        # Text areas
        elif shape.has_text_frame and shape.text:
            text = shape.text.strip()
            if text: # Only add if there is actual text
                if shape == slide_title_shape:
                    shape_md_parts.append(f"# {text.lstrip()}")
                else:
                    shape_md_parts.append(text)

        return "\n".join(shape_md_parts)

    def _process_pptx_notes_slide(self, slide: pptx.slide.Slide) -> str:
        """Processes the notes slide and returns its markdown representation."""
        notes_md = ""
        if slide.has_notes_slide:
            notes_frame = slide.notes_slide.notes_text_frame
            if notes_frame and notes_frame.text:
                notes_text = notes_frame.text.strip()
                if notes_text:
                    notes_md = f"### Notes:\n{notes_text}"
        return notes_md

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        extension = kwargs.get("file_extension", "")
        if extension.lower() != ".pptx":
            return None

        md_content_parts = []
        try:
            presentation = pptx.Presentation(local_path)
        except Exception as e:
            logger.error(f"Failed to open PPTX file {local_path}: {e}")
            return None

        for slide_num, slide in enumerate(presentation.slides):
            slide_md_parts = [f"<!-- Slide number: {slide_num + 1} -->"]

            slide_title_shape = slide.shapes.title if slide.shapes.has_title else None

            for shape in slide.shapes:
                shape_md = self._process_pptx_shape(shape, slide_title_shape)
                if shape_md:
                    slide_md_parts.append(shape_md)

            notes_md = self._process_pptx_notes_slide(slide)
            if notes_md:
                slide_md_parts.append(notes_md)

            # Join parts for the current slide, filtering out empty strings
            slide_content = "\n".join(filter(None, slide_md_parts)).strip()
            if slide_content:
                 md_content_parts.append(slide_content)

        final_md_content = "\n\n".join(md_content_parts).strip() # Join slides with double newline

        return DocumentConverterResult(
            title=None, # PPTX files don't have a single document title in the same way as others
            text_content=final_md_content,
        )

    def _is_picture(self, shape):
        if shape.shape_type == pptx.enum.shapes.MSO_SHAPE_TYPE.PICTURE:
            return True
        return bool(shape.shape_type == pptx.enum.shapes.MSO_SHAPE_TYPE.PLACEHOLDER and hasattr(shape, "image"))

    def _is_table(self, shape):
        return shape.shape_type == pptx.enum.shapes.MSO_SHAPE_TYPE.TABLE


class MediaConverter(DocumentConverter):
    """
    Abstract class for multi-modal media (e.g., images and audio)
    """

    def _get_metadata(self, local_path):
        exiftool = shutil.which("exiftool")
        if not exiftool:
            return None
        try:
            result = subprocess.run([exiftool, "-json", local_path], capture_output=True, text=True, check=False).stdout # noqa: S603
            return json.loads(result)[0]
        except Exception:
            return None


class WavConverter(MediaConverter):
    """
    Converts WAV files to markdown via extraction of metadata (if `exiftool` is installed), and speech transcription (if `speech_recognition` is installed).
    """

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        # Bail if not a XLSX
        extension = kwargs.get("file_extension", "")
        if extension.lower() != ".wav":
            return None

        md_content = ""

        # Add metadata
        metadata = self._get_metadata(local_path)
        if metadata:
            for f in [
                "Title",
                "Artist",
                "Author",
                "Band",
                "Album",
                "Genre",
                "Track",
                "DateTimeOriginal",
                "CreateDate",
                "Duration",
            ]:
                if f in metadata:
                    md_content += f"{f}: {metadata[f]}\n"

        # Transcribe
        try:
            transcript = self._transcribe_audio(local_path)
            md_content += "\n\n### Audio Transcript:\n" + ("[No speech detected]" if transcript == "" else transcript)
        except Exception:
            md_content += "\n\n### Audio Transcript:\nError. Could not transcribe this audio."

        return DocumentConverterResult(
            title=None,
            text_content=md_content.strip(),
        )

    def _transcribe_audio(self, local_path) -> str:
        recognizer = sr.Recognizer()
        with sr.AudioFile(local_path) as source:
            audio = recognizer.record(source)
            return recognizer.recognize_google(audio).strip()


class Mp3Converter(WavConverter):
    """
    Converts MP3 and M4A files to markdown via extraction of metadata (if `exiftool` is installed), and speech transcription (if `speech_recognition` AND `pydub` are installed).
    """

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        # Bail if not a MP3
        extension = kwargs.get("file_extension", "")
        if extension.lower() not in [".mp3", ".m4a"]:
            return None

        md_content = ""

        # Add metadata
        metadata = self._get_metadata(local_path)
        if metadata:
            for f in [
                "Title",
                "Artist",
                "Author",
                "Band",
                "Album",
                "Genre",
                "Track",
                "DateTimeOriginal",
                "CreateDate",
                "Duration",
            ]:
                if f in metadata:
                    md_content += f"{f}: {metadata[f]}\n"

        # Transcribe
        handle, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(handle)
        try:
            if extension.lower() == ".mp3":
                sound = pydub.AudioSegment.from_mp3(local_path)
            else:
                sound = pydub.AudioSegment.from_file(local_path, format="m4a")
            sound.export(temp_path, format="wav")

            _args = {}
            _args.update(kwargs)
            _args["file_extension"] = ".wav"

            try:
                transcript = super()._transcribe_audio(temp_path).strip()
                md_content += "\n\n### Audio Transcript:\n" + (
                    "[No speech detected]" if transcript == "" else transcript
                )
            except Exception:
                md_content += "\n\n### Audio Transcript:\nError. Could not transcribe this audio."

        finally:
            with contextlib.suppress(Exception):
                pass
            Path(temp_path).unlink()

        # Return the result
        return DocumentConverterResult(
            title=None,
            text_content=md_content.strip(),
        )


class ZipConverter(DocumentConverter):
    """
    Extracts ZIP files to a permanent local directory and returns a listing of extracted files.
    """

    def __init__(self, extract_dir: str = "downloads"):
        """
        Initialize with path to extraction directory.

        Args:
            extract_dir: The directory where files will be extracted. Defaults to "downloads"

        """
        self.extract_dir = extract_dir
        # Create the extraction directory if it doesn't exist
        Path(self.extract_dir).mkdir(parents=True, exist_ok=True)

    def convert(self, local_path: str, **kwargs: Any) -> Union[None, DocumentConverterResult]:
        # Bail if not a ZIP file
        extension = kwargs.get("file_extension", "")
        if extension.lower() != ".zip":
            return None

        # Verify it's actually a ZIP file
        if not zipfile.is_zipfile(local_path):
            return None

        # Extract all files and build list
        with zipfile.ZipFile(local_path, "r") as zip_ref:
            # Extract all files
            zip_ref.extractall(self.extract_dir)
            # Get list of all files
            extracted_files = [
                str(Path(self.extract_dir) / file_path)
                for file_path in zip_ref.namelist()
                if not file_path.endswith("/")
            ]

        # Sort files for consistent output
        extracted_files.sort()

        # Build the markdown content
        md_content = "Downloaded the following files:\n"
        for file in extracted_files:
            md_content += f"* {file}\n"

        return DocumentConverterResult(title="Extracted Files", text_content=md_content.strip())


class ImageConverter(MediaConverter):
    """
    Converts images to markdown via extraction of metadata (if `exiftool` is installed), OCR (if `easyocr` is installed), and description via a multimodal LLM (if an mlm_client is configured).
    """

    def convert(self, local_path, **kwargs) -> Union[None, DocumentConverterResult]:
        # Bail if not a XLSX
        extension = kwargs.get("file_extension", "")
        if extension.lower() not in [".jpg", ".jpeg", ".png"]:
            return None

        md_content = ""

        # Add metadata
        metadata = self._get_metadata(local_path)
        if metadata:
            for f in [
                "ImageSize",
                "Title",
                "Caption",
                "Description",
                "Keywords",
                "Artist",
                "Author",
                "DateTimeOriginal",
                "CreateDate",
                "GPSPosition",
            ]:
                if f in metadata:
                    md_content += f"{f}: {metadata[f]}\n"

        # Try describing the image with GPTV
        mlm_client = kwargs.get("mlm_client")
        mlm_model = kwargs.get("mlm_model")
        if mlm_client is not None and mlm_model is not None:
            md_content += (
                "\n# Description:\n"
                + self._get_mlm_description(
                    local_path, extension, mlm_client, mlm_model, prompt=kwargs.get("mlm_prompt")
                ).strip()
                + "\n"
            )

        return DocumentConverterResult(
            title=None,
            text_content=md_content,
        )

    def _get_mlm_description(self, local_path, extension, client, model, prompt=None):
        if prompt is None or prompt.strip() == "":
            prompt = "Write a detailed caption for this image."

        sys.stderr.write(f"MLM Prompt:\n{prompt}\n")

        data_uri = ""
        with Path(local_path).open("rb") as image_file:
            content_type, encoding = mimetypes.guess_type("_dummy" + extension)
            if content_type is None:
                content_type = "image/jpeg"
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
            data_uri = f"data:{content_type};base64,{image_base64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_uri,
                        },
                    },
                ],
            }
        ]

        response = client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content


class FileConversionError(Exception):
    pass


class UnsupportedFormatError(Exception):
    pass


class MarkdownConverter:
    """
    (In preview) An extremely simple text-based document reader, suitable for LLM use.
    This reader will convert common file-types or webpages to Markdown.
    """

    def __init__(
        self,
        requests_session: Optional[requests.Session] = None,
        mlm_client: Optional[Any] = None,
        mlm_model: Optional[Any] = None,
    ):
        if requests_session is None:
            self._requests_session = requests.Session()
        else:
            self._requests_session = requests_session

        self._mlm_client = mlm_client
        self._mlm_model = mlm_model

        self._page_converters: list[DocumentConverter] = []

        # Register converters for successful browsing operations
        # Later registrations are tried first / take higher priority than earlier registrations
        # To this end, the most specific converters should appear below the most generic converters
        self.register_page_converter(PlainTextConverter())
        self.register_page_converter(HtmlConverter())
        self.register_page_converter(WikipediaConverter())
        self.register_page_converter(YouTubeConverter())
        self.register_page_converter(DocxConverter())
        self.register_page_converter(XlsxConverter())
        self.register_page_converter(PptxConverter())
        self.register_page_converter(WavConverter())
        self.register_page_converter(Mp3Converter())
        self.register_page_converter(ImageConverter())
        self.register_page_converter(ZipConverter())
        self.register_page_converter(PdfConverter())

    def convert(
        self, source: Union[str, requests.Response], **kwargs: Any
    ) -> DocumentConverterResult:  # TODO: deal with kwargs
        """
        Converts a given source (local path, URL, or requests.Response) to markdown.

        Args:
            source: The source to convert (file path, URL, or response object).
            **kwargs: Additional arguments (e.g., file_extension for streams).

        Returns:
            DocumentConverterResult containing the converted text and metadata.

        Raises:
            UnsupportedFormatError: If the file format is not supported.
            FileConversionError: If any other error occurs during conversion.

        """
        # Local path or url
        if isinstance(source, str):
            if source.startswith(("http://", "https://", "file://")):
                return self.convert_url(source, **kwargs)
            return self.convert_local(source, **kwargs)
        # Request response
        if isinstance(source, requests.Response):
            return self.convert_response(source, **kwargs)
        return None

    def convert_local(self, path: str, **kwargs: Any) -> DocumentConverterResult:  # TODO: deal with kwargs
        # Prepare a list of extensions to try (in order of priority)
        ext = kwargs.get("file_extension")
        extensions = [ext] if ext is not None else []

        # Get extension alternatives from the path and puremagic
        path_obj = Path(path)
        ext = path_obj.suffix
        self._append_ext(extensions, ext)
        self._append_ext(extensions, self._guess_ext_magic(path))

        # Convert
        return self._convert(path, extensions, **kwargs)

    # TODO: what should stream's type be? Define proper type for stream.
    def convert_stream(self, stream: Any, **kwargs: Any) -> DocumentConverterResult:  # TODO: deal with kwargs
        # Prepare a list of extensions to try (in order of priority)
        ext = kwargs.get("file_extension")
        extensions = [ext] if ext is not None else []

        # Save the file locally to a temporary file. It will be deleted before this method exits
        handle, temp_path = tempfile.mkstemp()
        fh = os.fdopen(handle, "wb")
        result = None
        try:
            # Write to the temporary file
            content = stream.read()
            if isinstance(content, str):
                fh.write(content.encode("utf-8"))
            else:
                fh.write(content)
            fh.close()

            # Use puremagic to check for more extension options
            self._append_ext(extensions, self._guess_ext_magic(temp_path))

            # Convert
            result = self._convert(temp_path, extensions, **kwargs)
        # Clean up
        finally:
            with contextlib.suppress(Exception):
                fh.close()
            Path(temp_path).unlink()

        return result

    def convert_url(self, url: str, **kwargs: Any) -> DocumentConverterResult:  # TODO: fix kwargs type
        # Send a HTTP request to the URL
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        response = self._requests_session.get(url, stream=True, headers={"User-Agent": user_agent})
        response.raise_for_status()
        return self.convert_response(response, **kwargs)

    def convert_response(
        self, response: requests.Response, **kwargs: Any
    ) -> DocumentConverterResult:  # TODO: fix kwargs type
        # Prepare a list of extensions to try (in order of priority)
        ext = kwargs.get("file_extension")
        extensions = [ext] if ext is not None else []

        # Guess from the mimetype
        content_type = response.headers.get("content-type", "").split(";")[0]
        self._append_ext(extensions, mimetypes.guess_extension(content_type))

        # Read the content disposition if there is one
        content_disposition = response.headers.get("content-disposition", "")
        m = re.search(r"filename=([^;]+)", content_disposition)
        if m:
            path_obj = Path(m.group(1).strip("\"'"))
            ext = path_obj.suffix
            self._append_ext(extensions, ext)

        # Read from the extension from the path
        path_obj = Path(urlparse(response.url).path)
        ext = path_obj.suffix
        self._append_ext(extensions, ext)

        # Save the file locally to a temporary file. It will be deleted before this method exits
        handle, temp_path = tempfile.mkstemp()
        fh = os.fdopen(handle, "wb")
        result = None
        try:
            # Download the file
            for chunk in response.iter_content(chunk_size=512):
                fh.write(chunk)
            fh.close()

            # Use puremagic to check for more extension options
            self._append_ext(extensions, self._guess_ext_magic(temp_path))

            # Convert
            result = self._convert(temp_path, extensions, url=response.url)
        except Exception:
            logger.debug("Ignoring exception during stream conversion main logic", exc_info=True)

        # Clean up
        finally:
            with contextlib.suppress(Exception):
                fh.close()
            Path(temp_path).unlink()

        return result

    def _convert(self, local_path: str, extensions: list[Union[str, None]], **kwargs) -> DocumentConverterResult:
        error_trace = ""
        for ext in [*extensions, None]:  # Try last with no extension
            for converter in self._page_converters:
                _kwargs = copy.deepcopy(kwargs)

                # Overwrite file_extension appropriately
                if ext is None:
                    if "file_extension" in _kwargs:
                        del _kwargs["file_extension"]
                else:
                    _kwargs.update({"file_extension": ext})

                # Copy any additional global options
                if "mlm_client" not in _kwargs and self._mlm_client is not None:
                    _kwargs["mlm_client"] = self._mlm_client

                if "mlm_model" not in _kwargs and self._mlm_model is not None:
                    _kwargs["mlm_model"] = self._mlm_model

                # If we hit an error log it and keep trying
                try:
                    res = converter.convert(local_path, **_kwargs)
                except Exception:
                    error_trace = ("\n\n" + traceback.format_exc()).strip()

                if res is not None:
                    # Normalize the content
                    res.text_content = "\n".join([line.rstrip() for line in re.split(r"\r?\n", res.text_content)])
                    res.text_content = re.sub(r"\n{3,}", "\n\n", res.text_content)

                    # TODO: Add further post-processing if necessary
                    return res

        # If we got this far without success, report any exceptions
        if len(error_trace) > 0:
            msg = f"Could not convert '{local_path}' to Markdown. File type was recognized as {extensions}. While converting the file, the following error was encountered:\n\n{error_trace}"
            raise FileConversionError(msg)

        # Nothing can handle it!
        msg = f"Could not convert '{local_path}' to Markdown. The formats {extensions} are not supported."
        raise UnsupportedFormatError(msg)

    def _append_ext(self, extensions, ext):
        """Append a unique non-None, non-empty extension to a list of extensions."""
        if ext is None:
            return
        ext = ext.strip()
        if ext == "":
            return
        # if ext not in extensions:
        if True:
            extensions.append(ext)

    def _guess_ext_magic(self, path):
        """Use puremagic (a Python implementation of libmagic) to guess a file's extension based on the first few bytes."""
        # Use puremagic to guess
        try:
            guesses = puremagic.magic_file(path)
            if len(guesses) > 0:
                ext = guesses[0].extension.strip()
                if len(ext) > 0:
                    return ext
        except FileNotFoundError:
            pass
        except IsADirectoryError:
            pass
        except PermissionError:
            pass
        return None

    def register_page_converter(self, converter: DocumentConverter) -> None:
        """Register a page text converter."""
        self._page_converters.insert(0, converter)
