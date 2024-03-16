import settings
import sqlite3

DB_FILE_PATH = settings.DB_FILE_PATH


class DBManager:
    def __init__(self, db_path=DB_FILE_PATH):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.db_init()
        return self

    def db_init(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                sender TEXT NOT NULL,
                hash TEXT NOT NULL UNIQUE,
                receiver TEXT NOT NULL,
                amount INTEGER NOT NULL,
                ledger_version INTEGER NOT NULL,
                ledger_timestamp INTEGER NOT NULL
            )
        """
        )

    def insert_transactions(self, transactions):
        try:
            for transaction in transactions:
                self.cursor.execute(
                    """
                    INSERT OR IGNORE INTO transactions (sender, hash, receiver, amount, ledger_version, ledger_timestamp)
                    VALUES (:sender, :hash, :receiver, :amount, :ledger_version, :ledger_timestamp)
                """,
                    transaction,
                )
            # Removed the commit here to rely on context manager's commit/rollback
        except sqlite3.Error as e:
            print(f"An error occurred: {e}")
            raise  # Re-raise the exception to trigger the rollback in __exit__

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cursor is not None:
            self.cursor.close()
        if self.conn is not None:
            if exc_type is None:
                self.conn.commit()  # Commit on a successful exit
            else:
                self.conn.rollback()  # Rollback on exceptions
            self.conn.close()
