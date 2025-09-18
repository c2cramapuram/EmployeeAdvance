import sqlite3

conn = sqlite3.connect("salary.db")
c = conn.cursor()

# Step 1: Rename old table
c.execute("ALTER TABLE transactions RENAME TO transactions_old;")

# Step 2: Create new table with correct schema
c.execute("""
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee TEXT,
    type TEXT,
    amount REAL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Step 3: Copy existing data into new table (set comment empty and created_at as current timestamp)
c.execute("""
INSERT INTO transactions (id, employee, type, amount)
SELECT id, employee, type, amount
FROM transactions_old;
""")

# Step 4: Drop old table
c.execute("DROP TABLE transactions_old;")

conn.commit()
conn.close()

print("Migration complete. 'comment' and 'created_at' columns added.")
