#!/bin/bash
#test_python_with_par
# 


usage()
{
# usage
echo
echo "The script needs 3 obligatory integer parameters!"
echo "usage: `basename $0` run_grep.sh year from_doy to_doy " >&2
echo
exit 1
}

if [ $# -lt 3 ]; then 
  # no parameters passed
  usage
fi

cd /private/grep/
source /private/grep_venv/bin/activate

datestr=$(date +"%Y%m%d")

echo "$(date)"
echo Starting year $1 from $2 to $3


logfile="/my_path_to_nohup_output/nohup_out_${datestr}.log"
nohup python3 -c "from run.daily_routines import main; main($1, $2, $3)" > "$logfile" 2>&1 &

myPid=$!
echo "Started process PID $myPid (logging to $logfile)"

if kill -0 $myPid; then 
    wait
fi

echo $1 $2 $3
echo "FINISHED PID $myPid $(date)"








