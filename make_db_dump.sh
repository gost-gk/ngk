#!/bin/bash
set -eux

LOG_FILE="$(realpath db_dump.log)"
dump_name="ngk_$(date '+%Y%m%d_%H%M%S')"
echo "DB dump begin at $(date '+%Y-%m-%d %H:%M:%S'), dumping to $dump_name.gz..." >> $LOG_FILE

pushd db_dumps >> $LOG_FILE
pg_dump --no-comments -T user_settings -T auto_moderators -F c ngk | gzip -c > "$dump_name.gz"
# Remove the old dumps
ls -tp | grep -v '/$' | tail -n +2 | xargs -I {} rm -- {}
popd >> $LOG_FILE

echo "DB dump end at $(date '+%Y-%m-%d %H:%M:%S')." >> $LOG_FILE
echo "" >> $LOG_FILE
