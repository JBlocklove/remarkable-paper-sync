#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
import sys

import yaml

import papis.api as papi

from papersync import (
    read_config,
    parse_papis_info,
    send_to_remarkable,
)


def setup_logging():
    """Configure the logging module."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def request_papis_library():
    """Ask the user to select a Papis library."""
    libs = papi.get_libraries()
    for index, item in enumerate(libs, start=1):
        print(f"{index}. {item}")

    while True:
        try:
            choice = int(input("Please select an item by entering its number: "))

            if 1 <= choice <= len(libs):
                selected_item = libs[choice - 1]
                return selected_item
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Invalid input. Please enter a numerical value.")
            sys.exit(1)


def get_papis_paper(library):
    """Get a list of papers from Papis using 'papis list --info'."""
    try:
        docs = papi.get_all_documents_in_lib(library)
        doc = papi.pick_doc(docs)

        return doc[0].get_info_file()
    except subprocess.CalledProcessError:
        logging.error("Failed to pick paper. Is Papis installed and configured correctly?")
        sys.exit(1)


def parse_selection(selection, max_index):
    """Parse a selection string into a list of indices."""
    indices = []
    tokens = [s.strip() for s in selection.split(',')]
    for token in tokens:
        if '-' in token:
            start_str, end_str = token.split('-', 1)
            try:
                start = int(start_str)
                end = int(end_str)
                if start < 1 or end > max_index or start > end:
                    raise ValueError
                indices.extend(range(start - 1, end))
            except ValueError:
                logging.error(f"Invalid range '{token}'.")
                sys.exit(1)
        else:
            try:
                idx = int(token)
                if idx < 1 or idx > max_index:
                    raise ValueError
                indices.append(idx - 1)
            except ValueError:
                logging.error(f"Invalid selection '{token}'.")
                sys.exit(1)
    return sorted(set(indices))



def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Send papers from Papis to the reMarkable tablet."
    )
    parser.add_argument(
        '-d', '--destination',
        metavar='<path>',
        help='Destination path on the reMarkable tablet.'
    )
    parser.add_argument(
        '-c', '--config',
        metavar='<file>',
        help='Path to the configuration file.'
    )
    args = parser.parse_args()

    # Read configuration
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    default_config_path = os.path.join(xdg_config_home, 'papis', 'remarkableconfig.yaml')
    config_file = args.config if args.config else default_config_path
    configs = read_config(config_file)

    # Get list of papers
    library = request_papis_library()
    paper_info = get_papis_paper(library)

    # User selects papers
    logging.info(f"Selected paper: {paper_info}")

    # Use the provided destination or the default
    destination = args.destination if args.destination else configs["defaults"].get("remarkable_paper_dir", "/")

    logging.info(f"Processing paper: {paper_info}")
    info_dict, filename = parse_papis_info(paper_info)
    send_to_remarkable(info_dict, filename, destination, configs)

if __name__ == "__main__":
    main()
