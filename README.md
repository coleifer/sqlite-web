![](http://media.charlesleifer.com/blog/photos/sqlite-browser.png)

`sqlite-browser` is a web-based SQLite database browser written in Python.

Project dependencies:

* [flask](http://flask.pocoo.org)
* [peewee](http://docs.peewee-orm.com)

Installation:

```sh
$ pip install sqlite-browser flask peewee
```

Usage:

```sh
$ sqlite_browser /path/to/database.db
```

Features:

* Works with your existing SQLite databases, or can be used to create new databases.
* Add or drop:
  * Tables
  * Columns (yes, you can drop columns!)
  * Indexes
* Export data as JSON or CSV.
* Import JSON or CSV files.
* Browse table data.
