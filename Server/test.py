import mysql.connector

# Connect to MySQL
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="admin123", #enter your own login
    database="customer" # Change these credential as your own
)

cursor = conn.cursor()

print("Connected to MySQL!")
print("Type your SQL query or type 'exit' to quit.")

while True:
    query = input("\nSQL> ").strip()

    if query.lower() == "exit":
        break

    try:
        cursor.execute(query)

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            print("\n | ".join(columns))
            print("-" * 50)

            for row in cursor.fetchall():
                print(" | ".join(str(value) for value in row))
        else:
            conn.commit()
            print("Query executed successfully!")

    except mysql.connector.Error as e:
        print("Error:", e)

cursor.close()
conn.close()
print("Disconnected from MySQL.")
