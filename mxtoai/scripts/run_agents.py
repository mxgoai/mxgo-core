"""
Helper functions for processing and describing different file types for the email deep research agent.

This module provides functions to extract descriptions and content from various file types
including images, documents, and archives for use in the research process.
"""

import os
import shutil
import textwrap
from pathlib import Path


def get_image_description(file_name: str, question: str, visual_inspection_tool) -> str:
    """
    Get a description of an image.

    Args:
        file_name: Path to the image file
        question: Question to guide the image description
        visual_inspection_tool: Tool for visual inspection

    Returns:
        str: Description of the image

    """
    prompt = (
        f"Write a caption of 5 sentences for this image. Pay special attention to any details "
        f"that might be useful for someone answering the following question:\n"
        f"{question}. But do not try to answer the question directly!\n"
        f"Do not add any information that is not present in the image."
    )
    return visual_inspection_tool(image_path=file_name, question=prompt)


def get_document_description(file_path: str, question: str, document_inspection_tool) -> str:
    """
    Get a description of a document.

    Args:
        file_path: Path to the document file
        question: Question to guide the document description
        document_inspection_tool: Tool for document inspection

    Returns:
        str: Description of the document

    """
    prompt = (
        f"Write a caption of 5 sentences for this document. Pay special attention to any details "
        f"that might be useful for someone answering the following question:\n"
        f"{question}. But do not try to answer the question directly!\n"
        f"Do not add any information that is not present in the document."
    )
    return document_inspection_tool.forward_initial_exam_mode(file_path=file_path, question=prompt)


def get_single_file_description(file_path: str, question: str, visual_inspection_tool, document_inspection_tool):
    """
    Get a description of a single file based on its type.

    Args:
        file_path: Path to the file
        question: Question to guide the file description
        visual_inspection_tool: Tool for visual inspection
        document_inspection_tool: Tool for document inspection

    Returns:
        str: Description of the file

    """
    file_extension = file_path.split(".")[-1]
    if file_extension in ["png", "jpg", "jpeg"]:
        file_description = f" - Attached image: {file_path}"
        img_desc = get_image_description(file_path, question, visual_inspection_tool)
        file_description += f"\n     -> Image description: {img_desc}"
        return file_description

    if file_extension in ["pdf", "xls", "xlsx", "docx", "doc", "xml"]:
        file_description = f" - Attached document: {file_path}"
        image_path = file_path.split(".")[0] + ".png"
        if Path(image_path).exists():
            description = get_image_description(image_path, question, visual_inspection_tool)
        else:
            description = get_document_description(file_path, question, document_inspection_tool)
        file_description += f"\n     -> File description: {description}"
        return file_description

    if file_extension in ["mp3", "m4a", "wav"]:
        return f" - Attached audio: {file_path}"

    return f" - Attached file: {file_path}"


def get_zip_description(file_path: str, question: str, visual_inspection_tool, document_inspection_tool):
    """
    Get a description of the contents of a zip file.

    Args:
        file_path: Path to the zip file
        question: Question to guide the description
        visual_inspection_tool: Tool for visual inspection
        document_inspection_tool: Tool for document inspection

    Returns:
        str: Description of the zip contents

    """
    folder_path = file_path.replace(".zip", "")
    os.makedirs(folder_path, exist_ok=True)
    shutil.unpack_archive(file_path, folder_path)

    prompt_use_files = ""
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            description = get_single_file_description(
                file_path, question, visual_inspection_tool, document_inspection_tool
            )
            prompt_use_files += "\n" + textwrap.indent(description, prefix="    ")
    return prompt_use_files
