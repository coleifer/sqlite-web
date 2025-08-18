import os
import unittest
import tempfile
import sqlite3

from sqlite_web import sqlite_web

# Sample data
GIF_EMPTY = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
MP4_EMPTY = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'

class SqliteWebTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = sqlite_web.app
        self.app.config['TESTING'] = True
        sqlite_web.initialize_app(self.db_path)
        self.client = self.app.test_client()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE media (id INTEGER PRIMARY KEY, data BLOB)")
            conn.execute("INSERT INTO media (id, data) VALUES (?, ?)", (1, GIF_EMPTY))
            conn.execute("INSERT INTO media (id, data) VALUES (?, ?)", (2, MP4_EMPTY))
            conn.execute("INSERT INTO media (id, data) VALUES (?, ?)", (3, b'just text'))

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_table_content_media(self):
        response = self.client.get('/media/content/')
        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)
        self.assertIn('<img src="data:image;base64,', html)
        self.assertIn('<video controls', html)
        self.assertIn('BLOB, 9 bytes', html)

if __name__ == '__main__':
    unittest.main()
