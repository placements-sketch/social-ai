from app.db import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute("SELECT version();")
print(cursor.fetchone())

conn.close()