#!/usr/bin/env python

__version__ = '0.8.0'

import base64
import datetime
import decimal
import hashlib
import importlib
import logging
import math
import operator
import optparse
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from collections import namedtuple, OrderedDict
from functools import reduce
from functools import wraps
from getpass import getpass
from io import StringIO
from io import TextIOWrapper
from logging.handlers import WatchedFileHandler
from werkzeug.routing import BaseConverter, ValidationError
from werkzeug.utils import secure_filename
from werkzeug.wsgi import ClosingIterator


try:
    from flask import (
        Flask, abort, flash, g, jsonify, make_response, redirect,
        render_template, request, Response, session, url_for)
except ImportError:
    raise RuntimeError('Unable to import flask module. Install by running '
                       'pip install flask')
try:
    from markupsafe import Markup, escape
except ImportError:
    raise RuntimeError('Unable to import markupsafe module. Install by running'
                       ' pip install markupsafe')

try:
    from pygments import formatters, highlight, lexers
except ImportError:
    import warnings
    warnings.warn('pygments library not found.', ImportWarning)
    syntax_highlight = lambda data: '<pre>%s</pre>' % escape(data)
else:
    def syntax_highlight(data):
        if not data:
            return ''
        lexer = lexers.get_lexer_by_name('sql')
        formatter = formatters.HtmlFormatter(linenos=False)
        return highlight(data, lexer, formatter)

try:
    from peewee import __version__ as _pw_version
    peewee_version = tuple([int(p) for p in _pw_version.split('.')])
except ImportError:
    raise RuntimeError('Unable to import peewee module. Install by running '
                       'pip install peewee')
else:
    if peewee_version < (3, 0, 0):
        raise RuntimeError('Peewee >= 3.0.0 is required. Found version %s. '
                           'Please update by running pip install --update '
                           'peewee' % _pw_version)

from peewee import *
from peewee import IndexMetadata
from peewee import sqlite3
from playhouse.dataset import DataSet
from playhouse.migrate import migrate

try:
    from sqlite_web.executor import (
        Result, is_read, key_decode, key_encode, run_one, run_script,
        split_statements)
except ImportError:
    from executor import (
        Result, is_read, key_decode, key_encode, run_one, run_script,
        split_statements)


CUR_DIR = os.path.realpath(os.path.dirname(__file__))
DEBUG = False

BLOB_AS_BASE64 = False  # Default is hex.
ROWS_PER_PAGE = 50
QUERY_ROWS_PER_PAGE = 1000
TRUNCATE_VALUES = True
SECRET_KEY = 'sqlite-database-browser-0.1.0'

app = Flask(
    __name__,
    static_folder=os.path.join(CUR_DIR, 'static'),
    template_folder=os.path.join(CUR_DIR, 'templates'))
app.config.from_object(__name__)
datasets = {}
dataset_config = {}

#
# Database metadata objects.
#

TriggerMetadata = namedtuple('TriggerMetadata', ('name', 'sql'))

ViewMetadata = namedtuple('ViewMetadata', ('name', 'sql'))

#
# Database helpers.
#

class SqliteDataSet(DataSet):
    _schema_version = None

    def ensure_cache(self):
        version = self._database.pragma('schema_version')
        if version != self._schema_version:
            self._schema_version = version
            self._memos = {}
            self.update_cache()

    def _cached(self, key, fn):
        self.ensure_cache()
        if key not in self._memos:
            self._memos[key] = fn()
        return self._memos[key]

    def cached_tables(self):
        return self._cached('tables', lambda: self.tables)

    def cached_virtual_tables(self):
        return self._cached('virtual_tables', self.get_virtual_tables)

    def cached_corollary_virtual_tables(self):
        return self._cached('corollary_virtual_tables',
                            self.get_corollary_virtual_tables)

    def cached_is_view(self, name):
        return self._cached(('is_view', name), lambda: self.is_view(name))

    def cached_view_operations(self, name):
        return self._cached(('view_operations', name),
                            lambda: self.view_operations(name))

    def cached_table_sql(self, table):
        return self._cached(('table_sql', table),
                            lambda: self.get_table_sql(table))

    def cached_foreign_keys(self, table):
        return self._cached(('foreign_keys', table),
                            lambda: self.get_foreign_keys(table))

    @property
    def filename(self):
        db_file = self._database.database
        if db_file.startswith('file:'):
            db_file = db_file[5:]
        return os.path.realpath(db_file.rsplit('?', 1)[0])

    @property
    def basename(self):
        return os.path.basename(self.filename)

    @property
    def is_readonly(self):
        db_file = self._database.database
        return db_file.endswith('?mode=ro')

    @property
    def created(self):
        stat = os.stat(self.filename)
        return datetime.datetime.fromtimestamp(stat.st_ctime)

    @property
    def modified(self):
        stat = os.stat(self.filename)
        return datetime.datetime.fromtimestamp(stat.st_mtime)

    @property
    def size_on_disk(self):
        stat = os.stat(self.filename)
        return stat.st_size

    def get_indexes(self, table):
        return self._database.get_indexes(table)

    def get_all_indexes(self):
        cursor = self.query(
            'SELECT name, sql FROM sqlite_master '
            'WHERE type = ? ORDER BY name',
            ('index',))
        return [IndexMetadata(row[0], row[1], None, None, None)
                for row in cursor.fetchall()]

    def get_columns(self, table):
        return self._database.get_columns(table)

    def get_foreign_keys(self, table):
        return self._database.get_foreign_keys(table)

    def get_triggers(self, table):
        cursor = self.query(
            'SELECT name, sql FROM sqlite_master '
            'WHERE type = ? AND tbl_name = ?',
            ('trigger', table))
        return [TriggerMetadata(*row) for row in cursor.fetchall()]

    def get_all_triggers(self):
        cursor = self.query(
            'SELECT name, sql FROM sqlite_master '
            'WHERE type = ? ORDER BY name',
            ('trigger',))
        return [TriggerMetadata(*row) for row in cursor.fetchall()]

    def get_table_sql(self, table):
        if not table:
            return

        cursor = self.query(
            'SELECT sql FROM sqlite_master '
            'WHERE tbl_name = ? AND type IN (?, ?)',
            [table, 'table', 'view'])
        res = cursor.fetchone()
        if res is not None:
            return res[0]

    def get_view(self, name):
        cursor = self.query(
            'SELECT name, sql FROM sqlite_master '
            'WHERE type = ? AND name = ?', ('view', name))
        res = cursor.fetchone()
        if res is not None:
            return ViewMetadata(*res)

    def get_all_views(self):
        cursor = self.query(
            'SELECT name, sql FROM sqlite_master '
            'WHERE type = ? ORDER BY name',
            ('view',))
        return [ViewMetadata(*row) for row in cursor.fetchall()]

    def get_virtual_tables(self):
        cursor = self.query(
            'SELECT name FROM sqlite_master '
            'WHERE type = ? AND sql LIKE ? '
            'ORDER BY name',
            ('table', 'CREATE VIRTUAL TABLE%'))
        return set([row[0] for row in cursor.fetchall()])

    def get_corollary_virtual_tables(self):
        virtual_tables = self.get_virtual_tables()
        suffixes = ['content', 'docsize', 'segdir', 'segments', 'stat']
        return set(
            '%s_%s' % (virtual_table, suffix) for suffix in suffixes
            for virtual_table in virtual_tables)

    def is_view(self, name):
        cursor = self.query(
            'SELECT name FROM sqlite_master '
            'WHERE type = ? AND name = ?', ('view', name))
        return cursor.fetchone() is not None

    def view_operations(self, name):
        cursor = self.query(
            'SELECT sql FROM sqlite_master WHERE type=? AND tbl_name=?',
            ('trigger', name))
        triggers = [t for t, in cursor.fetchall()]
        rgx = re.compile(r'CREATE\s+TRIGGER.+?\sINSTEAD\s+OF\s+'
                         r'(INSERT|UPDATE|DELETE)\s', re.I)
        operations = set()
        for trigger in triggers:
            operations.update([op.lower() for op in rgx.findall(trigger)])

        return operations

class Base64Converter(BaseConverter):
    # The URL segment is a rowkey token (see executor.key_encode). It is
    # already URL-safe, so it passes through unchanged. Malformed tokens
    # fail to decode and 404.
    def to_python(self, value):
        try:
            values = key_decode(value)
        except Exception:
            raise ValidationError('invalid row key')
        if not values:
            # A token holding no values (e.g. crafted "[]") would otherwise
            # blow up in decode_pk.
            raise ValidationError('empty row key')
        return value

    def to_url(self, value):
        return value

app.url_map.converters['b64'] = Base64Converter

def get_dataset():
    if not hasattr(g, 'dataset'):
        dataset_key = session.get('dataset')
        if dataset_key is None or dataset_key not in datasets:
            dataset_key = list(datasets)[0]
            session['dataset'] = dataset_key
        g.dataset = datasets[dataset_key]
    return g.dataset

def quote_ident(name):
    return '"%s"' % name.replace('"', '""')

def quote_value(value):
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "X'%s'" % bytes(value).hex()
    return "'%s'" % str(value).replace("'", "''")

def _bulk_delete_values(tokens):
    # Bulk delete is single-column-pk only, so each token holds one value.
    values = []
    for token in tokens:
        try:
            values.append(key_decode(token)[0])
        except Exception:
            continue
    return values

#
# Flask views.
#

@app.route('/')
def index():
    return render_template('index.html', sqlite=sqlite3)

@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == app.config['PASSWORD']:
            session['authorized'] = True
            return redirect(session.get('next_url') or url_for('index'))
        flash('The password you entered is incorrect.', 'danger')
        app.logger.debug('Received incorrect password attempt from %s' %
                         request.remote_addr)
    return render_template('login.html')

@app.route('/logout/', methods=['GET'])
def logout():
    session.pop('authorized', None)
    return redirect(url_for('login'))

@app.route('/select-dataset/', methods=['GET'])
def select_dataset():
    dataset = request.args.get('name')
    if dataset and dataset in datasets:
        session['dataset'] = dataset
    else:
        flash('Unable to load selected database.', 'danger')
    return redirect(url_for('index'))

@app.route('/load/', methods=['GET', 'POST'])
def load():
    enable_load = app.config.get('ENABLE_LOAD')
    enable_filesystem = app.config.get('ENABLE_FILESYSTEM')
    if not (enable_load or enable_filesystem):
        flash('Loading databases at run-time is not supported.', 'warning')
        return redirect(url_for('index'))

    dataset = None
    filename = None
    error = None
    if request.method == 'POST':
        filename = request.form.get('filename')
        try:
            dataset, error = _add_dataset(enable_load, enable_filesystem)
        except ValueError as exc:
            error = str(exc)

        if dataset and not error:
            flash('Successfully loaded database.', 'success')
            return redirect(url_for('index'))

    return render_template(
        'load.html',
        filename=filename,
        error=error)

def _add_dataset(enable_load, enable_filesystem):
    mode = request.form.get('mode')
    if mode == 'upload':
        if not enable_load:
            return None, 'Uploading databases is not allowed.'

        database = request.files.get('database')
        if not database:
            return None, 'Database file is required.'

        if app.config['DB_UPLOAD_DIR']:
            dirname = app.config['DB_UPLOAD_DIR']
            os.makedirs(dirname, exist_ok=True)
        else:
            dirname = tempfile.mkdtemp(prefix='sqlite-web')
        filename = secure_filename(database.filename) or 'database.db'
        path = os.path.join(dirname, filename)
        database.save(path)
    elif mode == 'filesystem':
        if not enable_filesystem:
            return None, 'Loading databases from the filesystem is not allowed.'
        path = request.form.get('filename')
        if not path:
            return None, 'Filename is required.'
        if not os.path.exists(path):
            return None, 'File "%s" not found.' % path
    else:
        return None, 'Error: unrecognized mode "%s".' % mode

    try:
        dataset = initialize_dataset(path)
    except Exception as exc:
        return None, 'Unable to load database: %s' % exc
    else:
        basename = os.path.basename(path)
        datasets[basename] = dataset
        session['dataset'] = basename

    return dataset, None

@app.route('/unload/', methods=['GET', 'POST'])
def unload():
    enable_load = app.config.get('ENABLE_LOAD')
    enable_filesystem = app.config.get('ENABLE_FILESYSTEM')
    if not (enable_load or enable_filesystem):
        flash('Unloading databases is not supported.', 'danger')
        return redirect(url_for('index'))
    if len(datasets) == 1:
        flash('Cannot unload dataset.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        dataset = request.form.get('dataset')
        if not dataset or dataset not in datasets:
            flash('Database not found.', 'warning')
            return redirect(url_for('unload'))

        ds = datasets.pop(dataset)
        ds.close()

        current = session.get('dataset')
        if current == dataset:
            session['dataset'] = list(datasets)[0]
        flash('Database "%s" unloaded successfully.' % dataset, 'success')
        return redirect(url_for('index'))
    else:
        dataset = request.args.get('dataset')

    return render_template('unload.html', selected=dataset)

def _query_view(template, table=None):
    dataset = get_dataset()
    sql = request.values.get('sql') or ''

    export_format = None
    explain = False
    if request.method == 'POST':
        if 'export_json' in request.form:
            export_format = 'json'
        elif 'export_csv' in request.form:
            export_format = 'csv'
        elif 'explain' in request.form:
            explain = True

    ordering_key = 'export_ordering' if export_format else 'ordering'
    try:
        ordering = int(request.values.get(ordering_key) or 0) or None
    except ValueError:
        ordering = None

    page = request.values.get('page') or ''
    page = max(int(page), 1) if page.isdigit() else 1

    if table:
        default_sql = 'SELECT * FROM %s' % quote_ident(table)
        model_class = dataset[table].model_class
        pk = model_class._meta.primary_key
        is_composite_pk = isinstance(pk, CompositeKey)
        allow_detail = pk is not False and not dataset.cached_is_view(table)
        allow_edit = allow_detail and not dataset.is_readonly
        allow_bulk = allow_edit and not is_composite_pk
        fk_lookup = {fk.column: (fk.dest_table, fk.dest_column)
                     for fk in dataset.cached_foreign_keys(table)}
    else:
        default_sql = ''
        model_class = dataset._base_model
        pk = None
        is_composite_pk = False
        allow_detail = allow_edit = allow_bulk = False
        fk_lookup = {}

    if request.method == 'POST' and request.form.get('action') == 'bulk-delete':
        values = _bulk_delete_values(request.form.getlist('pk'))
        if not allow_bulk:
            flash('Cannot perform bulk operation on this table.', 'warning')
        elif not values:
            flash('No rows were selected.', 'warning')
        else:
            try:
                n = (model_class.delete()
                     .where(model_class._meta.primary_key.in_(values))
                     .execute())
            except Exception as exc:
                flash('Error performing bulk delete: %s' % exc, 'danger')
                app.logger.exception('Error performing bulk delete.')
            else:
                flash('Successfully deleted %s row(s)' % n, 'success')

    statements = split_statements(sql) if sql.strip() else []
    single_read = len(statements) == 1 and is_read(dataset, sql)
    # The bulk form re-submits the sql, so only offer it for reads.
    allow_bulk = allow_bulk and single_read

    if export_format and statements:
        if not single_read:
            flash('Only a single query may be exported.', 'warning')
        else:
            qsql = sql.rstrip('; \t\r\n')
            if ordering:
                qsql = ('SELECT * FROM (\n%s\n) AS _ ORDER BY %d %s' %
                        (qsql, abs(ordering),
                         'DESC' if ordering < 0 else 'ASC'))
            return export(model_class.raw(qsql).dicts(), export_format, table)

    result = results = total = total_pages = None
    rpp = app.config['QUERY_ROWS_PER_PAGE']
    if statements and export_format is None:
        if request.method == 'GET' and not single_read:
            # Writes and scripts only execute via POST.
            flash('Press Execute to run this statement.', 'info')
        elif explain and len(statements) > 1:
            flash('Only a single statement may be explained.', 'warning')
        elif len(statements) == 1:
            # EXPLAIN QUERY PLAN compiles the statement without running it.
            run_sql = 'EXPLAIN QUERY PLAN %s' % sql if explain else sql
            result = run_one(dataset, run_sql, page=page, page_size=rpp,
                             ordering=ordering)
        else:
            results = run_script(dataset, statements, page_size=rpp)

    if (result is not None and result.kind == 'rows' and allow_detail and
            not explain and not is_composite_pk and
            pk.column_name in result.columns):
        pk_index = result.columns.index(pk.column_name)  # First one wins.
        result.keys = [key_encode([row[pk_index]]) for row in result.rows]

    if result is not None and result.kind == 'rows' and \
       'count' in request.values:
        try:
            total, = dataset.query('SELECT COUNT(*) FROM (\n%s\n) AS _' %
                                   sql.rstrip('; \t\r\n')).fetchone()
            total_pages = max(1, int(math.ceil(total / float(rpp))))
        except Exception:
            total = total_pages = None

    error = None
    if result is not None and result.kind == 'error':
        error = result.error

    return render_template(
        template,
        allow_bulk=allow_bulk,
        allow_detail=allow_detail,
        allow_edit=allow_edit,
        default_sql=default_sql,
        error=error,
        fk_lookup=fk_lookup,
        ordering=ordering,
        page=page,
        page_start=(page - 1) * rpp + 1,
        paginate=single_read and not explain,
        query_images=get_query_images(),
        result=result,
        results=results,
        sql=sql,
        table=table,
        table_sql=dataset.cached_table_sql(table),
        total=total,
        total_pages=total_pages,
        total_statements=len(statements))

@app.route('/query/', methods=['GET', 'POST'])
def generic_query():
    return _query_view('query.html')

def require_table(fn):
    @wraps(fn)
    def inner(table, *args, **kwargs):
        if table not in get_dataset().cached_tables():
            abort(404)
        return fn(table, *args, **kwargs)
    return inner

@app.route('/create-table/', methods=['POST'])
def table_create():
    table = (request.form.get('table_name') or '').strip()
    if not table:
        flash('Table name is required.', 'danger')
        dest = request.form.get('redirect') or url_for('index')
        dest = '/' + dest.lstrip('/')  # idiot vulnerability "researchers".
        return redirect(dest)

    try:
        get_dataset()[table]
    except Exception as exc:
        flash('Error: %s' % str(exc), 'danger')
        app.logger.exception('Error attempting to create table.')
    return redirect(url_for('table_import', table=table))

@app.route('/<table>/')
@require_table
def table_structure(table):
    dataset = get_dataset()
    ds_table = dataset[table]
    model_class = ds_table.model_class

    return render_template(
        'table_structure.html',
        columns=dataset.get_columns(table),
        ds_table=ds_table,
        foreign_keys=dataset.get_foreign_keys(table),
        indexes=dataset.get_indexes(table),
        model_class=model_class,
        table=table,
        table_sql=dataset.cached_table_sql(table),
        triggers=dataset.get_triggers(table))

def get_request_data():
    if request.method == 'POST':
        return request.form
    return request.args

@app.route('/<table>/add-column/', methods=['GET', 'POST'])
@require_table
def add_column(table):
    dataset = get_dataset()

    class JsonField(TextField):
        field_type = 'JSON'
    column_mapping = OrderedDict((
        ('TEXT', TextField),
        ('INTEGER', IntegerField),
        ('REAL', FloatField),
        ('BLOB', BlobField),
        ('JSON', JsonField),
        ('BOOL', BooleanField),
        ('DATETIME', DateTimeField),
        ('DATE', DateField),
        ('DECIMAL', DecimalField),
        ('TIME', TimeField),
        ('VARCHAR', CharField)))

    request_data = get_request_data()
    col_type = request_data.get('type')
    name = request_data.get('name', '')

    if request.method == 'POST':
        name = re.sub(r'[^\w]+', '_', name.strip())
        if name and col_type in column_mapping:
            try:
                migrate(
                    dataset._migrator.add_column(
                        table,
                        name,
                        column_mapping[col_type](null=True)))
            except Exception as exc:
                flash('Error attempting to add column "%s": %s' % (name, exc),
                      'danger')
                app.logger.exception('Error attempting to add column.')
            else:
                flash('Column "%s" was added successfully!' % name, 'success')
                dataset.update_cache(table)
                return redirect(url_for('table_structure', table=table))
        else:
            flash('Name and column type are required.', 'danger')

    return render_template(
        'add_column.html',
        col_type=col_type,
        column_mapping=column_mapping,
        name=name,
        table=table,
        table_sql=dataset.cached_table_sql(table))

@app.route('/<table>/drop-column/', methods=['GET', 'POST'])
@require_table
def drop_column(table):
    dataset = get_dataset()
    request_data = get_request_data()
    name = request_data.get('name', '')
    columns = dataset.get_columns(table)
    column_names = [column.name for column in columns]

    if request.method == 'POST':
        if name in column_names:
            try:
                migrate(dataset._migrator.drop_column(table, name))
            except Exception as exc:
                flash('Error attempting to drop column "%s": %s' % (name, exc),
                      'danger')
                app.logger.exception('Error attempting to drop column.')
            else:
                flash('Column "%s" was dropped successfully!' % name, 'success')
                dataset.update_cache(table)
                return redirect(url_for('table_structure', table=table))
        else:
            flash('Name is required.', 'danger')

    return render_template(
        'drop_column.html',
        columns=columns,
        column_names=column_names,
        name=name,
        table=table)

@app.route('/<table>/rename-column/', methods=['GET', 'POST'])
@require_table
def rename_column(table):
    dataset = get_dataset()
    request_data = get_request_data()
    rename = request_data.get('rename', '')
    rename_to = request_data.get('rename_to', '')

    columns = dataset.get_columns(table)
    column_names = [column.name for column in columns]

    if request.method == 'POST':
        rename_to = re.sub(r'[^\w]+', '_', rename_to.strip())
        if (rename in column_names) and (rename_to not in column_names):
            try:
                migrate(dataset._migrator.rename_column(table, rename, rename_to))
            except Exception as exc:
                flash('Error attempting to rename column "%s": %s' %
                      (rename, exc), 'danger')
                app.logger.exception('Error attempting to rename column.')
            else:
                flash('Column "%s" was renamed successfully!' % rename, 'success')
                dataset.update_cache(table)
                return redirect(url_for('table_structure', table=table))
        else:
            flash('Column name is required and cannot conflict with an '
                  'existing column\'s name.', 'danger')

    return render_template(
        'rename_column.html',
        columns=columns,
        column_names=column_names,
        rename=rename,
        rename_to=rename_to,
        table=table)

@app.route('/<table>/add-index/', methods=['GET', 'POST'])
@require_table
def add_index(table):
    dataset = get_dataset()
    request_data = get_request_data()
    indexed_columns = request_data.getlist('indexed_columns')
    unique = bool(request_data.get('unique'))

    columns = dataset.get_columns(table)

    if request.method == 'POST':
        if indexed_columns:
            try:
                migrate(
                    dataset._migrator.add_index(
                        table,
                        indexed_columns,
                        unique))
            except Exception as exc:
                flash('Error attempting to create index: %s' % exc, 'danger')
                app.logger.exception('Error attempting to create index.')
            else:
                flash('Index created successfully.', 'success')
                return redirect(url_for('table_structure', table=table))
        else:
            flash('One or more columns must be selected.', 'danger')

    return render_template(
        'add_index.html',
        columns=columns,
        indexed_columns=indexed_columns,
        table=table,
        unique=unique)

@app.route('/<table>/drop-index/', methods=['GET', 'POST'])
@require_table
def drop_index(table):
    dataset = get_dataset()
    request_data = get_request_data()
    name = request_data.get('name', '')
    indexes = dataset.get_indexes(table)
    index_names = [index.name for index in indexes]

    if request.method == 'POST':
        if name in index_names:
            try:
                migrate(dataset._migrator.drop_index(table, name))
            except Exception as exc:
                flash('Error attempting to drop index: %s' % exc, 'danger')
                app.logger.exception('Error attempting to drop index.')
            else:
                flash('Index "%s" was dropped successfully!' % name, 'success')
                return redirect(url_for('table_structure', table=table))
        else:
            flash('Index name is required.', 'danger')

    return render_template(
        'drop_index.html',
        indexes=indexes,
        index_names=index_names,
        name=name,
        table=table)

@app.route('/<table>/drop-trigger/', methods=['GET', 'POST'])
@require_table
def drop_trigger(table):
    dataset = get_dataset()
    request_data = get_request_data()
    name = request_data.get('name', '')
    triggers = dataset.get_triggers(table)
    trigger_names = [trigger.name for trigger in triggers]

    if request.method == 'POST':
        if name in trigger_names:
            try:
                dataset.query('DROP TRIGGER %s;' % quote_ident(name))
            except Exception as exc:
                flash('Error attempting to drop trigger: %s' % exc, 'danger')
                app.logger.exception('Error attempting to drop trigger.')
            else:
                flash('Trigger "%s" was dropped successfully!' % name, 'success')
                return redirect(url_for('table_structure', table=table))
        else:
            flash('Trigger name is required.', 'danger')

    return render_template(
        'drop_trigger.html',
        triggers=triggers,
        trigger_names=trigger_names,
        name=name,
        table=table)


@app.route('/<table>/content/', methods=['GET', 'POST'])
@require_table
def table_content(table):
    dataset = get_dataset()
    dataset.ensure_cache()
    ds_table = dataset[table]
    model = ds_table.model_class
    is_composite_pk = isinstance(model._meta.primary_key, CompositeKey)

    # Views get a synthetic all-column pk from introspection, which is not
    # a usable row key. They get no row links and no editing.
    allow_detail = (model._meta.primary_key is not False and
                    not dataset.cached_is_view(table))
    allow_edit = allow_detail and not dataset.is_readonly
    allow_bulk = allow_edit and not is_composite_pk

    if request.method == 'POST':
        action = request.form.get('action')
        values = _bulk_delete_values(request.form.getlist('pk'))
        if not allow_bulk:
            flash('Cannot perform bulk operation on this table.', 'warning')
        elif action != 'bulk-delete':
            flash('Unrecognized action', 'warning')
        elif not values:
            flash('No rows were selected.', 'warning')
        else:
            try:
                n = (model.delete()
                     .where(model._meta.primary_key.in_(values))
                     .execute())
            except Exception as exc:
                flash('Error performing bulk delete: %s' % exc, 'danger')
                app.logger.exception('Error performing bulk delete.')
            else:
                flash('Successfully deleted %s row(s)' % n, 'success')
        return redirect(request.full_path)

    page_number = request.args.get('page') or ''
    if page_number == 'last': page_number = '1000000'
    page_number = int(page_number) if page_number.isdigit() else 1

    total_rows = ds_table.all().count()
    rows_per_page = app.config['ROWS_PER_PAGE']
    total_pages = max(1, int(math.ceil(total_rows / float(rows_per_page))))
    # Restrict bounds.
    page_number = max(min(page_number, total_pages), 1)

    previous_page = page_number - 1 if page_number > 1 else None
    next_page = page_number + 1 if page_number < total_pages else None

    query = ds_table.all().paginate(page_number, rows_per_page)

    columns = [f.column_name for f in model._meta.sorted_fields]
    try:
        ordering = int(request.args.get('ordering') or 0) or None
    except ValueError:
        ordering = None
    if ordering:
        idx = abs(ordering) - 1
        if 0 <= idx < len(columns):
            field = model._meta.sorted_fields[idx]
            query = query.order_by(field.desc() if ordering < 0 else field.asc())
        else:
            ordering = None

    # One capped most-recent-first list, so browsing many tables cannot
    # bloat the cookie. A dict loses order because flask sorts session keys.
    for key in [k for k in session if k.endswith('.last_viewed')]:
        del session[key]  # Per-table keys written by older versions.
    last_viewed = [e for e in session.get('last_viewed') or []
                   if e[0] != table]
    last_viewed.insert(0, (table, page_number, ordering))
    session['last_viewed'] = last_viewed[:10]

    table_pk = model._meta.primary_key
    rows, keys = [], ([] if allow_detail else None)
    for row in query:
        rows.append([row[c] for c in columns])
        if allow_detail:
            keys.append(encode_pk(row, table_pk))
    result = Result('rows', columns=columns, rows=rows, keys=keys)

    fk_lookup = {fk.column: (fk.dest_table, fk.dest_column)
                 for fk in dataset.cached_foreign_keys(table)}

    return render_template(
        'table_content.html',
        allow_bulk=allow_bulk,
        allow_detail=allow_detail,
        allow_edit=allow_edit,
        fk_lookup=fk_lookup,
        next_page=next_page,
        ordering=ordering,
        page=page_number,
        previous_page=previous_page,
        result=result,
        table=table,
        table_sql=dataset.cached_table_sql(table),
        total_pages=total_pages,
        total_rows=total_rows)

def _blank_means_null(field):
    # Whitelist of types that cannot hold an empty string. Anything
    # text-like keeps '', which is a real value there, including a
    # foreign key that references a TEXT primary key.
    if isinstance(field, ForeignKeyField):
        field = field.rel_field
    return isinstance(field, (IntegerField, FloatField, DecimalField,
                              BooleanField, DateTimeField, DateField,
                              TimeField))

def minimal_validate_field(field, value):
    if value.lower().strip() == 'null':
        value = None
    elif value == '' and _blank_means_null(field):
        # A form cannot submit the absence of a value for an enabled
        # input, so blank means NULL where '' is unrepresentable.
        value = None
    if value is None and not field.null:
        return 'NULL', 'Column does not allow NULL values.'
    if value is None:
        return None, None
    if isinstance(field, IntegerField):
        try:
            _ = int(value)
        except Exception:
            return value, 'Value is not a number.'
    elif isinstance(field, FloatField):
        try:
            _ = float(value)
        except Exception:
            return value, 'Value is not a numeric/real.'
    elif isinstance(field, DecimalField):
        try:
            value = str(decimal.Decimal(value))
        except Exception as exc:
            return value, 'Value is not a Decimal.'
    elif isinstance(field, BooleanField):
        if value.lower() not in ('1', '0', 'true', 'false', 't', 'f'):
            return value, 'Value must be 1, 0, true, false, t or f.'
        value = True if value.lower() in ('1', 't', 'true') else False
    elif isinstance(field, (DateTimeField, DateField, TimeField)):
        if isinstance(field.adapt(value), str):
            return value, ('Value does not match any supported format: %s.' %
                           ', '.join(field.formats))
    elif isinstance(field, BlobField):
        if app.config['BLOB_AS_BASE64']:
            try:
                value = base64.b64decode(value)
            except Exception as exc:
                return value, 'Value must be base64-encoded binary data.'
        else:
            try:
                value = bytes.fromhex(value)
            except Exception as exc:
                return value, 'Value must be valid hex representation.'
    try:
        field.db_value(value)
    except Exception as exc:
        return value, str(exc)

    return value, None

@app.route('/<table>/insert/', methods=['GET', 'POST'])
@require_table
def table_insert(table):
    dataset = get_dataset()
    dataset.ensure_cache()
    model = dataset[table].model_class

    columns = []
    fields = []
    defaults = {}
    row = {}
    for column in dataset.get_columns(table):
        field = model._meta.columns[column.name]
        if isinstance(field, AutoField):
            continue
        if column.default:
            defaults[column.name] = column.default
        columns.append(column)
        fields.append(field)
        row[field.name] = ''

    edited = set()
    errors = {}
    if request.method == 'POST':
        insert = {}
        for key, value in request.form.items():
            if key not in model._meta.fields: continue
            field = model._meta.fields[key]
            if isinstance(field, AutoField):
                continue
            edited.add(field.name)
            row[field.name] = value

            value, err = minimal_validate_field(field, value)
            if err:
                errors[key] = err
            else:
                insert[field] = value

        if errors:
            flash('One or more errors prevented the row being inserted.',
                  'danger')
        elif insert:
            try:
                with dataset.transaction() as txn:
                    n = model.insert(insert).execute()
            except Exception as exc:
                flash('Insert failed: %s' % exc, 'danger')
                app.logger.exception('Error attempting to insert row into %s.', table)
            else:
                flash('Successfully inserted record (%s).' % n, 'success')
                return redirect(url_for(
                    'table_content',
                    table=table,
                    page='last'))
        else:
            flash('No data was specified to be inserted.', 'warning')
    else:
        edited = set(model._meta.sorted_field_names) - set(defaults)  # Make all fields editable on load.

    columns_fields = zip(columns, fields)

    return render_template(
        'table_insert.html',
        columns_fields=columns_fields,
        defaults=defaults,
        edited=edited,
        errors=errors,
        model=model,
        row=row,
        table=table)

def redirect_to_previous(table):
    entries = [e for e in session.get('last_viewed') or [] if e[0] == table]
    if not entries:
        return redirect(url_for('table_content', table=table))
    _, page, ordering = entries[0]
    kw = {}
    if page and page != 1:
        kw['page'] = page
    if ordering:
        kw['ordering'] = ordering
    return redirect(url_for('table_content', table=table, **kw))

@app.route('/<table>/update/<b64:pk>/', methods=['GET', 'POST'])
@require_table
def table_update(table, pk):
    dataset = get_dataset()
    dataset.ensure_cache()
    model = dataset[table].model_class
    table_pk = model._meta.primary_key
    if not table_pk:
        flash('Table must have a primary key to perform update.', 'danger')
        return redirect(url_for('table_content', table=table))

    expr = decode_pk(model, pk)
    try:
        obj = model.get(expr)
    except model.DoesNotExist:
        pk_repr = pk_display(table_pk, pk)
        flash('Could not fetch row with primary-key %s.' % str(pk_repr), 'danger')
        return redirect(url_for('table_content', table=table))

    columns = []
    fields = []
    for column in dataset.get_columns(table):
        columns.append(column)
        fields.append(model._meta.columns[column.name])

    row = {}
    for field in fields:
        value = getattr(obj, field.name)
        if value is None:
            row[field.name] = None
        elif isinstance(field, BlobField):
            if app.config['BLOB_AS_BASE64']:
                row[field.name] = base64.b64encode(value).decode('utf8')
            else:
                row[field.name] = value.hex()
        else:
            row[field.name] = value

    edited = set()
    errors = {}
    if request.method == 'POST':
        update = {}
        for key, value in request.form.items():
            if key not in model._meta.fields: continue
            field = model._meta.fields[key]
            edited.add(field.name)
            row[field.name] = value

            value, err = minimal_validate_field(field, value)
            if err:
                errors[key] = err
            else:
                update[field] = value

        if errors:
            flash('One or more errors prevented the row being updated.',
                  'danger')
        elif update:
            try:
                with dataset.transaction() as txn:
                    n = model.update(update).where(expr).execute()
            except Exception as exc:
                flash('Update failed: %s' % exc, 'danger')
                app.logger.exception('Error attempting to update row from %s.', table)
            else:
                flash('Successfully updated %s record.' % n, 'success')
                return redirect_to_previous(table)
        else:
            flash('No data was specified to be updated.', 'warning')

    columns_fields = zip(columns, fields)

    return render_template(
        'table_update.html',
        columns_fields=columns_fields,
        edited=edited,
        errors=errors,
        fields=fields,
        model=model,
        pk=pk,
        row=row,
        table=table,
        table_pk=model._meta.primary_key)

@app.route('/<table>/delete/<b64:pk>/', methods=['GET', 'POST'])
@require_table
def table_delete(table, pk):
    dataset = get_dataset()
    dataset.ensure_cache()
    model = dataset[table].model_class
    table_pk = model._meta.primary_key
    if not table_pk:
        flash('Table must have a primary key to perform delete.', 'danger')
        return redirect(url_for('table_content', table=table))

    expr = decode_pk(model, pk)
    try:
        row = model.select().where(expr).dicts().get()
    except model.DoesNotExist:
        pk_repr = pk_display(table_pk, pk)
        flash('Could not fetch row with primary-key %s.' % str(pk_repr), 'danger')
        return redirect(url_for('table_content', table=table))

    if request.method == 'POST':
        try:
            with dataset.transaction() as txn:
                n = model.delete().where(expr).execute()
        except Exception as exc:
            flash('Delete failed: %s' % exc, 'danger')
            app.logger.exception('Error attempting to delete row from %s.', table)
        else:
            flash('Successfully deleted %s record.' % n, 'success')
            return redirect_to_previous(table)

    return render_template(
        'table_delete.html',
        model=model,
        pk=pk,
        row=row,
        table=table,
        table_pk=table_pk)

@app.route('/<table>/row/<b64:pk>/')
@require_table
def table_row_detail(table, pk):
    dataset = get_dataset()
    dataset.ensure_cache()
    model = dataset[table].model_class
    table_pk = model._meta.primary_key
    if not table_pk or dataset.cached_is_view(table):
        flash('Row detail requires a table with a primary key.', 'danger')
        return redirect(url_for('table_content', table=table))

    expr = decode_pk(model, pk)
    try:
        row = model.select().where(expr).dicts().get()
    except model.DoesNotExist:
        pk_repr = pk_display(table_pk, pk)
        flash('Could not fetch row with primary-key %s.' % str(pk_repr),
              'danger')
        return redirect(url_for('table_content', table=table))

    fk_lookup = {fk.column: (fk.dest_table, fk.dest_column)
                 for fk in dataset.cached_foreign_keys(table)}
    return render_template(
        'table_row.html',
        allow_edit=not dataset.is_readonly,
        fk_lookup=fk_lookup,
        model=model,
        pk=pk,
        row=row,
        table=table,
        table_pk=table_pk)

@app.route('/<table>/query/', methods=['GET', 'POST'])
@require_table
def table_query(table):
    return _query_view('table_query.html', table)

def export(query, export_format, table=None):
    dataset = get_dataset()
    buf = StringIO()
    if export_format == 'json':
        kwargs = {'indent': 2}
        filename = 'export.json'
        mimetype = 'application/json'
    else:
        kwargs = {}
        filename = 'export.csv'
        mimetype = 'text/csv'

    if table:
        filename = '%s-%s' % (table, filename)

    # Avoid any special chars in export filename.
    filename = re.sub(r'[^\w\d\-\.]+', '', filename)

    if peewee_version >= (4, 0, 2):
        kwargs['base64_bytes'] = app.config['BLOB_AS_BASE64']

    dataset.freeze(query, export_format, file_obj=buf, **kwargs)

    response_data = buf.getvalue().encode('utf8')
    response = make_response(response_data)
    response.headers['Content-Length'] = len(response_data)
    response.headers['Content-Type'] = mimetype
    response.headers['Content-Disposition'] = 'attachment; filename="%s"' % (
        filename)
    response.headers['Expires'] = 0
    response.headers['Pragma'] = 'public'
    return response

@app.route('/<table>/export/', methods=['GET', 'POST'])
@require_table
def table_export(table):
    dataset = get_dataset()
    columns = dataset.get_columns(table)
    if request.method == 'POST':
        export_format = request.form.get('export_format') or 'json'
        col_dict = {c.name: c for c in columns}
        selected = [c for c in (request.form.getlist('columns') or [])
                    if c in col_dict]
        if not selected:
            flash('Please select one or more columns to export.', 'danger')
        else:
            model = dataset[table].model_class
            fields = [model._meta.columns[c] for c in selected]
            query = model.select(*fields).dicts()
            try:
                return export(query, export_format, table)
            except Exception as exc:
                flash('Error generating export: %s' % exc, 'danger')
                app.logger.exception('Error generating export.')

    return render_template(
        'table_export.html',
        columns=columns,
        table=table)

@app.route('/download/')
def db_download():
    dataset = get_dataset()
    # The same filename sanitizer the row exports use.
    filename = re.sub(r'[^\w\d\-\.]+', '', dataset.basename) or 'database.db'
    tmp_dir = tempfile.mkdtemp()
    dest = os.path.join(tmp_dir, filename)
    try:
        # VACUUM INTO produces a consistent snapshot even mid-write.
        dataset.query('VACUUM INTO ?', (dest,))
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        flash('Error creating database snapshot: %s' % exc, 'danger')
        app.logger.exception('Error creating database snapshot.')
        return redirect(url_for('index'))

    def remove_snapshot():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def stream_then_remove():
        # The finally block cleans up when the body is consumed or the
        # client disconnects mid-stream.
        try:
            with open(dest, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
        finally:
            remove_snapshot()

    # The ClosingIterator also cleans up when the response is closed before
    # the generator ever starts, which is what a HEAD request does. Closing
    # an unstarted generator skips its finally block. send_file was no good
    # here at all, its direct-passthrough response never runs call_on_close.
    response = Response(ClosingIterator(stream_then_remove(), remove_snapshot),
                        mimetype='application/octet-stream')
    response.headers['Content-Length'] = os.path.getsize(dest)
    response.headers['Content-Disposition'] = 'attachment; filename="%s"' % (
        filename)
    return response

@app.route('/<table>/import/', methods=['GET', 'POST'])
@require_table
def table_import(table):
    dataset = get_dataset()
    count = None
    request_data = get_request_data()
    strict = bool(request_data.get('strict'))

    if request.method == 'POST':
        file_obj = request.files.get('file')
        if not file_obj:
            flash('Please select an import file.', 'danger')
        elif not file_obj.filename.lower().endswith(('.csv', '.json')):
            flash('Unsupported file-type. Must be a .json or .csv file.',
                  'danger')
        else:
            if file_obj.filename.lower().endswith('.json'):
                format = 'json'
            else:
                format = 'csv'

            # Here we need to translate the file stream. Werkzeug uses a
            # spooled temporary file opened in wb+ mode, which is not
            # compatible with Python's CSV module. We'd need to reach pretty
            # far into Flask's internals to modify this behavior, so instead
            # we'll just translate the stream into utf8-decoded unicode.
            try:
                stream = TextIOWrapper(file_obj, encoding='utf8')
            except AttributeError:
                # The SpooledTemporaryFile used by werkzeug does not
                # implement an API that the TextIOWrapper expects, so we'll
                # just consume the whole damn thing and decode it.
                # Fixed in werkzeug 0.15.
                stream = StringIO(file_obj.read().decode('utf8'))

            kwargs = {}
            if peewee_version >= (4, 0, 2):
                kwargs['base64_bytes'] = app.config['BLOB_AS_BASE64']
            try:
                with dataset.transaction():
                    count = dataset.thaw(
                        table,
                        format=format,
                        file_obj=stream,
                        strict=strict,
                        **kwargs)
            except Exception as exc:
                flash('Error importing file: %s' % exc, 'danger')
                app.logger.exception('Error importing file.')
            else:
                flash(
                    'Successfully imported %s objects from %s.' % (
                        count, file_obj.filename),
                    'success')
                return redirect(url_for('table_content', table=table))

    return render_template(
        'table_import.html',
        count=count,
        strict=strict,
        table=table)

@app.route('/<table>/drop/', methods=['GET', 'POST'])
@require_table
def drop_table(table):
    dataset = get_dataset()
    is_view = any(v.name == table for v in dataset.get_all_views())
    label = 'view' if is_view else 'table'
    if request.method == 'POST':
        try:
            if is_view:
                dataset.query('DROP VIEW %s;' % quote_ident(table))
            else:
                model_class = dataset[table].model_class
                model_class.drop_table()
        except Exception as exc:
            flash('Error attempting to drop %s "%s".' % (label, table), 'danger')
            app.logger.exception('Error attempting to drop %s "%s".', label, table)
        else:
            dataset.update_cache()  # Update all tables.
            flash('%s "%s" dropped successfully.' %
                  ('view' if is_view else 'table', table),
                  'success')
            return redirect(url_for('index'))

    return render_template('drop_table.html', is_view=is_view, table=table)

@app.template_filter('format_index')
def format_index(index_sql):
    split_regex = re.compile(r'\bon\b', re.I)
    if not split_regex.search(index_sql):
        return index_sql

    create, definition = split_regex.split(index_sql, 1)
    return '\nON '.join((create.strip(), definition.strip()))

@app.template_filter('encode_pk')
def encode_pk(row, pk):
    if isinstance(pk, CompositeKey):
        values = [row[f] for f in pk.field_names]
    else:
        values = [row[pk.column_name]]
    return key_encode(values)

def decode_pk(model, token):
    pk = model._meta.primary_key
    values = key_decode(token)
    if isinstance(pk, CompositeKey):
        fields = [pk.model._meta.columns[f] for f in pk.field_names]
        expressions = [(f == v) for f, v in zip(fields, values)]
        return reduce(operator.and_, expressions)
    return (pk == values[0])

@app.template_filter('pk_display')
def pk_display(table_pk, token):
    try:
        values = key_decode(token)
    except Exception:
        return token
    if isinstance(table_pk, CompositeKey):
        return tuple(values)
    value = values[0]
    return value.hex() if isinstance(value, bytes) else value

@app.template_filter('fk_link')
def fk_link(value, fk):
    # Link a foreign-key value to the referenced row via the query tab.
    dest_table, dest_column = fk
    sql = 'SELECT * FROM %s WHERE %s = %s' % (
        quote_ident(dest_table), quote_ident(dest_column), quote_value(value))
    return url_for('table_query', table=dest_table, sql=sql)

link_re = re.compile(r'(?:https?://|mailto:)[^\s]+')

@app.template_filter('value_filter')
def value_filter(value, max_length=50):
    if isinstance(value, (int, float)):
        return value

    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            value = value.decode('utf8')
        except UnicodeDecodeError:
            if app.config['BLOB_AS_BASE64']:
                value = base64.b64encode(value).decode('utf8')
            else:
                value = value.hex()
            if app.config['TRUNCATE_VALUES']:
                value = value[:1024]
    if isinstance(value, str):
        if link_re.fullmatch(value):
            label = value
            if len(value) > max_length and app.config['TRUNCATE_VALUES']:
                label = value[:max_length] + '...'
            return '<a href="%s">%s</a>' % (escape(value), escape(label))
        if len(value) > max_length:
            if app.config['TRUNCATE_VALUES']:
                return ('<span class="truncated">%s</span> '
                        '<span class="full" style="display:none;">%s</span>'
                        '<a class="toggle-value" href="#">...</a>') % (
                            escape(value[:max_length]),
                            escape(value))
            return '<span class="full">%s</span>' % escape(value)
        if '\n' in value:
            # Line breaks display only when the data has them. The td must
            # stay whitespace-insensitive or template indentation renders.
            return '<span class="pre">%s</span>' % escape(value)
        return escape(value)
    return value

column_re = re.compile(r'(.+?)\((.+)\)', re.S)
column_split_re = re.compile(r'(?:[^,(]|\([^)]*\))+')

def _format_create_table(sql):
    create_table, column_list = column_re.search(sql).groups()
    columns = ['  %s' % column.strip()
               for column in column_split_re.findall(column_list)
               if column.strip()]
    return '%s (\n%s\n)' % (
        create_table,
        ',\n'.join(columns))

@app.template_filter()
def format_create_table(sql):
    try:
        return _format_create_table(sql)
    except:
        return sql

@app.template_filter('highlight')
def highlight_filter(data):
    return Markup(syntax_highlight(data))

def get_query_images():
    accum = []
    image_dir = os.path.join(app.static_folder, 'img')
    if not os.path.exists(image_dir):
        return accum
    for filename in sorted(os.listdir(image_dir)):
        basename = os.path.splitext(os.path.basename(filename))[0]
        parts = basename.split('-')
        accum.append((parts, 'img/' + filename))
    return accum

#
# Flask application helpers.
#

@app.context_processor
def _general():
    return {
        'dataset': get_dataset(),
        'datasets': datasets,
        'enable_load': app.config.get('ENABLE_LOAD'),
        'enable_filesystem': app.config.get('ENABLE_FILESYSTEM'),
        'login_required': bool(app.config.get('PASSWORD')),
        'version': __version__,
    }

@app.context_processor
def _now():
    return {'now': datetime.datetime.now()}

@app.before_request
def _reject_cross_site_post():
    # Any web page can auto-submit a form to this app. Browsers label such
    # requests with Sec-Fetch-Site. Non-browser clients omit the header.
    if request.method == 'POST' and \
       request.headers.get('Sec-Fetch-Site') == 'cross-site':
        abort(403)

@app.before_request
def _connect_db():
    dataset = get_dataset()
    dataset.connect()
    if dataset_config.get('startup_hook'):
        dataset_config['startup_hook'](dataset._database)

@app.teardown_request
def _close_db(exc):
    dataset = get_dataset()
    if not dataset._database.is_closed():
        dataset.close()


class PrefixMiddleware(object):
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = '/%s' % prefix.strip('/')
        self.prefix_len = len(self.prefix)

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO']
        if path == self.prefix or path.startswith(self.prefix + '/'):
            environ['PATH_INFO'] = path[self.prefix_len:] or '/'
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)
        else:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return ['URL does not match application prefix.'.encode()]

#
# Script options.
#

def get_option_parser():
    parser = optparse.OptionParser()
    parser.add_option(
        '-p',
        '--port',
        default=8080,
        help='Port for web interface, default=8080',
        type='int')
    parser.add_option(
        '-H',
        '--host',
        default='127.0.0.1',
        help='Host for web interface, default=127.0.0.1')
    parser.add_option(
        '-d',
        '--debug',
        action='store_true',
        help='Run server in debug mode')
    parser.add_option(
        '-x',
        '--no-browser',
        action='store_false',
        default=False,
        dest='browser',
        help='Do not automatically open browser page.')
    parser.add_option(
        '-b',
        '--browser',
        action='store_true',
        default=False,
        dest='browser',
        help='Automatically open browser page.')
    parser.add_option(
        '-l',
        '--log-file',
        dest='log_file',
        help='Filename for application logs.')
    parser.add_option(
        '-q',
        '--quiet',
        action='store_true',
        dest='quiet',
        help='Only log errors to console.')
    parser.add_option(
        '-P',
        '--password',
        action='store_true',
        dest='prompt_password',
        help='Prompt for password to access database browser.')
    parser.add_option(
        '-r',
        '--read-only',
        action='store_true',
        dest='read_only',
        help='Open database in read-only mode.')
    parser.add_option(
        '-R',
        '--rows-per-page',
        default=50,
        dest='rows_per_page',
        help='Number of rows to display per page in content tab (default=50)',
        type='int')
    parser.add_option(
        '-Q',
        '--query-rows-per-page',
        default=1000,
        dest='query_rows_per_page',
        help='Number of rows to display per page in query tab (default=1000)',
        type='int')
    parser.add_option(
        '-T',
        '--no-truncate',
        action='store_false',
        default=True,
        dest='truncate_values',
        help=('Disable truncating long text values. By default text values '
              'are ellipsized after 50 characters and the full text is shown '
              'on click.'))
    parser.add_option(
        '-B',
        '--base64',
        action='store_true',
        dest='base64',
        help='BLOB data as base64 (default is hex)')
    parser.add_option(
        '-u',
        '--url-prefix',
        dest='url_prefix',
        help='URL prefix for application.')
    parser.add_option(
        '-f',
        '--foreign-keys',
        action='store_true',
        dest='foreign_keys',
        help='Enable the foreign_keys pragma.')
    parser.add_option(
        '-e',
        '--extension',
        action='append',
        dest='extensions',
        help='Path or name of loadable extension.')
    parser.add_option(
        '-s',
        '--startup-hook',
        dest='startup_hook',
        help=('Path to a startup hook used to initialize the connection '
              'before each request, e.g. my.module.some_callable'))
    parser.add_option(
        '-L',
        '--enable-load',
        action='store_true',
        dest='enable_load',
        help=('Enable loading additional databases at runtime (upload only). '
              'For adding local databases use --enable-filesystem'))
    parser.add_option(
        '-U',
        '--upload-dir',
        dest='upload_dir',
        help=('Destination directory for uploaded databases (-L). If not '
              'specified, a system tempdir will be used.'))
    parser.add_option(
        '-F',
        '--enable-filesystem',
        action='store_true',
        dest='enable_filesystem',
        help=('Enable loading additional databases by specifying on-disk '
              'path at runtime.'))
    ssl_opts = optparse.OptionGroup(parser, 'SSL options')
    ssl_opts.add_option(
        '-c',
        '--ssl-cert',
        dest='ssl_cert',
        help='SSL certificate file path.')
    ssl_opts.add_option(
        '-k',
        '--ssl-key',
        dest='ssl_key',
        help='SSL private key file path.')
    ssl_opts.add_option(
        '-a',
        '--ad-hoc',
        action='store_true',
        dest='ssl_ad_hoc',
        help='Use ad-hoc SSL context.')
    parser.add_option_group(ssl_opts)
    return parser

def die(msg, exit_code=1):
    sys.stderr.write('%s\n' % msg)
    sys.stderr.flush()
    sys.exit(exit_code)

def open_browser_tab(host, port, scheme='http'):
    url = '%s://%s:%s/' % (scheme, host, port)

    def _open_tab(url):
        time.sleep(1.5)
        webbrowser.open_new_tab(url)

    thread = threading.Thread(target=_open_tab, args=(url,))
    thread.daemon = True
    thread.start()

def install_auth_handler(password):
    app.config['PASSWORD'] = password

    @app.before_request
    def check_password():
        if not session.get('authorized') and request.path != '/login/' and \
           not request.path.startswith(('/static/', '/favicon')):
            flash('You must log-in to view the database browser.', 'danger')
            session['next_url'] = request.base_url
            return redirect(url_for('login'))

def initialize_dataset(filename):
    dataset_kw = {}
    if peewee_version >= (3, 14, 9):
        dataset_kw['include_views'] = True

    if dataset_config['read_only']:
        if peewee_version < (3, 5, 1):
            die('Peewee 3.5.1 or newer is required for read-only access.')
        db = SqliteDatabase('file:%s?mode=ro' % filename, uri=True)
        try:
            db.connect()
        except OperationalError:
            die('Unable to open database file in read-only mode. Ensure that '
                'the database exists in order to use read-only mode.')
        db.close()
    else:
        db = SqliteDatabase(filename)

    if dataset_config['foreign_keys']:
        db.pragma('foreign_keys', True, permanent=True)

    if dataset_config['extensions']:
        # Load extensions before performing introspection.
        for ext in dataset_config['extensions']:
            db.load_extension(ext)

    if dataset_config['startup_hook']:
        dataset_config['startup_hook'](db)

    dataset = SqliteDataSet(db, **dataset_kw)
    dataset.ensure_cache()
    dataset.close()
    return dataset

def initialize_app(filenames, read_only=False, password=None, url_prefix=None,
                   extensions=None, foreign_keys=None, startup_hook=None):
    global datasets
    global dataset_config

    dataset_config.update(
        read_only=read_only,
        extensions=extensions,
        foreign_keys=foreign_keys,
        startup_hook=startup_hook)

    if password:
        install_auth_handler(password)

    if url_prefix:
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=url_prefix)

    for filename in filenames:
        datasets[os.path.basename(filename)] = initialize_dataset(filename)

def configure_app():
    # This function exists to act as a console script entry-point.
    parser = get_option_parser()
    options, args = parser.parse_args()

    if not args:
        die('Error: missing required path to database file.')

    werkzeug_logger = logging.getLogger('werkzeug')
    if options.log_file:
        fmt = logging.Formatter('[%(asctime)s] - [%(levelname)s] - %(message)s')
        handler = WatchedFileHandler(options.log_file)
        handler.setLevel(logging.DEBUG if options.debug else logging.WARNING)
        handler.setFormatter(fmt)
        app.logger.addHandler(handler)

        # Remove default handler.
        from flask.logging import default_handler
        app.logger.removeHandler(default_handler)

    if options.quiet:
        app.logger.setLevel(logging.ERROR)
        werkzeug_logger.setLevel(logging.ERROR)

    password = None
    if options.prompt_password:
        if os.environ.get('SQLITE_WEB_PASSWORD'):
            password = os.environ['SQLITE_WEB_PASSWORD']
        else:
            while True:
                password = getpass('Enter password: ')
                password_confirm = getpass('Confirm password: ')
                if password != password_confirm:
                    print('Passwords did not match!')
                else:
                    break

    if options.rows_per_page:
        app.config['ROWS_PER_PAGE'] = options.rows_per_page
    if options.query_rows_per_page:
        app.config['QUERY_ROWS_PER_PAGE'] = options.query_rows_per_page
    if options.base64:
        app.config['BLOB_AS_BASE64'] = options.base64

    app.config['TRUNCATE_VALUES'] = options.truncate_values

    # Store reference to these config options.
    app.config['ENABLE_LOAD'] = options.enable_load
    app.config['ENABLE_FILESYSTEM'] = options.enable_filesystem
    app.config['DB_UPLOAD_DIR'] = options.upload_dir

    if options.startup_hook:
        try:
            module_path, hook_name = options.startup_hook.rsplit('.', 1)
        except Exception:
            die('startup hook must be dotted-path to module.hook_function')
        module = importlib.import_module(module_path)
        try:
            hook = getattr(module, hook_name)
        except AttributeError:
            die('Hook named "%s" not found in %s' % (hook_name, module))
    else:
        hook = None

    # Initialize the dataset instances and (optionally) authentication handler.
    initialize_app(args, options.read_only, password, options.url_prefix,
                   options.extensions, options.foreign_keys, hook)

    if options.upload_dir and not options.enable_load:
        app.logger.warning('--upload-dir has no effect without --enable-load.')

    if options.browser:
        scheme = 'https' if (options.ssl_ad_hoc or options.ssl_cert) else 'http'
        open_browser_tab(options.host, options.port, scheme)

    if password:
        key = b'sqlite-web-' + args[0].encode('utf8') + password.encode('utf8')
        app.secret_key = hashlib.sha256(key).hexdigest()

    # Set up SSL context, if specified.
    kwargs = {
        'host': options.host,
        'port': options.port,
        'debug': options.debug,
    }

    if options.ssl_ad_hoc:
        kwargs['ssl_context'] = 'adhoc'

    if options.ssl_cert and options.ssl_key:
        if not os.path.exists(options.ssl_cert) or not os.path.exists(options.ssl_key):
            die('ssl cert or ssl key not found. Please check the file-paths.')
        kwargs['ssl_context'] = (options.ssl_cert, options.ssl_key)
    elif options.ssl_cert:
        die('ssl key "-k" is required alongside the ssl cert')
    elif options.ssl_key:
        die('ssl cert "-c" is required alongside the ssl key')

    return kwargs


def main():
    kwargs = configure_app()  # Read options from command-line, configure app.

    # Run WSGI application.
    app.run(**kwargs)


if __name__ == '__main__':
    main()
