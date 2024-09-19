import json
import logging
import os
import sys
import time
import uuid

import paramiko
import yaml
from PyPDF2 import PdfReader
from scp import SCPClient


def read_config(config_file):
    """Read the YAML configuration file."""
    if not os.path.isfile(config_file):
        logging.error(f"Configuration file '{config_file}' not found.")
        sys.exit(1)
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config


def parse_papis_info(info_file):
    """Parse metadata from a Papis info.yaml file."""
    with open(info_file, 'r') as f:
        papis_info = yaml.safe_load(f)

    # Extract authors
    authors = []
    author_list = papis_info.get("author_list")
    if author_list:
        # Use author_list if available
        for author in author_list:
            given = author.get('given', '').strip()
            family = author.get('family', '').strip()
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)
            elif given:
                authors.append(given)
    else:
        # Fallback to parsing the 'author' field
        author_str = papis_info.get("author", "")
        if author_str:
            # Split the author string by ' and '
            author_entries = [a.strip() for a in author_str.split(' and ')]
            for entry in author_entries:
                # Assuming format "Family, Given"
                if ',' in entry:
                    family, given = [s.strip() for s in entry.split(',', 1)]
                    authors.append(f"{given} {family}")
                else:
                    authors.append(entry)
        else:
            logging.warning("No author information found.")

    # Extract title
    title = papis_info.get("title", "Untitled")

    # Extract tags and ensure it's a list
    tags = papis_info.get("tags", [])
    if isinstance(tags, str):
        # Split tags if they are comma-separated
        tags = [tag.strip() for tag in tags.split(',')]
    elif not isinstance(tags, list):
        tags = []

    info_dict = {
        "authors": authors,
        "title": title,
        "tags": tags,
    }

    # Get the directory of the info.yaml file
    info_dir = os.path.dirname(os.path.abspath(info_file))

    # Handle the case where 'files' might be empty or missing
    files_list = papis_info.get("files", [])
    if not files_list:
        logging.error(f"No files listed in {info_file}")
        sys.exit(1)

    # The file path is relative to the info.yaml file
    relative_file_path = files_list[0]

    # Construct the absolute path
    absolute_file_path = os.path.join(info_dir, relative_file_path)

    # Verify that the file exists
    if not os.path.isfile(absolute_file_path):
        logging.error(f"The file {absolute_file_path} does not exist.")
        sys.exit(1)

    return info_dict, absolute_file_path


def create_doc_metadata_json(info_dict):
    """Create the document metadata JSON content."""
    metadata_dict = {
        "deleted": "false",
        "lastModified": str(int(time.time())),
        "lastOpened": str(int(time.time())),
        "lastOpenedPage": 0,
        "metadatamodified": "false",
        "parent": "PARENT_UUID",
        "pinned": "false",
        "synced": "false",
        "type": "DocumentType",
        "version": 2,
        "visibleName": info_dict["title"],
    }

    metadata_json = json.dumps(metadata_dict, indent=4)
    return metadata_json


def create_doc_content_json(info_dict, filename):
    """Create the document content JSON, including page and tag information."""
    default_content = {
        "coverPageNumber": -1,
        "dummyDocument": False,
        "extraMetadata": {},
        "fileType": "pdf",
        "fontName": "",
        "formatVersion": 1,
        "lastOpenedPage": 0,
        "lineHeight": -1,
        "margins": 100,
        "orientation": "portrait",
    }

    size_in_bytes = os.path.getsize(filename)
    with open(filename, 'rb') as file:
        num_pages = len(PdfReader(file).pages)

    content_dict = {
        "documentMetadata": {
            "authors": info_dict["authors"],
            "title": info_dict["title"],
        },
        "tags": [{"name": tag.strip(), "timestamp": str(int(time.time()))} for tag in info_dict["tags"]],
        "sizeInBytes": str(size_in_bytes),
        "originalPageCount": num_pages,
        "pageCount": num_pages,
        "pages": [str(uuid.uuid4()) for _ in range(num_pages)],
        "redirectionPageMap": list(range(num_pages)),
    }

    content_dict.update(default_content)

    content_json = json.dumps(content_dict, indent=4)
    return content_json


def send_to_remarkable(info_dict, filename, destination, configs):
    """Send the document and metadata to the reMarkable tablet."""
    metadata_json = create_doc_metadata_json(info_dict)
    content_json = create_doc_content_json(info_dict, filename)

    # Create temporary JSON files
    with open("doc.metadata", "w") as f:
        f.write(metadata_json)

    with open("doc.content", "w") as f:
        f.write(content_json)

    ssh_host = configs["ssh_configs"]["ssh_host"]
    ssh_user = configs["ssh_configs"]["ssh_user"]
    ssh_port = configs["ssh_configs"].get("ssh_port", 22)
    ssh_key_path = configs["ssh_configs"].get("ssh_key", "~/.ssh/remarkable")
    remarkable_script = configs["ssh_configs"].get(
        "remarkable_script", "/home/root/remarkable-paper-sync/remarkable-add-paper"
    )

    # Initialize SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Expand the SSH key path
    ssh_key_path = os.path.expanduser(ssh_key_path)
    private_key = paramiko.RSAKey.from_private_key_file(ssh_key_path)

    try:
        # Connect to the reMarkable tablet
        logging.info(f"Connecting to reMarkable at {ssh_host}:{ssh_port}...")
        ssh.connect(hostname=ssh_host, port=ssh_port, username=ssh_user, pkey=private_key)

        # Use SCP to transfer files
        with SCPClient(ssh.get_transport()) as scp:
            logging.info("Transferring files to reMarkable...")
            scp.put("doc.metadata", "/home/root/remarkable-paper-sync/doc.metadata")
            scp.put("doc.content", "/home/root/remarkable-paper-sync/doc.content")

            # Transfer the PDF file
            remote_pdf_path = "/home/root/remarkable-paper-sync/" + os.path.basename(filename)
            scp.put(filename, remote_pdf_path)

        # Prepare the command to run on the reMarkable tablet
        command = (
            f"{remarkable_script} '{destination}' "
            f"'/home/root/remarkable-paper-sync/doc.metadata' "
            f"'/home/root/remarkable-paper-sync/doc.content' "
            f"'{remote_pdf_path}' '{info_dict['title']}'"
        )

        # Execute the command
        logging.info("Executing command on reMarkable...")
        stdin, stdout, stderr = ssh.exec_command(command)

        # Handle the output and errors
        stdout_str = stdout.read().decode().strip()
        stderr_str = stderr.read().decode().strip()

        if stdout_str:
            logging.info(f"STDOUT:\n{stdout_str}")
        if stderr_str:
            logging.error(f"STDERR:\n{stderr_str}")

    except paramiko.ssh_exception.AuthenticationException:
        logging.error("Authentication failed, please verify your SSH credentials.")
        sys.exit(1)
    except paramiko.ssh_exception.NoValidConnectionsError:
        logging.error("Unable to connect to the reMarkable tablet. Please check the IP address and network connection.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        # Clean up local files
        os.remove("doc.metadata")
        os.remove("doc.content")
        ssh.exec_command("systemctl restart xochitl")
        ssh.close()
        logging.info("File transfer complete.")

