#!/bin/bash
LOG_FILE="$(realpath db_dump.log)"
dump_name="ngk_$(date '+%Y%m%d_%H%M%S')"
echo "DB dump begin at $(date '+%Y-%m-%d %H:%M:%S'), dumping to $dump_name.zip..." >> $LOG_FILE

pushd db_dumps >/dev/null
pg_dump -F t ngk > "$dump_name.dump"
zip -q -6 "$dump_name.zip" "$dump_name.dump"
rm -f "$dump_name.dump"
# Remove the old dumps
ls -tp | grep -v '/$' | tail -n +2 | xargs -I {} rm -- {}
popd >/dev/null

echo "DB dump end at $(date '+%Y-%m-%d %H:%M:%S')." >> $LOG_FILE
echo "" >> $LOG_FILE
