![](http://media.charlesleifer.com/blog/photos/sqlite-web.png)

`sqlite-web` is a web-based SQLite database browser written in Python.

Project dependencies:

* [flask](http://flask.pocoo.org)
* [peewee](http://docs.peewee-orm.com)
* [pygments](http://pygments.org)

### Installation

```sh
$ pip install sqlite-web
```

### Usage

```sh
$ sqlite_web /path/to/database.db
```

### Features

![](http://media.charlesleifer.com/blog/photos/p1494359468.71.gif)

* Works with your existing SQLite databases, or can be used to create new databases.
* Add or drop:
  * Tables
  * Columns (yes, you can drop and rename columns!)
  * Indexes
* Export data as JSON or CSV.
* Import JSON or CSV files.
* Browse table data.

### Screenshots

The index page shows some basic information about the database, including the number of tables and indexes, as well as its size on disk:

![](http://media.charlesleifer.com/blog/photos/s1415479324.32.png)

The `structure` tab displays information about the structure of the table, including columns, indexes, and foreign keys (if any exist). From this page you can also create, rename or drop columns and indexes.

![](http://media.charlesleifer.com/blog/photos/s1415479418.23.png)

The `content` tab displays all the table data. Links in the table header can be used to sort the data:

![](http://media.charlesleifer.com/blog/photos/s1415479502.61.png)

The `query` tab allows you to execute arbitrary SQL queries on a table. The query results are displayed in a table and can be exported to either JSON or CSV:

![](http://media.charlesleifer.com/blog/photos/s1415487149.3.png)

The `import` tab supports importing CSV and JSON files into a table. There is an option to automatically create columns for any unrecognized keys in the import file:

![](http://media.charlesleifer.com/blog/photos/s1415479625.44.png)

### Command-line options

The syntax for invoking sqlite-web is:

```console

$ sqlite_web [options] /path/to/database-file.db
```

The following options are available:

* ``-p``, ``--port``: default is 8080
* ``-H``, ``--host``: default is 127.0.0.1
* ``-d``, ``--debug``: default is false
* ``-x``, ``--no-browser``: do not open a web-browser when sqlite-web starts.
* ``-P``, ``--password``: prompt for password to access sqlite-web.

### Using docker

A Dockerfile is provided with sqlite-web. To use:

```console

$ cd docker/  # Change dirs to the dir containing Dockerfile
$ docker build -t coleifer/sqlite-web .
$ docker run -it --rm \
    -p 8080:8080 \
    -v /path/to/your-data:/data \
    -e SQLITE_DATABASE=db_filename.db \
    coleifer/sqlite-web
```
