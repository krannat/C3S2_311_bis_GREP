GREP is a software package for collecting and archiving GNSS observational data in
RINEX format together with GNSS sites’ metadata (logfiles). GREP acts as a central repository for GNSS-PWV reanalysis supporting global climate monitoring.

All RINEX files are gathered into one global repository with unified format and no site duplicates. The RINEX file names are harmonized (according to long 9char name standard), 
while original provenance (agency, repository, original filename) is preserved in internal data tables. All files are stored in UNIX *.gz format. Site logfiles are collected 
whenever available to support metadata validation and long-term analysis. Every RINEX file undergoes QC, checking metadata consistency between RINEX headers and site logfiles, 
with the comparison results stored for each file.

This GitHub repository consists the Python scripts in “grep”, documentation with instructions for installation and usage, and a *.7z compressed HTML document describing 
the structure and functions of the software package.
