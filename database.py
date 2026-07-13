import sqlite3


DATABASE_NAME = "grimoire.db"


def create_database():
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


def get_albums():
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT title, url
        FROM albums
        ORDER BY id
    """)

    albums = cursor.fetchall()

    connection.close()

    return albums

def delete_album(self):
    selected = self.album_list.currentItem()

    if selected:
        title = selected.text()

        database.delete_album(title)

        self.load_albums()


def add_album(title, url):
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO albums (title, url)
        VALUES (?, ?)
    """, (title, url))

    connection.commit()
    connection.close()


def delete_album(title):
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM albums
        WHERE title = ?
    """, (title,))

    connection.commit()
    connection.close()    