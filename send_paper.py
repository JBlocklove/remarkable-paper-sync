#!./venv/bin/python3

import yaml
import json
import os
import PyPDF2
import uuid
import time
import getopt
import sys
import paramiko
from scp import SCPClient

def read_config(config_file):
    if not os.path.isfile(config_file):
        print(f"Error: Configuration file '{config_file}' not found.")
        sys.exit(1)
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config

def interactive_mode():
    # get info from user
    info_dict = {}
    info_dict["authors"] = input("Authors: ").split(",")
    info_dict["title"] = input("Title: ")
    info_dict["tags"] = input("Tags: ").split(",")
    destination = input("Destination path (leave blank if default): ")
    file_path = input("File path (leave blank if added as an option): ")

    return info_dict, destination, file_path

def parse_papis_info(info_file):
    with open(info_file, 'r') as f:
        papis_info = yaml.safe_load(f)

    # Extract authors
    authors = [
        f"{author['given']} {author['family']}"
        for author in papis_info.get("author_list", [])
    ]

    # Extract title and tags
    title = papis_info.get("title", "Untitled")
    tags = papis_info.get("tags", [])

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
        print(f"Error: No files listed in {info_file}")
        sys.exit(1)

    # The file path is relative to the info.yaml file
    relative_file_path = files_list[0]

    # Construct the absolute path
    absolute_file_path = os.path.join(info_dir, relative_file_path)

    # Verify that the file exists
    if not os.path.isfile(absolute_file_path):
        print(f"Error: The file {absolute_file_path} does not exist.")
        sys.exit(1)

    return info_dict, absolute_file_path

def parse_zotero_info(info_file):
    pass

def parse_bibtex_info(info_file):
    pass

def create_doc_metadata_json(info_dict):
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
        "version": 2, # no idea what version should be at this point, but 2 seems to work just fine
        "visibleName": info_dict["title"],
    }

    metadata_json = json.dumps(metadata_dict, indent=4)
    return metadata_json


def create_doc_content_json(info_dict,filename):
    # "docuemnt metadata"
        # authors
        # title
    # pages
    # tags
        # name
        # timestamp
    # size in bytes

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
    file = open(filename, 'rb')
    num_pages = len(PyPDF2.PdfReader(file).pages)
    file.close()

    content_dict = {
        "documentMetadata": {
            "authors": info_dict["authors"],
            "title": info_dict["title"],
        },
        "tags": [{"name": tag, "timestamp": str(int(time.time()))} for tag in info_dict["tags"]],
    }


    content_dict["sizeInBytes"] = str(size_in_bytes)
    content_dict["originalPageCount"] = num_pages
    content_dict["pageCount"] = num_pages
    content_dict["pages"] = [str(uuid.uuid4()) for i in range(num_pages)]
    content_dict["redirectionPageMap"] = list(range(num_pages))

    content_dict.update(default_content)

    content_json = json.dumps(content_dict, indent=4)
    return content_json


def send_to_remarkable(info_dict, filename, destination, configs):
    metadata_json = create_doc_metadata_json(info_dict)
    content_json = create_doc_content_json(info_dict, filename)

    # create json files
    with open ("doc.metadata", "w") as f:
        f.write(metadata_json)

    with open ("doc.content", "w") as f:
        f.write(content_json)

    ssh_host = configs["ssh_configs"]["ssh_host"]
    ssh_user = configs["ssh_configs"]["ssh_user"]
    ssh_port = configs["ssh_configs"].get("ssh_port", 22)
    ssh_key_path = configs["ssh_configs"].get("ssh_key", "~/.ssh/remarkable")
    remarkable_script = configs["ssh_configs"].get("remarkable_script", "/home/root/remarkable-paper-sync/remarkable-add-paper")

    # Initialize SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Expand the SSH key path
    ssh_key_path = os.path.expanduser(ssh_key_path)
    private_key = paramiko.RSAKey.from_private_key_file(ssh_key_path)

    try:
        # Connect to the reMarkable tablet
        ssh.connect(hostname=ssh_host, port=ssh_port, username=ssh_user, pkey=private_key)

        # Use SCP to transfer files
        with SCPClient(ssh.get_transport()) as scp:
            # Transfer the metadata and content files
            scp.put("doc.metadata", "/home/root/remarkable-paper-sync/doc.metadata")
            scp.put("doc.content", "/home/root/remarkable-paper-sync/doc.content")

            # Transfer the PDF file
            remote_pdf_path = "/home/root/remarkable-paper-sync/" + os.path.basename(filename)
            scp.put(filename, remote_pdf_path)

        # Prepare the command to run on the reMarkable tablet
        command = f"{remarkable_script} '{destination}' '/home/root/remarkable-paper-sync/doc.metadata' '/home/root/remarkable-paper-sync/doc.content' '{remote_pdf_path}' '{info_dict['title']}'"

        # Execute the command
        stdin, stdout, stderr = ssh.exec_command(command)

        # Handle the output and errors
        stdout_str = stdout.read().decode()
        stderr_str = stderr.read().decode()

        if stdout_str:
            print(f"STDOUT:\n{stdout_str}")
        if stderr_str:
            print(f"STDERR:\n{stderr_str}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Clean up local files
        os.remove("doc.metadata")
        os.remove("doc.content")
        ssh.exec_command(f"systemctl restart xochitl")
        ssh.close()

def main():
    # Initialize variables
    interactive = False
    info_file = None
    filename = None
    destination = None
    config_file = None

    # Set default config path
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    default_config_path = os.path.join(xdg_config_home, 'papis', 'config.yaml')



    usage = """
    Usage: send_paper.py [options]

    Options:
        -h, --help              Prints this usage message
        -i, --interactive       Use interactive mode to enter metadata. Takes priority over other options.
        -p, --papis-info <file> Path to a Papis info.yaml file for metadata.
        -f, --file <paper pdf>  Path to the paper being sent to the reMarkable.
        -d, --destination <path> The path on the reMarkable to send the paper.
        -c, --config <file>     Path to the configuration file (defaults to XDG_CONFIG_HOME/papis/config.yaml).
    """

    # Parse command-line arguments
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hip:f:d:c:", ["help", "interactive", "papis-info=", "file=", "destination=", "config="])
    except getopt.GetoptError as err:
        print(err)
        print(usage)
        sys.exit(2)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(usage)
            sys.exit()
        elif opt in ("-i", "--interactive"):
            interactive = True
        elif opt in ("-p", "--papis-info"):
            interactive = False
            info_file = arg
        elif opt in ("-f", "--file"):
            filename = arg
        elif opt in ("-d", "--destination"):
            destination = arg
        elif opt in ("-c", "--config"):
            config_file = arg
        else:
            assert False, "unhandled option"

    # Read the configuration file
    if not config_file:
        config_file = default_config_path

    configs = read_config(config_file)

    # Handle interactive mode
    if interactive:
        info_dict, interactive_destination, interactive_filename = interactive_mode()
        if interactive_filename:
            filename = interactive_filename
        if interactive_destination:
            destination = interactive_destination
    else:
        if not info_file:
            print("Error: You must specify a Papis info file with -p or --papis-info.")
            sys.exit(1)
        info_dict, filename = parse_papis_info(info_file)

    # Set default destination if not provided
    if not destination:
        destination = configs["defaults"]["remarkable_paper_dir"]

    # Check if the filename is set
    if not filename:
        print("Error: No file specified to send.")
        sys.exit(1)



    # Proceed to send the paper
    send_to_remarkable(info_dict, filename, destination, configs)

if __name__ == "__main__":
    main()
