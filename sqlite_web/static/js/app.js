App = window.App || {};

(function(exports, $) {
    initialize = function() {
        /* Toggle long values on/off. */
        $('a.toggle-value').on('click', function(e) {
            e.preventDefault();
            var elem = $(this),
                truncated = elem.siblings('span.truncated'),
                full = elem.siblings('span.full');
            truncated.toggle();
            full.toggle();
        });

        /* Show/hide table info div. */
        var tableInfo = $('div#tableInfo');
        if (tableInfo.length > 0) {
            if (localStorage.getItem('tableInfo') === 'false') {
                tableInfo.hide();
            }

            $('a#toggleTableInfo').on('click', function(e) {
                e.preventDefault();
                var show = !tableInfo.is(':visible');
                localStorage.setItem('tableInfo', show ? 'true' : 'false')
                tableInfo.toggle();
            });
        }

        /* Show SQL (e.g. for indexes / triggers). */
        $('a.view-sql').on('click', function(e) {
            e.preventDefault();
            var elem = $(this),
                pre = elem.siblings('div'),
                modalDiv = $('div#sql-modal');
            modalDiv.find('h5.modal-title').text(elem.data('name'));
            modalDiv.find('.modal-body').empty().append(pre.clone().show());
            modalDiv.modal({'keyboard': true});
        });

        /* Show one of the SQL syntax railroad diagrams. */
        $('a.sql-image').on('click', function(e) {
            e.preventDefault();
            var elem = $(this),
                imgUrl = elem.attr('href'),
                modalDiv = $('div#sql-image-modal');
            modalDiv.find('h5.modal-title').text(elem.text());
            modalDiv.find('.modal-body').empty().append(
                $('<img src="' + imgUrl + '" style="max-width:100%;" />'));
            modalDiv.modal({'keyboard': true});
        });

        /* Toggle helper virtual tables and table typeahead search. */
        $('a#toggle-helper-tables').on('click', function(e) {
            e.preventDefault();
            $('ul#helper-tables').toggle();
        });
        $('input#table-search').on('keyup', function(e) {
            var searchQuery = $(this).val().toUpperCase();
            $('li.table-link').each(function() {
                var elem = $(this),
                    tableName = elem.find('a').prop('innerText').toUpperCase();
                elem.toggle(tableName.indexOf(searchQuery) != -1);
            });
        });

        /* Checkboxes for enabling/disabling inputs. */
        $('input.chk-enable-column').on('click', function (evt) {
            var elem = $(this),
                inp = $('#' + elem.data('target-element'));
            inp.prop('disabled', elem.is(':checked') ? false : true);
        });

        $('input#toggle-checkboxes').on('click', function (evt) {
            $('input.chk-enable-column').prop('checked', $(this).is(':checked'));
            $('input.chk-enable-column').each(function(_) {
                var elem = $(this),
                    inp = $('#' + elem.data('target-element'));
                inp.prop('disabled', elem.is(':checked') ? false : true);
            });
        });

        /* Initialize focus on SQL textarea. */
        var sqlTextarea = $('textarea#sql');
        if (sqlTextarea.length > 0) {
            sqlTextarea.focus();
        }
    };

    Bookmarks = function() {};

    Bookmarks.prototype.initialize = function() {
        this.bkList = [];
        this.bk = {};
        this.container = $('div#bookmarks');
        this.sqlTextarea = $('textarea#sql');
        this.modal = $('div#bookmark-modal');
        this.inpName = this.modal.find('input#bookmark-name');
        this.btnAdd = $('button#add-bookmark');
        this.btnSave = this.modal.find('button#save-bookmark');
        this.frmSave = this.modal.find('form');

        var queries = JSON.parse(localStorage.getItem('bookmarks') || '[]');
        for (var i = 0; i < queries.length; i++) {
            var name = queries[i][0],
                sql = queries[i][1];
            if (!(name in this.bk)) {
                this.bkList.push(name);
                this.bk[name] = sql;
            }

        }

        this.bindHandlers();
        this.populateMenu();
    };

    Bookmarks.prototype.bindHandlers = function() {
        var self = this;
        this.btnAdd.on('click', function(e) {
            e.preventDefault();
            self.inpName.val('');
            self.modal.modal({'keyboard': true});
        });

        this.btnSave.on('click', function(e) {
            e.preventDefault();
            self.saveBookmark();
            self.modal.modal('hide');
        });

        this.frmSave.on('submit', function(e) {
            e.preventDefault();
            self.saveBookmark();
            self.modal.modal('hide');
        });
    };

    Bookmarks.prototype.saveBookmark = function() {
        var name = this.inpName.val();
        if (!name) return;

        var i = this.bkList.indexOf(name);
        if (i >= 0) {
            this.bkList.splice(i, 1);
        }
        this.bkList.unshift(name);
        this.bk[name] = this.sqlTextarea.val();

        this.saveData();
        this.populateMenu();
    };

    Bookmarks.prototype.deleteBookmark = function(name) {
        if (!name) return;
        var i = this.bkList.indexOf(name);
        if (i < 0) return;

        this.bkList.splice(i, 1);
        delete this.bk[name];
        this.saveData();
        this.populateMenu();
    };

    Bookmarks.prototype.saveData = function() {
        var accum = [];
        for (var i = 0; i < this.bkList.length; i++) {
            accum.push([this.bkList[i], this.bk[this.bkList[i]]]);
        }
        localStorage.setItem('bookmarks', JSON.stringify(accum));
    };

    Bookmarks.prototype.populateMenu = function() {
        var self = this;
        this.container.empty();
        for (var i = 0; i < this.bkList.length; i++) {
            var name = this.bkList[i],
                sql = this.bk[name];

            var elem = $(
                '<div class="dropdown-item" data-name="' + name + '" style="min-width: 250px;">' +
                '<a class="bk-delete float-right" href="#">X</a>' +
                '<a class="bk" href="#" style="display: block;">' + name + '</a> ' +
                '</div>');
            var bookmark = elem.find('a.bk'),
                del = elem.find('a.bk-delete');

            bookmark.on('click', function(e) {
                e.preventDefault();
                var name = $(this).parent().data('name');
                self.sqlTextarea.val(self.bk[name]);
                self.sqlTextarea.parents('form').submit();
            });
            del.on('click', function(e) {
                e.preventDefault();
                var name = $(this).parent().data('name');
                self.deleteBookmark(name);
            });
            this.container.append(elem);
        }
    };

    Recent = function() {};

    Recent.prototype.initialize = function(sql) {
        this.sqlTextarea = $('textarea#sql');
        this.form = this.sqlTextarea.parents('form');
        this.queries = JSON.parse(localStorage.getItem('recentQueries') || '[]');
        this.idx = 0;
        if (sql) {
            var accum = [sql];
            for (var i = 0; i < this.queries.length; i++) {
                if (this.queries[i] !== sql) { accum.push(this.queries[i]) };
            }
            this.queries = accum.slice(0, 50);
            localStorage.setItem('recentQueries', JSON.stringify(this.queries));
        }

        this.bindHandlers();
    }

    Recent.prototype.bindHandlers = function() {
        var self = this;
        this.sqlTextarea.on('keydown', function(e) {
            if ((e.metaKey || e.ctrlKey) && e.keyCode == 13) { // ctrl+enter or meta+enter.
                self.form.submit();
            }
            if (e.shiftKey) {
                if (e.keyCode == 38) { // up.
                    self.idx += 1;
                    if (self.idx >= self.queries.length) { self.idx = 0; }
                    self.sqlTextarea.html(self.queries[self.idx]);
                    e.preventDefault();
                } else if (e.keyCode == 40) { // down.
                    self.idx -= 1;
                    if (self.idx < 0) { self.idx = self.queries.length - 1; }
                    self.sqlTextarea.html(self.queries[self.idx]);
                    e.preventDefault();
                }
            }
        });
    };

    exports.initialize = initialize;
    exports.Bookmarks = Bookmarks;
    exports.Recent = Recent;
})(App, jQuery);
