#!./venv/bin/python3

import yaml
import json
import os
import PyPDF2
import uuid
import time
import getopt
import sys

def read_config(config_file):
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

    authors = [papis_info["author_list"][i]["given"] + " " + papis_info["author_list"][i]["family"] for i in range(len(papis_info["author_list"]))]
    title = papis_info["title"]
    tags = papis_info["tags"]

    info_dict = {
        "authors": authors,
        "title": title,
        "tags": tags,
    }

    return info_dict, papis_info["files"][0]

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

    # scp files to remarkable
    if configs["ssh_configs"]["ssh_bin"] == "sshpass":
        os.system("sshpass -p %s scp doc.metadata doc.content %s %s@%s:/home/root/remarkable-paper-sync" % (configs["ssh_configs"]["ssh_passwd"], filename, configs["ssh_configs"]["ssh_user"], configs["ssh_configs"]["ssh_host"]))
        os.system("sshpass -p %s ssh %s@%s 'cd /home/root/remarkable-paper-sync; ./remarkable-add-paper %s doc.metadata doc.content %s %s'" % (configs["ssh_configs"]["ssh_passwd"], configs["ssh_configs"]["ssh_user"], configs["ssh_configs"]["ssh_host"], destination, filename, info_dict["title"]))
        os.system("rm doc.metadata doc.content")


def check_prerequisites():
    # check if sshpass is installed
    path=os.system("which sshpass")
    if path == "":
        print("sshpass is not installed. Please install it and try again.")
        sys.exit(2)

def main():


    usage = "Usage: send_paper.py [--help] --interactive | --parser <papis/zotero/bibtex> --file <filename> --destination <destination>\n\n\t-h|--help: Prints this usage message\n\n\t-i|--interactive: Use interactive mode to enter metadata. Takes priority over other options.\n\n\t-p|--papis <info file>: Path to a papis file for metadata.\n\n\t-f|--file <paper pdf>: Path to the paper being sent to the remarkable.\n\n\t-d|--destination <path on remarkable>: The path to the directory on the remarkable to send the paper."

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hip:f:d:", ["help", "interactive", "papis-info ", "file ", "destination "])
    except getopt.GetoptError as err:
        print(err)
        print(usage)
        sys.exit(2)

    interactive = True

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
        else:
            assert False, "unhandled option"

    configs = read_config("./config")

    #info_dict, filename = parse_papis_info("test.yaml")
    #destination = configs["defaults"]["remarkable_paper_dir"]

    if interactive:
        info_dict, interactive_destination, interactive_filename = interactive_mode()
    else:
        info_dict = parse_papis_info(info_file)


    if interactive_filename:
        filename = interactive_filename

    if interactive_destination:
        destination = interactive_destination
    elif not destination:
        destination = configs["defaults"]["remarkable_paper_dir"]

    send_to_remarkable(info_dict, filename, destination, configs)

if __name__ == "__main__":
    main()
