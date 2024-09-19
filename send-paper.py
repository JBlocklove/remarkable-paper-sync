#!/home/jason/repos/remarkable/remarkable-paper-sync/venv/bin/python

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import paramiko
import yaml
from PyPDF2 import PdfReader
from scp import SCPClient


def setup_logging():
    """Configure the logging module."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def read_config(config_file):
    """
    Read the YAML configuration file.

    Parameters:
        config_file (str): Path to the configuration file.

    Returns:
        dict: Configuration data.
    """
    if not os.path.isfile(config_file):
        logging.error(f"Configuration file '{config_file}' not found.")
        sys.exit(1)
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config


def interactive_mode():
    """
    Collect metadata from the user interactively.

    Returns:
        tuple: (info_dict, destination, file_path)
    """
    info_dict = {}
    info_dict["authors"] = input("Authors (comma-separated): ").split(",")
    info_dict["title"] = input("Title: ")
    info_dict["tags"] = input("Tags (comma-separated): ").split(",")
    destination = input("Destination path (leave blank if default): ")
    file_path = input("File path (leave blank if added as an option): ")

    return info_dict, destination, file_path


def parse_papis_info(info_file):
    """
    Parse metadata from a Papis info.yaml file.

    Parameters:
        info_file (str): Path to the Papis info.yaml file.

    Returns:
        tuple: (info_dict, absolute_file_path)
    """
    with open(info_file, 'r') as f:
        papis_info = yaml.safe_load(f)

    # Extract authors
    authors = [
        f"{author['given']} {author['family']}"
        for author in papis_info.get("author_list", [])
    ]
    print(authors)

    # Extract title and tags
    title = papis_info.get("title", "Untitled")

    # Extract tags and ensure it's a list
    tags = papis_info.get("tags", [])
    if isinstance(tags, str):
        # Optionally split tags if they are comma-separated
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
    """
    Create the document metadata JSON content.

    Parameters:
        info_dict (dict): Document metadata.

    Returns:
        str: JSON string of the metadata.
    """
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
    """
    Create the document content JSON, including page and tag information.

    Parameters:
        info_dict (dict): Document metadata.
        filename (str): Path to the PDF file.

    Returns:
        str: JSON string of the content.
    """
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
            "authors": [author + '; ' for author in info_dict["authors"]],
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
    """
    Send the document and metadata to the reMarkable tablet.

    Parameters:
        info_dict (dict): Document metadata.
        filename (str): Path to the PDF file.
        destination (str): Destination path on the reMarkable tablet.
        configs (dict): Configuration data.
    """
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
        # os.remove("doc.metadata")
        # os.remove("doc.content")

        # Restart xochitl before closing ssh
        time.sleep(5)
        stdin, stdout, stderr = ssh.exec_command(f"systemctl restart xochitl")
        ssh.close()
        logging.info("File transfer complete.")


def parse_arguments():
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    default_config_path = os.path.join(xdg_config_home, 'papis', 'remarkableconfig.yaml')

    parser = argparse.ArgumentParser(
        description="Sync papers from Papis to a reMarkable tablet while preserving metadata."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='Use interactive mode to enter metadata.'
    )
    group.add_argument(
        '-p', '--papis-info',
        metavar='<file>',
        help='Path to a Papis info.yaml file for metadata.'
    )

    parser.add_argument(
        '-f', '--file',
        metavar='<paper.pdf>',
        help='Path to the paper PDF file.'
    )
    parser.add_argument(
        '-d', '--destination',
        metavar='<path>',
        help='Destination path on the reMarkable tablet.'
    )
    parser.add_argument(
        '-c', '--config',
        metavar='<file>',
        default=default_config_path,
        help=f"Path to the configuration file (default: {default_config_path})."
    )

    return parser.parse_args()


def main():
    """Main function of the script."""
    setup_logging()
    args = parse_arguments()
    configs = read_config(args.config)

    # Initialize variables
    info_dict = {}
    filename = args.file
    destination = args.destination

    # Handle interactive mode
    if args.interactive:
        logging.info("Running in interactive mode.")
        info_dict, interactive_destination, interactive_filename = interactive_mode()
        if interactive_filename:
            filename = interactive_filename
        if interactive_destination:
            destination = interactive_destination
    else:
        if not args.papis_info:
            logging.error("You must specify a Papis info file with -p or --papis-info.")
            sys.exit(1)
        logging.info(f"Parsing Papis info file: {args.papis_info}")
        info_dict, filename = parse_papis_info(args.papis_info)
        print(info_dict)

    # Validate filename
    if not filename:
        logging.error("No file specified to send.")
        sys.exit(1)
    if not os.path.isfile(filename):
        logging.error(f"The file '{filename}' does not exist.")
        sys.exit(1)

    # Set default destination if not provided
    if not destination:
        destination = configs["defaults"].get("remarkable_paper_dir", "/")
        logging.info(f"No destination specified. Using default: {destination}")

    # Proceed to send the paper
    send_to_remarkable(info_dict, filename, destination, configs)


if __name__ == "__main__":
    main()

