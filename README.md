# Зеркало ГК на время набегов спамботов, ошибок 504 и т.п.

Тут: https://gcode.space/#!/

Для работы БД требуется установить расширение «pg_trgm»:
* `sudo -u postgres psql`
* `\c ngk`
* `CREATE EXTENSION pg_trgm;`
* `\q`