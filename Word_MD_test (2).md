# C3S2_311_bis GREP 

**Introduction**

This document includes workflow explanations, expanded scientific background, and technical commentary on each component of the Python scripts used to retrieve and process the GNSS observational data and metadata stored in the Global RINEX Data Repository (GREP). GREP is a repository of RINEX observations merging global, regional and national data repositories, (most of them are open-access repositories).

The processing workflow performs:

* Data and metadata download and extraction
* Generating standard long RINEX filenames
* Removing/out-filtering duplicated sites from the processing queue (redundant sites)
* Quality check of the data (site coordinates, comparing RINEX headers with site logfiles)
* Storing the data not passed QC into dedicated folders (without changes/corrections made)
* Compiling the tables of QC-results and processing history
* Writing the results to GREP by YYYY/DOY, updating the metadata and processing history tables

Initial data for GREP (GNSS observational data and metadata) is downloaded from remote repositories, each having its own data access rules and technical requirements. The process is fully automated but needs supervision and maintenance in case of long internet connection time-outs or any unexpected processing errors detected.

**Software archival location**

Provide a link and access details for the archive of the software used including the README file. This should be on Github or similar public-access code repository.

Include as a figure a screencap of the start of the file listing of the software instance being described.

Include as a figure a screencap of the README file first few lines.

Default is an open-access repository. If username or password are required to access, provide contact details as to how to request access.

If the software license is not explicitly indicated within the software repository, then this license must be indicated here.

The GREP repository can be found at URL: <https://github.com/krannat/C3S2_311_bis_GREP> .

GREP (modular) Structure:

Scripts:

/grep/

├── compare comparing RINEX headers with logfiles

├── dbio internal data management

├── download download from different remote repositories

├── log logging support

├── process remote-specific data processing

├── run the main run script

└── t\_box supporting scripts for monitoring and maintenance

Data and processing outputs:

grep\_data

├── brdc daily ephemeris files

├── df\_backups dataframe backups

├── logfiles sites’ logfiles

├── logfiles\_err

├── logging operative daily logfiles

├── pickles dataframes

├── RINEX QC-passed RINEXes by Year (YYYY) and Day of the Year (DOY)

│   └── YYYY

│   └── DOY

├── RINEX\_err QC NOT passed RINEXes by Year (YYYY) and Day of the Year (DOY)

│   └── YYYY

│   └── DOY

├── RINEX\_v1 RINEX v1

│   └── YYYY

│   └── DOY

├── stns stations’ table

├── tmp temporary processing info

└── unavco\_tokens EartScope Tokens

3rd parties’ software (licences described in DL-deliverable):

Installed under ~/Tools:

Anubis-3.9, gfzrnx\_2.2.0\_lx64, interp\_1min (together with the EGM2008 grid-file).

License: CC-BY-4.0

**2.1 Technical specifications**

Programming Language:

* Python 3.x

Package Management / Environment:

The following pre-installed packages (as given in requirements.txt) must be installed into the virtual environment of GREP.

Supported Operating Systems:

* Linux (tested on Debian, Fedora 35, Rocky 9.3)

System Requirements:

* CPU: Multi-core processor for parallel processing
* RAM: 32 GB recommended
* Storage: Tens of TBytes (and growing)
* Network: High-speed Internet connection for parallel data download

Notes:

* All processing is done at ECMWF Virtual Machine
* Some remote repositories (data providers) require FTP

**Installation instructions**

In general, the installation process consists of 5 steps and user-specific configuration described below.

1st step – clone GREP scripts from git into your working directory.

2nd step – create the required directory tree into your local file system

3rd step – modify config.py according to your local file system

4th step – install all required Python packages (based on requirements.txt) and stn\_table (under grep\_data/stns/)

5th step – ask/get personal access (ssh-keys, access tokens) to all remote GNSS data repositories

Configuration of GREP in any local file system starts with configuring the paths:

BASE\_PATH = directory to where\_to\_install\_grep'

'/home/grep\_user/’ -- directory for installing 3rd parties’ software

and,

getting personal credentials for accessing EarthData and EarthScope and Greenland remote servers.

These missing parameters must be written into the GREP configuration file config.py:

BASE\_PATH = 'where\_to\_install\_grep'

anubis\_executable = '/home/grep\_user/Tools/anubis-3.9-lin-static-64b'

rx3name\_executable = '/home/grep\_user/Tools/RX3name'

rin1to2\_executable = '/home/grep\_user/Tools/gfzrnx\_2.2.0\_lx64'

greenland\_username = 'grep\_user'

greenland\_password = 'grep\_user\_pwd'

chile\_rinex\_temp\_down\_path = 'free choice' # tests and bulk download from CSN (Chile)

Installing stations’ table:

It is highly recommended to pre-install the rather long stn\_table into /grep/stns/ before starting to run the script on any network/repository. Starting from an empty stations list may trigger massive 429 Errors from Nominatim (too many requests in a short period of time), which can ultimately result in sites being excluded from routine data processing. When adding a new network, it is advisable to carefully check for Nominatim-related errors during the processing of the first day. If necessary, rerun the first day several times until all stations have been successfully resolved and added. This procedure is safe, as duplicate entries are not created since no data is processed twice.

Installing 3rd party software (in /Tools):

Anubis: download the free version of executable from <https://gnutsoftware.com/software/anubis/download>

gfzrnx\_2.2.0\_lx64: download the executable from <https://gnss.gfz.de/products/gfzrnx/downloads>

Nominatim: must have GeoPy installed (pip install geopy). geopy is a Python client for geocoding web service Nominatim. The use policy: <https://operations.osmfoundation.org/policies/nominatim/>

The interp\_1min for EGM2008: executable must be compiled from source interp\_1min.f into /EGM2008\_WGS84 (the grid-file must be decompressed and installed to the same directory). Just copying executable from one file system to the next may not work. After compilation run a test by comparing the sample file INPUT.DAT and OUTPUT.DAT (given in GitHub).

Staying in /EGM2008\_WGS84 run a test in command line:

./interp1\_min INPUT.DAT

The output is a csv-file (OUTPUT.DAT), each line containing the same coordinates, but the 3rd item is the interpolated amsl-height. The line numbers must conform with the line numbers in INPUT.DAT.

EarthScope access:

EarthScope uses Bearer access tokens for authentication to access GNSS data and NSF National Geophysical Facility (NGF) services. The instructions can be found at <https://www.earthscope.org/data/authentication/> and for the programmatic access the user must install the EarthScope SDK <https://gitlab.com/earthscope/public/earthscope-sdk/> .

EarthData access:

As a 1st step, create a personal EarthData login account:

<https://urs.earthdata.nasa.gov/oauth/authorize?client_id=gDQnv1IO0j9O2xXdwS8KMQ&response_type=code&redirect_uri=https%3A%2F%2Fcddis.nasa.gov%2Fproxyauth&state=aHR0cDovL2NkZGlzLm5hc2EuZ292L2FyY2hpdmU>

The 2nd step – create the .netrc file into your /home directory

<https://www.earthdata.nasa.gov/centers/cddis-daac/archive-access> with brief instructions under Python3 examples for a .netrc file set up:

* To create a .netrc file, you will need to create a text file with the name .netrc; this file needs to have read permissions set to only yourself, so that no one can read your file and get your username and password. The format of the file is:
* machine urs.earthdata.nasa.gov login <username> password <password>
* where <username> and <password> are the values you set when you created your Earthdata login account.

Greenland:

For getting access to the data (registering user and password), contact GNET PI at <https://go-gnet.org/contact>

Settings in local file system (for accessing remote servers):

.ssh, .netrc (for EarthData/CDDIS)

The *known\_hosts* file must include IP address for Geoscience Australia and .ssh the keys for any other service providers that require identification for resource access. We cannot guarantee that intervention by the local sysadmin can be avoided.

**Usage instructions**

GREP can be run in different modes (for different use cases):

1. Processing yearly data from all sources/networks simultaneously (max 1 year per session)
2. Processing data on a network basis (must edit the site list in config.py). The list of networks consists of the network names and is expandable. The list can contain also just one item, if trying to process data from one network only (for example, ‘epn’).
3. Adding data missing from earlier processing (filling the data processing gaps)

The internal data tables and stations’ list will be updated automatically. However, adding completely a new data source requires writing additional source-specific functions/modules according to the technical requirements of the new network, and integration to the GREP package.

Preparing to run grep-script:

Create Python virtual environment (ref. <https://docs.python.org/3/library/venv.html>) into path\_to\_grep.

python3 -m venv /path\_to\_grep/

Copy run\_grep.sh into your working directory, and make changes to the lines:

cd /path\_to\_grep/grep/

source /path\_to\_grep/grep\_venv/bin/activate

logfile="/my\_path\_to\_nohup\_output/nohup\_out\_${datestr}.log",

where the “my\_path\_to\_nohup\_output” according to user’s own preferences. After making the changes, the script must be made executable.

It is suggested to run the long-lasting processes with nohup. The nohup command allows processes in local Linux system to keep running after the terminal closes. Additional benefit can be seen in a possibility to inspect the process running and to analyse the last tasks performed in case in script malfunction or unexpected termination.

A shell-script run\_grep.sh takes care about activation of the Python virtual environment and using Nohup.

Starting the data processing:

Copy run\_grep.sh into your working directory and run it in command line:

grep.sh year from\_doy to\_doy

where the 4-digit year denotes the year, and from\_doy and to\_doy denote the starting day of the year and the ending day of the year chosen for data processing.

Ideally, once the script is initiated, the GREP repository should autonomously expand without requiring external intervention. However, the application's functionality relies on an external online service (Nominatim) and the accessibility of various data provider servers. If any of these services experience prolonged downtime, the script cannot proceed, and the issues must be resolved.

The first step in verifying that the processing is running successfully is to inspect the daily.log and daily\_errors.log files in the logging/ directory (see also a section for testing below). These files provide detailed information about the processing workflow and any errors encountered. A log-rotation function is available that renames these files to .1, .2, etc., while retaining up to 40 backup copies. The rotated log files are also stored in the corresponding daily RINEX directory (RINEX/YYYY/DOY).

In practice, data providers' repositories showed great heterogeneity (different data formats, compression rules, file naming conventions, data transfer protocols, security rules, etc.). Every new network may require the system administrator to implement some changes. For any changes like this, the GREP processing must be stopped. This also implies that the GREP will be regularly monitored and maintained over the long term. Operators of the GREP shall be aware of changes planned and made by data providers, for implementing changes to the code, if necessary.

**Known limitations**:

Technical restrictions for Nominatim (max number of requests per day and per time unit <https://operations.osmfoundation.org/policies/nominatim/> ).

Internet connection time-out – the script will not stay waiting, it will stop after a limited number of trials to reconnect.

The workflow gets broken by unknown exception. This is option is intentionally left for safety – the situation must be handled by a skilled person. The working scripts may need some updates and the GREP data repository may need maintenance before restart. These issues may arise due to changes (modified structure of the remote repository or changes in data transmission protocols) made in any of the remote servers.

In one session the GREP can process maximum one year of data.

Data download from NCN and Geoscience Australia relies on Amazon AWS

**Testing**

The following commands can be used to process a single day of data from the CACS network. This provides a compact example of how the stn\_table, pickle files, as well as RINEX and logfile directories evolve during processing, how to check comparing.txt contents, and how to verify GREP processing logfiles for potential ERROR messages.

1. Set two shortcuts (B = data folder, T = folder for the test notes):

B=/path/to/data/folder; T/path/to/test/notes; mkdir -p $T; cd /path/to/grep/scripts

2. To show the test configuration:

grep -n "^network\_list\|^BASE\_PATH\|^pkl\_path" config.py

![](data:image/png;base64...)

3. Save a timestamp and a copy of the station table:

touch $T/start\_marker; cp $B/stns/stn\_table.csv $T/stn\_table\_before.csv

4. Count what exists now and save it to before.txt

{ echo "stn\_table rows: $(($(wc -l < $B/stns/stn\_table.csv)-1))"; echo "logfiles: $(ls $B/logfiles | wc -l)"; echo "RINEX/2025/001: $(ls $B/RINEX/2025/001/\* 2>/dev/null | wc -l)"; } | tee $T/before.txt

![](data:image/png;base64...)

5. Run the test for 2025, doy of year 001:

grep.sh 2025 1 1

6. After the run use the same count command as Step 4, but it saves to after.txt:

{ echo "stn\_table rows: $(($(wc -l < $B/stns/stn\_table.csv)-1))"; echo "logfiles: $(ls $B/logfiles | wc -l)"; echo "RINEX/2025/001: $(ls $B/RINEX/2025/001/\* 2>/dev/null | wc -l)"; } | tee $T/after.txt

7. Show before and after side by side

diff -y $T/before.txt $T/after.txt

![](data:image/png;base64...)

8. Rows added or changed in stn\_table.csv:

diff $T/stn\_table\_before.csv $B/stns/stn\_table.csv | grep '^[<>]'

9. Stations that needed a Nominatim query:

grep -h "Making a Nominatim query" $B/RINEX/2025/001/daily.log

10. Number of new logfiles:

find $B/logfiles -type f -newer $T/start\_marker | wc -l

11. The first 5 of new logfiles:

find $B/logfiles -type f -newer $T/start\_marker | head -5

![](data:image/png;base64...)

12. Check if some RINEX files were rejected (if yes then inspect daily\_errors.log):

ls $B/RINEX\_err/2025/001 2>/dev/null || echo "No RINEX\_err/2025/001 folder -> no RINEX files rejected"

![](data:image/png;base64...)

13. Check the content of the dataframe (output table), rows per day (YYYYDOY):

cut -d, -f2 $B/df\_backups/2025/2025\_01.csv | tail -n +2 | cut -c13-19 | sort | uniq -c

![](data:image/png;base64...)

14. A sample of the content (site, RINEX file, matched logfile):

grep 2025001 $B/df\_backups/2025/2025\_01.csv | head -10 | cut -d, -f1,2,6

![](data:image/png;base64...)

15. Number of sites per error code (0 = consistent):

grep -E '\.(crx|rnx)' $B/RINEX/2025/001/comparing\_log\_rinex\_2025\_001.txt | awk -F'|' '{print ($4==""?"no logfile":$4)}' | sort | uniq -c | sort -rn

![](data:image/png;base64...)

16. Check the processing logs for error messages. Number of messages per type for DOY 001:

awk '{print $3}' $B/RINEX/2025/001/daily\_errors.log | sort | uniq -c

![](data:image/png;base64...)

**Verification**

To ensure, that everything is installed and works appropriately, it is suggested to contact the developers for running a test-set of networks and a fixed number of consecutive days on a platform independent of a new user. The results and logfiles can be compared after the test-run.
