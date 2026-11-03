GREP is a software package for collecting and archiving GNSS observational data in
RINEX format together with GNSS sites’ metadata (logfiles). GREP acts as a central repository for GNSS-PWV reanalysis supporting global climate monitoring.

All RINEX files are gathered into one global repository with unified format and no site duplicates. The RINEX file names are harmonized (according to long 9char name standard), 
while original provenance (agency, repository, original filename) is preserved in internal data tables. All files are stored in UNIX *.gz format. Site logfiles are collected 
whenever available to support metadata validation and long-term analysis. Every RINEX file undergoes QC, checking metadata consistency between RINEX headers and site logfiles, 
with the comparison results stored for each file.

This GitHub repository consists the Python scripts in “grep”, documentation with instructions for installation and usage, and a *.7z compressed HTML document describing 
the structure and functions of the software package.

The packages needed to run the GREP are listed in the requirements.txt . 

EGM2008_WGS84 1x1 minutes grid interpolator (interp_1min.f) is a program for a global grid of regularly spaced point values to selected scattered coordinates. The executable must be compiled from source interp_1min.f into /EGM2008_WGS84 . The ca 1 GB grid-file must be decompressed and installed to the same directory. After compilation, run a test by comparing the sample file INPUT.DAT and OUTPUT.DAT. For running grep, the user must make changes to config.py according to the installation instructions given in SD document. 

This dataset is licensed by the rights-holder under a Creative Commons Attribution 4.0 International Licence: https://creativecommons.org/licenses/by/4.0/.

Host: University of Tartu, Estonia

Additional information
Kalev Rannat kalev.rannat@ut.ee
Hannes Keernik hannes.keernik@ut.ee

This work is funded by the ECMWF, Service contract No ECMWF/COPERNICUS/2025/C3S2_311_Bis_MU .
