# Remarkable Paper Sync
This is a program (or set of programs) intended to allow a user to send a paper/book/etc. to their reMarkable device with accompanying metadata that the reMarkable can display. It relies on a local Python program to package the metadata and send it to the tablet, and a program on the reMarkable which will handle final renaming and placement due to the flattened file storage method that the reMarkable software uses.

## TODO:
 - [ ] Sort out path issues
    - Determine ensure paths will always work, regardless of where the script is called from
    - Mostly need to fix that papis yaml files using a relative path to the pdf
 - [ ] Determine config location and its affect on paths
    - Maybe XDG_CONFIG_HOME?
 - [ ] Set up method to integrate program with papis citation manager
 - [ ] Create Zotero plugin and parser
 - [ ] Comment and document
