#!/bin/bash

LOG_FILE="compress.log"
today_folder="$(date +%Y-%m-%d)/"
folders_count=0

echo "Compression started at $(date '+%Y-%m-%d %H:%M:%S')..." >> $LOG_FILE

pushd dumps >/dev/null
for d in */ ; do
    if [ $d != $today_folder ]; then
        tar -zcf "${d:0:-1}.tar.gz" $d
        rm -rf $d
        ((folders_count=folders_count+1))
    fi
done
popd >/dev/null

echo "Compression ended at $(date '+%Y-%m-%d %H:%M:%S'). $folders_count folders compressed." >> $LOG_FILE
echo "" >> $LOG_FILE