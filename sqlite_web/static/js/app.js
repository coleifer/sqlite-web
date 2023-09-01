App = window.App || {};

(function(exports, $) {
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

    exports.Bookmarks = Bookmarks;
    exports.Recent = Recent;
})(App, jQuery);
